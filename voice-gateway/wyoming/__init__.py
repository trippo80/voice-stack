"""
Wyoming protocol integration for voice-gateway.

This package provides Wyoming protocol compatibility for Home Assistant voice integration.
"""

from .server import start_wyoming_servers
from .protocol import (
    Event,
    read_event,
    write_event,
    audio_start,
    audio_chunk,
    audio_stop,
    transcript,
    Info,
    AsrProgram,
    AsrModel,
    TtsProgram,
    TtsVoice,
)

__all__ = [
    "start_wyoming_servers",
    "Event",
    "read_event",
    "write_event",
    "audio_start",
    "audio_chunk",
    "audio_stop",
    "transcript",
    "Info",
    "AsrProgram",
    "AsrModel",
    "TtsProgram",
    "TtsVoice",
]
