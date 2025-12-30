import json
import uuid
import asyncio
import logging
from datetime import datetime
from fastapi import WebSocket
from fastapi.websockets import WebSocketDisconnect, WebSocketState

from stt import transcribe_wav

logger = logging.getLogger(__name__)
from tts import synthesize_chunks
from brain import ask_llm, call_home_assistant_if_needed
from utils import pcm_to_wav

# Alla aktiva enheter
# clients[device_id] = {
#   "ws": WebSocket,
#   "room": "vardagsrum",
#   "last_seen": datetime.utcnow(),
# }
clients = {}

# Audio limits
MAX_AUDIO_BYTES = 10 * 1024 * 1024  # 10 MB max recording
MAX_AUDIO_DURATION_SEC = 60  # 60 seconds max
PIPELINE_TIMEOUT_SEC = 60  # timeout for full STT -> LLM -> TTS pipeline


async def ws_handler(ws: WebSocket):
    """
    WebSocket-protokoll för ESP32:
    - "hello": registrera device_id, room, mic format
    - binära frames: rå PCM16LE från mic
    - "end_recording": vi kör STT -> brain -> HA -> TTS och streamar tillbaka
    """
    await ws.accept()
    logger.info("New WebSocket connection accepted")

    device_id = None
    room = "unknown"

    # default mic format, kan överskrivas i "hello"
    mic_sr = 16000
    mic_width = 2      # bytes per sample (2 = 16-bit)
    mic_ch = 1

    recorded_chunks = []
    recorded_bytes_total = 0
    recording_done = False

    try:
        while True:
            msg = await ws.receive()

            # Binärt = mic audio chunk
            if msg.get("bytes") is not None:
                chunk = msg["bytes"]
                logger.debug(f"[{device_id or 'unknown'}] Received binary chunk: {len(chunk)} bytes")
                if not recording_done:
                    # Check audio size limit
                    if recorded_bytes_total + len(chunk) > MAX_AUDIO_BYTES:
                        logger.warning(f"[{device_id}] Recording too large, rejecting")
                        await ws.send_json({
                            "type": "error",
                            "error": "recording_too_large",
                            "message": f"Recording exceeds {MAX_AUDIO_BYTES // (1024*1024)} MB limit",
                        })
                        recorded_chunks.clear()
                        recorded_bytes_total = 0
                        recording_done = True
                        continue
                    recorded_chunks.append(chunk)
                    recorded_bytes_total += len(chunk)
                continue

            # Text = kontrollmeddelande
            if msg.get("text") is not None:
                raw_text = msg["text"]
                logger.debug(f"[{device_id or 'unknown'}] Received text: {raw_text[:200]}")
                try:
                    data = json.loads(raw_text)
                except Exception as e:
                    logger.warning(f"[{device_id or 'unknown'}] Invalid JSON received: {e}")
                    continue

                msg_type = data.get("type")
                logger.info(f"[{device_id or 'unknown'}] Message type: {msg_type}")

                if msg_type == "hello":
                    # ESP32 registrerar sig
                    device_id = data.get("device_id", f"dev-{uuid.uuid4()}")
                    room = data.get("room", "unknown")

                    fmt = data.get("mic_format", {})
                    mic_sr = fmt.get("sample_rate", mic_sr)
                    mic_width = fmt.get("sample_width", mic_width)
                    mic_ch = fmt.get("channels", mic_ch)

                    logger.info(f"[{device_id}] Registered: room={room}, mic={mic_sr}Hz/{mic_width*8}bit/{mic_ch}ch")

                    clients[device_id] = {
                        "ws": ws,
                        "room": room,
                        "last_seen": datetime.utcnow(),
                    }

                    await ws.send_json({
                        "type": "hello_ack",
                        "device_id": device_id,
                        "room": room,
                    })

                elif msg_type == "end_recording":
                    # Slut på tal → vi processar allt
                    logger.info(f"[{device_id}] End recording: {len(recorded_chunks)} chunks, {recorded_bytes_total} bytes")

                    recording_done = True

                    # Check if we have any audio
                    if not recorded_chunks:
                        await ws.send_json({
                            "type": "error",
                            "error": "no_audio",
                            "message": "No audio data received",
                        })
                        recording_done = False
                        continue

                    # 1. bygg WAV av inspelad PCM
                    pcm_all = b"".join(recorded_chunks)

                    # Check duration limit
                    bytes_per_sample = mic_width * mic_ch
                    duration_sec = len(pcm_all) / (mic_sr * bytes_per_sample)
                    if duration_sec > MAX_AUDIO_DURATION_SEC:
                        await ws.send_json({
                            "type": "error",
                            "error": "recording_too_long",
                            "message": f"Recording exceeds {MAX_AUDIO_DURATION_SEC}s limit",
                        })
                        recorded_chunks.clear()
                        recorded_bytes_total = 0
                        recording_done = False
                        continue

                    wav_bytes = pcm_to_wav(
                        pcm_all,
                        sample_rate=mic_sr,
                        sample_width=mic_width,
                        channels=mic_ch,
                    )

                    try:
                        # Run pipeline with timeout
                        async def run_pipeline():
                            # 2. STT (run in thread pool to avoid blocking)
                            logger.info(f"[{device_id}] Starting STT...")
                            user_text = await asyncio.to_thread(transcribe_wav, wav_bytes)
                            logger.info(f"[{device_id}] STT result: '{user_text}'")

                            if not user_text.strip():
                                logger.warning(f"[{device_id}] Empty transcription")
                                return None, "Jag hörde inte vad du sa."

                            # 3. Brain (LLM) + ev. Home Assistant
                            logger.info(f"[{device_id}] Calling LLM...")
                            action_obj = await ask_llm(user_text, room)
                            logger.info(f"[{device_id}] LLM response: {action_obj}")
                            await call_home_assistant_if_needed(action_obj)
                            reply_text = action_obj.get("reply", "Okej.")

                            # 4. TTS (reply_text -> röst)
                            logger.info(f"[{device_id}] Generating TTS for: '{reply_text}'")
                            meta, tts_chunks = await synthesize_chunks(reply_text)
                            logger.info(f"[{device_id}] TTS done: {len(tts_chunks)} chunks")
                            return (meta, tts_chunks), reply_text

                        result, reply_text = await asyncio.wait_for(
                            run_pipeline(),
                            timeout=PIPELINE_TIMEOUT_SEC
                        )

                        if result is None:
                            # Empty transcription - send simple response
                            meta, tts_chunks = await synthesize_chunks(reply_text)
                        else:
                            meta, tts_chunks = result

                    except asyncio.TimeoutError:
                        logger.error(f"[{device_id}] Pipeline timeout after {PIPELINE_TIMEOUT_SEC}s")
                        await ws.send_json({
                            "type": "error",
                            "error": "pipeline_timeout",
                            "message": f"Processing timed out after {PIPELINE_TIMEOUT_SEC}s",
                        })
                        recorded_chunks.clear()
                        recorded_bytes_total = 0
                        recording_done = False
                        continue

                    except Exception as e:
                        logger.exception(f"[{device_id}] Pipeline error: {e}")
                        await ws.send_json({
                            "type": "error",
                            "error": "pipeline_error",
                            "message": "Failed to process audio",
                        })
                        recorded_chunks.clear()
                        recorded_bytes_total = 0
                        recording_done = False
                        continue

                    # 5. Skicka ner svaret till just den här klienten:
                    #    Först metadata (så ESP32 kan sätta I2S-format)
                    await ws.send_json({
                        "type": "assistant_reply",
                        "text": reply_text,
                        "sample_rate": meta["sample_rate"],
                        "sample_width": meta["sample_width"],
                        "channels": meta["channels"],
                    })

                    #    Sedan binära PCM16-chunks i ordning
                    for ch_bytes in tts_chunks:
                        await ws.send_bytes(ch_bytes)

                    #    Och säg att vi är klara
                    await ws.send_json({
                        "type": "assistant_end"
                    })
                    logger.info(f"[{device_id}] Response sent successfully")

                    # 6. Reset så nästa fråga kan börja utan ny socket
                    recorded_chunks.clear()
                    recorded_bytes_total = 0
                    recording_done = False

            # Klienten stänger
            if msg["type"] == "websocket.disconnect":
                logger.info(f"[{device_id or 'unknown'}] Client requested disconnect")
                break

    except WebSocketDisconnect:
        logger.info(f"[{device_id or 'unknown'}] WebSocket disconnected")
    except Exception as e:
        logger.exception(f"[{device_id or 'unknown'}] WebSocket error: {e}")

    finally:
        # Städa upp
        if device_id in clients and clients[device_id]["ws"] is ws:
            del clients[device_id]

        if ws.client_state != WebSocketState.DISCONNECTED:
            await ws.close()

        logger.info(f"[{device_id or 'unknown'}] Connection closed, cleanup done")


async def broadcast_tts(target_ids, text: str):
    """
    Används av /announce:
    - Generera TTS för `text` en gång
    - Skicka ut till:
      * varje target device i target_ids
      * eller alla om target_ids == ["*"]
    Protokoll till klienterna:
      1) JSON {type:"broadcast_start", sample_rate,..., text:...}
      2) binära PCM16-chunks
      3) JSON {type:"broadcast_end"}
    """
    # synthesize_chunks is already imported at module level
    meta, tts_chunks = await synthesize_chunks(text)

    # bestäm mottagare
    if target_ids == ["*"]:
        chosen = list(clients.keys())
    else:
        chosen = [cid for cid in target_ids if cid in clients]

    logger.info(f"Broadcasting '{text}' to {chosen}")

    dead_clients = []

    for cid in chosen:
        ws = clients[cid]["ws"]
        if ws.client_state != WebSocketState.CONNECTED:
            dead_clients.append(cid)
            continue

        try:
            # metadata först
            await ws.send_json({
                "type": "broadcast_start",
                "text": text,
                "sample_rate": meta["sample_rate"],
                "sample_width": meta["sample_width"],
                "channels": meta["channels"],
            })

            # ljudet
            for ch_bytes in tts_chunks:
                await ws.send_bytes(ch_bytes)

            # slut
            await ws.send_json({
                "type": "broadcast_end"
            })

        except Exception as e:
            logger.error(f"Broadcast to {cid} failed: {e}")
            dead_clients.append(cid)

    # rensa döda clients
    for cid in dead_clients:
        if cid in clients:
            try:
                await clients[cid]["ws"].close()
            except Exception:
                pass
            del clients[cid]

