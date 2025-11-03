import tempfile
from faster_whisper import WhisperModel
from config import WHISPER_MODEL_NAME

whisper_model = WhisperModel(WHISPER_MODEL_NAME, device="cpu", compute_type="int8")

def transcribe_wav(wav_bytes: bytes) -> str:
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(wav_bytes)
        path = tmp.name

    segments, _ = whisper_model.transcribe(path, language="sv")
    return " ".join(s.text.strip() for s in segments).strip()

