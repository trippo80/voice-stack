from fastapi import FastAPI, UploadFile, File
from faster_whisper import WhisperModel
import tempfile
import uvicorn

app = FastAPI()

# CPU only, small model = better, tiny model = faster
model = WhisperModel(
    "tiny",
    device="cpu",
    compute_type="int8"
)

@app.post("/stt")
async def stt(file: UploadFile = File(...)):
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        wav_path = tmp.name
        tmp.write(await file.read())

    segments, info = model.transcribe(wav_path, language="sv")
    text = " ".join([seg.text.strip() for seg in segments]).strip()

    return { "text": text }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5001)
