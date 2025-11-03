import json
import uuid
from datetime import datetime
from fastapi import WebSocket
from fastapi.websockets import WebSocketDisconnect, WebSocketState

from stt import transcribe_wav
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


async def ws_handler(ws: WebSocket):
    """
    WebSocket-protokoll för ESP32:
    - "hello": registrera device_id, room, mic format
    - binära frames: rå PCM16LE från mic
    - "end_recording": vi kör STT -> brain -> HA -> TTS och streamar tillbaka
    """
    await ws.accept()

    device_id = None
    room = "unknown"

    # default mic format, kan överskrivas i "hello"
    mic_sr = 16000
    mic_width = 2      # bytes per sample (2 = 16-bit)
    mic_ch = 1

    recorded_chunks = []
    recording_done = False

    try:
        while True:
            msg = await ws.receive()

            # Binärt = mic audio chunk
            if msg.get("bytes") is not None:
                if not recording_done:
                    recorded_chunks.append(msg["bytes"])
                continue

            # Text = kontrollmeddelande
            if msg.get("text") is not None:
                try:
                    data = json.loads(msg["text"])
                except Exception:
                    # garbage från klienten -> ignorera
                    continue

                msg_type = data.get("type")

                if msg_type == "hello":
                    # ESP32 registrerar sig
                    device_id = data.get("device_id", f"dev-{uuid.uuid4()}")
                    room = data.get("room", "unknown")

                    fmt = data.get("mic_format", {})
                    mic_sr = fmt.get("sample_rate", mic_sr)
                    mic_width = fmt.get("sample_width", mic_width)
                    mic_ch = fmt.get("channels", mic_ch)

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

                    recording_done = True

                    # 1. bygg WAV av inspelad PCM
                    pcm_all = b"".join(recorded_chunks)
                    wav_bytes = pcm_to_wav(
                        pcm_all,
                        sample_rate=mic_sr,
                        sample_width=mic_width,
                        channels=mic_ch,
                    )

                    # 2. STT
                    user_text = transcribe_wav(wav_bytes)

                    # 3. Brain (LLM) + ev. Home Assistant
                    action_obj = await ask_llm(user_text, room)
                    await call_home_assistant_if_needed(action_obj)
                    reply_text = action_obj.get("reply", "Okej.")

                    # 4. TTS (reply_text -> röst)
                    meta, tts_chunks = await synthesize_chunks(reply_text)

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

                    # 6. Reset så nästa fråga kan börja utan ny socket
                    recorded_chunks.clear()
                    recording_done = False

            # Klienten stänger
            if msg["type"] == "websocket.disconnect":
                break

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print("WS error:", e)

    finally:
        # Städa upp
        if device_id in clients and clients[device_id]["ws"] is ws:
            del clients[device_id]

        if ws.client_state != WebSocketState.DISCONNECTED:
            await ws.close()

        print(f"WS client {device_id or 'unknown'} disconnected")


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
    from .tts import synthesize_chunks  # import här för att undvika circular
    meta, tts_chunks = await synthesize_chunks(text)

    # bestäm mottagare
    if target_ids == ["*"]:
        chosen = list(clients.keys())
    else:
        chosen = [cid for cid in target_ids if cid in clients]

    print(f"Broadcast '{text}' to {chosen}")

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
            print(f"Broadcast to {cid} failed:", e)
            dead_clients.append(cid)

    # rensa döda clients
    for cid in dead_clients:
        if cid in clients:
            try:
                await clients[cid]["ws"].close()
            except Exception:
                pass
            del clients[cid]

