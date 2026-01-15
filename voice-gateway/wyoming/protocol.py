"""
Wyoming protocol implementation for voice-gateway.

The Wyoming protocol uses JSONL + binary payloads over TCP sockets.
Wire format:
  1. JSON header line (newline-terminated)
  2. Optional JSON data (if data_length > 0)
  3. Optional binary payload (if payload_length > 0)
"""

import json
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

WYOMING_VERSION = "1.0.0"


@dataclass
class Event:
    """Wyoming protocol event."""
    type: str
    data: Dict[str, Any] = field(default_factory=dict)
    payload: Optional[bytes] = None

    def to_bytes(self) -> bytes:
        """Serialize event to Wyoming wire format."""
        header = {"type": self.type, "version": WYOMING_VERSION}

        data_bytes = b""
        if self.data:
            data_bytes = json.dumps(self.data).encode("utf-8")
            header["data_length"] = len(data_bytes)

        if self.payload:
            header["payload_length"] = len(self.payload)

        header_bytes = json.dumps(header).encode("utf-8") + b"\n"

        result = header_bytes
        if data_bytes:
            result += data_bytes + b"\n"
        if self.payload:
            result += self.payload

        return result


async def read_event(reader: asyncio.StreamReader) -> Optional[Event]:
    """Read a single Wyoming event from the stream."""
    try:
        # Read header line
        header_line = await reader.readline()
        if not header_line:
            return None

        header = json.loads(header_line.decode("utf-8").strip())
        event_type = header.get("type")
        if not event_type:
            logger.warning("Received event without type")
            return None

        data = {}
        payload = None

        # Read data section if present
        data_length = header.get("data_length", 0)
        if data_length > 0:
            data_bytes = await reader.readexactly(data_length)
            # Skip trailing newline after data
            await reader.readexactly(1)
            data = json.loads(data_bytes.decode("utf-8"))

        # Read payload if present
        payload_length = header.get("payload_length", 0)
        if payload_length > 0:
            payload = await reader.readexactly(payload_length)

        return Event(type=event_type, data=data, payload=payload)

    except asyncio.IncompleteReadError:
        logger.debug("Connection closed while reading event")
        return None
    except json.JSONDecodeError as e:
        logger.warning(f"Invalid JSON in event: {e}")
        return None
    except Exception as e:
        logger.exception(f"Error reading event: {e}")
        return None


async def write_event(writer: asyncio.StreamWriter, event: Event) -> None:
    """Write a single Wyoming event to the stream."""
    writer.write(event.to_bytes())
    await writer.drain()


# --- Audio Events ---

def audio_start(rate: int, width: int, channels: int, timestamp: Optional[int] = None) -> Event:
    """Create an audio-start event."""
    data = {"rate": rate, "width": width, "channels": channels}
    if timestamp is not None:
        data["timestamp"] = timestamp
    return Event(type="audio-start", data=data)


def audio_chunk(rate: int, width: int, channels: int, audio: bytes, timestamp: Optional[int] = None) -> Event:
    """Create an audio-chunk event with PCM payload."""
    data = {"rate": rate, "width": width, "channels": channels}
    if timestamp is not None:
        data["timestamp"] = timestamp
    return Event(type="audio-chunk", data=data, payload=audio)


def audio_stop(timestamp: Optional[int] = None) -> Event:
    """Create an audio-stop event."""
    data = {}
    if timestamp is not None:
        data["timestamp"] = timestamp
    return Event(type="audio-stop", data=data)


# --- ASR Events ---

def transcribe(name: Optional[str] = None, language: Optional[str] = None) -> Event:
    """Create a transcribe request event."""
    data = {}
    if name:
        data["name"] = name
    if language:
        data["language"] = language
    return Event(type="transcribe", data=data)


def transcript(text: str, language: Optional[str] = None) -> Event:
    """Create a transcript response event."""
    data = {"text": text}
    if language:
        data["language"] = language
    return Event(type="transcript", data=data)


# --- TTS Events ---

def synthesize(text: str, voice: Optional[str] = None, language: Optional[str] = None) -> Event:
    """Create a synthesize request event."""
    data = {"text": text}
    if voice:
        data["voice"] = {"name": voice}
    if language:
        if "voice" not in data:
            data["voice"] = {}
        data["voice"]["language"] = language
    return Event(type="synthesize", data=data)


# --- Info/Describe Events ---

def describe() -> Event:
    """Create a describe request event."""
    return Event(type="describe")


@dataclass
class AsrModel:
    """ASR model info."""
    name: str
    languages: List[str] = field(default_factory=list)
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "languages": self.languages,
            "description": self.description,
        }


@dataclass
class AsrProgram:
    """ASR program info."""
    name: str
    models: List[AsrModel] = field(default_factory=list)
    installed: bool = True
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "models": [m.to_dict() for m in self.models],
            "installed": self.installed,
            "description": self.description,
        }


@dataclass
class TtsVoice:
    """TTS voice info."""
    name: str
    languages: List[str] = field(default_factory=list)
    speakers: List[str] = field(default_factory=list)
    description: str = ""

    def to_dict(self) -> dict:
        d = {
            "name": self.name,
            "languages": self.languages,
            "description": self.description,
        }
        if self.speakers:
            d["speakers"] = self.speakers
        return d


@dataclass
class TtsProgram:
    """TTS program info."""
    name: str
    voices: List[TtsVoice] = field(default_factory=list)
    installed: bool = True
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "voices": [v.to_dict() for v in self.voices],
            "installed": self.installed,
            "description": self.description,
        }


@dataclass
class Info:
    """Service info response."""
    asr: List[AsrProgram] = field(default_factory=list)
    tts: List[TtsProgram] = field(default_factory=list)

    def to_event(self) -> Event:
        data = {}
        if self.asr:
            data["asr"] = [p.to_dict() for p in self.asr]
        if self.tts:
            data["tts"] = [p.to_dict() for p in self.tts]
        return Event(type="info", data=data)
