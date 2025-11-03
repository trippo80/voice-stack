import io, wave
from typing import List
from piper import PiperVoice, SynthesisConfig
from config import (
    VOICE_MODEL_PATH, VOICE_CONFIG_PATH,
    PIPER_VOLUME, PIPER_LENGTH_SCALE,
    PIPER_NOISE_SCALE, PIPER_NOISE_W_SCALE, PIPER_NORMALIZE
)

voice = PiperVoice.load(VOICE_MODEL_PATH, VOICE_CONFIG_PATH)

async def synthesize_chunks(text: str):
    cfg = SynthesisConfig(
        volume=PIPER_VOLUME,
        length_scale=PIPER_LENGTH_SCALE,
        noise_scale=PIPER_NOISE_SCALE,
        noise_w_scale=PIPER_NOISE_W_SCALE,
        normalize_audio=PIPER_NORMALIZE,
    )

    first_meta = None
    chunks = []

    for c in voice.synthesize(text, syn_config=cfg):
        if not first_meta:
            first_meta = {
                "sample_rate": c.sample_rate,
                "sample_width": c.sample_width,
                "channels": c.sample_channels,
            }
        chunks.append(c.audio_int16_bytes)

    return first_meta or {"sample_rate": 16000, "sample_width": 2, "channels": 1}, chunks

def build_wav(chunks: List[bytes], meta: dict) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(meta["channels"])
        w.setsampwidth(meta["sample_width"])
        w.setframerate(meta["sample_rate"])
        w.writeframes(b"".join(chunks))
    return buf.getvalue()

