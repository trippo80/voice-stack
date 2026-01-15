"""
Wyoming TTS service handler.

Exposes Piper TTS as a Wyoming-compatible service that Home Assistant can discover and use.
"""

import asyncio
import logging

from .protocol import (
    read_event, write_event,
    audio_start, audio_chunk, audio_stop,
    Info, TtsProgram, TtsVoice, Attribution,
)
from tts import synthesize_chunks
from config import VOICE_NAME, VOICE_LANGUAGE

PIPER_ATTRIBUTION = Attribution(
    name="rhasspy",
    url="https://github.com/rhasspy/piper",
)

logger = logging.getLogger(__name__)

# Audio format from Piper
SAMPLE_RATE = 16000
SAMPLE_WIDTH = 2  # 16-bit
CHANNELS = 1  # mono


def get_tts_info() -> Info:
    """Return TTS service info for Wyoming discovery."""
    return Info(
        tts=[
            TtsProgram(
                name="piper",
                description="A fast, local, neural text to speech engine",
                attribution=PIPER_ATTRIBUTION,
                installed=True,
                voices=[
                    TtsVoice(
                        name=VOICE_NAME,
                        languages=[VOICE_LANGUAGE],
                        attribution=PIPER_ATTRIBUTION,
                        installed=True,
                        description=f"Piper voice: {VOICE_NAME}",
                    )
                ],
            )
        ]
    )


async def handle_tts_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    """Handle a single Wyoming TTS client connection."""
    peer = writer.get_extra_info("peername")
    logger.info(f"[TTS] New connection from {peer}")

    try:
        while True:
            event = await read_event(reader)
            if event is None:
                logger.debug(f"[TTS] Connection closed by {peer}")
                break

            logger.debug(f"[TTS] Received event: {event.type}")

            if event.type == "describe":
                # Respond with service info
                info = get_tts_info()
                await write_event(writer, info.to_event())
                logger.info(f"[TTS] Sent service info to {peer}")

            elif event.type == "synthesize":
                # Extract text to synthesize
                text = event.data.get("text", "")
                if not text:
                    logger.warning(f"[TTS] Empty synthesize request from {peer}")
                    continue

                requested_voice = event.data.get("voice", {})
                voice_name = requested_voice.get("name") if isinstance(requested_voice, dict) else None
                logger.info(f"[TTS] Synthesizing '{text[:50]}...' (voice={voice_name or 'default'})")

                try:
                    # Generate TTS audio using existing Piper integration
                    meta, chunks = await synthesize_chunks(text)

                    rate = meta.get("sample_rate", SAMPLE_RATE)
                    width = meta.get("sample_width", SAMPLE_WIDTH)
                    ch = meta.get("channels", CHANNELS)

                    # Send audio-start
                    await write_event(writer, audio_start(rate, width, ch))

                    # Send audio chunks
                    for chunk_data in chunks:
                        await write_event(writer, audio_chunk(rate, width, ch, chunk_data))

                    # Send audio-stop
                    await write_event(writer, audio_stop())
                    logger.info(f"[TTS] Sent {len(chunks)} audio chunks to {peer}")

                except Exception as e:
                    logger.exception(f"[TTS] Synthesis error: {e}")
                    # Send empty audio-stop to signal completion even on error
                    await write_event(writer, audio_stop())

            else:
                logger.debug(f"[TTS] Ignoring unknown event type: {event.type}")

    except asyncio.CancelledError:
        logger.info(f"[TTS] Connection cancelled for {peer}")
    except Exception as e:
        logger.exception(f"[TTS] Error handling client {peer}: {e}")
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        logger.info(f"[TTS] Connection closed for {peer}")
