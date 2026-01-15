"""
Wyoming ASR service handler.

Exposes Whisper STT as a Wyoming-compatible service that Home Assistant can discover and use.
"""

import asyncio
import logging

from .protocol import (
    read_event, write_event,
    transcript,
    Info, AsrProgram, AsrModel,
)
from stt import transcribe_wav
from utils import pcm_to_wav
from config import WHISPER_MODEL_NAME, ASR_LANGUAGE

logger = logging.getLogger(__name__)


def get_asr_info() -> Info:
    """Return ASR service info for Wyoming discovery."""
    return Info(
        asr=[
            AsrProgram(
                name="whisper",
                description=f"Faster Whisper ({WHISPER_MODEL_NAME})",
                models=[
                    AsrModel(
                        name=WHISPER_MODEL_NAME,
                        languages=[ASR_LANGUAGE],
                        description=f"Whisper {WHISPER_MODEL_NAME} model",
                    )
                ],
                installed=True,
            )
        ]
    )


async def handle_asr_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    """Handle a single Wyoming ASR client connection."""
    peer = writer.get_extra_info("peername")
    logger.info(f"[ASR] New connection from {peer}")

    # Audio buffer state
    audio_buffer = bytearray()
    audio_rate = 16000
    audio_width = 2
    audio_channels = 1

    try:
        while True:
            event = await read_event(reader)
            if event is None:
                logger.debug(f"[ASR] Connection closed by {peer}")
                break

            logger.debug(f"[ASR] Received event: {event.type}")

            if event.type == "describe":
                # Respond with service info
                info = get_asr_info()
                await write_event(writer, info.to_event())
                logger.info(f"[ASR] Sent service info to {peer}")

            elif event.type == "transcribe":
                # Prepare for incoming audio stream
                # Audio will follow: audio-start -> audio-chunk* -> audio-stop
                audio_buffer.clear()
                requested_language = event.data.get("language", ASR_LANGUAGE)
                logger.info(f"[ASR] Transcribe request (language={requested_language})")

            elif event.type == "audio-start":
                # Start of audio stream
                audio_rate = event.data.get("rate", 16000)
                audio_width = event.data.get("width", 2)
                audio_channels = event.data.get("channels", 1)
                audio_buffer.clear()
                logger.debug(f"[ASR] Audio stream started: {audio_rate}Hz, {audio_width*8}bit, {audio_channels}ch")

            elif event.type == "audio-chunk":
                # Accumulate audio data
                if event.payload:
                    audio_buffer.extend(event.payload)
                    # Update format from chunk if provided
                    if "rate" in event.data:
                        audio_rate = event.data["rate"]
                    if "width" in event.data:
                        audio_width = event.data["width"]
                    if "channels" in event.data:
                        audio_channels = event.data["channels"]

            elif event.type == "audio-stop":
                # End of audio stream - perform transcription
                if not audio_buffer:
                    logger.warning(f"[ASR] Empty audio buffer from {peer}")
                    await write_event(writer, transcript(""))
                    continue

                logger.info(f"[ASR] Processing {len(audio_buffer)} bytes of audio")

                try:
                    # Convert PCM to WAV
                    wav_bytes = pcm_to_wav(
                        bytes(audio_buffer),
                        sample_rate=audio_rate,
                        sample_width=audio_width,
                        channels=audio_channels,
                    )

                    # Run Whisper transcription in thread pool
                    text = await asyncio.to_thread(transcribe_wav, wav_bytes)
                    logger.info(f"[ASR] Transcribed: '{text}'")

                    # Send transcript response
                    await write_event(writer, transcript(text, language=ASR_LANGUAGE))

                except Exception as e:
                    logger.exception(f"[ASR] Transcription error: {e}")
                    await write_event(writer, transcript(""))

                finally:
                    audio_buffer.clear()

            else:
                logger.debug(f"[ASR] Ignoring unknown event type: {event.type}")

    except asyncio.CancelledError:
        logger.info(f"[ASR] Connection cancelled for {peer}")
    except Exception as e:
        logger.exception(f"[ASR] Error handling client {peer}: {e}")
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        logger.info(f"[ASR] Connection closed for {peer}")
