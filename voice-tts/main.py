from fastapi import FastAPI
from fastapi.responses import Response
import uvicorn
from piper import PiperVoice, SynthesisConfig
import io
import wave
import os

app = FastAPI()

VOICE_DIR = "./voices"
VOICE_MODEL = os.path.join(VOICE_DIR, "sv_SE-lisa-medium.onnx")
VOICE_CONFIG = os.path.join(VOICE_DIR, "sv_SE-lisa-medium.onnx.json")

voice = PiperVoice.load(VOICE_MODEL, VOICE_CONFIG)

@app.post("/tts")
async def tts(payload: dict):
    text = payload.get("text", "Hej, detta är ett test")

    syn_config = SynthesisConfig(
        volume=0.5,
        length_scale=1.0,
        noise_scale=1.0,
        noise_w_scale=0.8,
        normalize_audio=False
    )

    wav_io = io.BytesIO()
    pcm_bytes_all = b""
    sample_rate = None
    sample_width = None
    sample_channels = None
    
    for chunk in voice.synthesize(text):
        if sample_rate is None:
            sample_rate = chunk.sample_rate
            sample_width = chunk.sample_width
            sample_channels = chunk.sample_channels

        pcm_bytes_all += chunk.audio_int16_bytes

    with wave.open(wav_io, "wb") as wav_file:
        wav_file.setnchannels(sample_channels or 1)
        wav_file.setsampwidth(sample_width or 2)
        wav_file.setframerate(sample_rate or 16000)
        wav_file.writeframes(pcm_bytes_all)

    return Response(content=wav_io.getvalue(), media_type="audio/wav")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5003)
