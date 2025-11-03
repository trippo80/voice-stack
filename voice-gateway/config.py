import os

# LiteLLM
LITELLM_URL = os.getenv("LITELLM_URL", "http://litellm:4000/v1/chat/completions")
LITELLM_MODEL = os.getenv("LITELLM_MODEL", "your-fast-model")
LITELLM_KEY = os.getenv("LITELLM_KEY", "")

# Home Assistant
HA_URL = os.getenv("HA_URL", "http://homeassistant:8123")
HA_TOKEN = os.getenv("HA_TOKEN", "CHANGE_ME")

# Whisper (STT)
WHISPER_MODEL_NAME = os.getenv("WHISPER_MODEL_NAME", "tiny")

# Piper (TTS)
VOICE_DIR = os.getenv("VOICE_DIR", "/app/voices")
VOICE_MODEL_PATH = os.path.join(VOICE_DIR, "sv_SE-lisa-medium.onnx")
VOICE_CONFIG_PATH = os.path.join(VOICE_DIR, "sv_SE-lisa-medium.onnx.json")

PIPER_VOLUME = float(os.getenv("PIPER_VOLUME", "0.8"))
PIPER_LENGTH_SCALE = float(os.getenv("PIPER_LENGTH_SCALE", "0.75"))
PIPER_NOISE_SCALE = float(os.getenv("PIPER_NOISE_SCALE", "1.0"))
PIPER_NOISE_W_SCALE = float(os.getenv("PIPER_NOISE_W_SCALE", "1.0"))
PIPER_NORMALIZE = os.getenv("PIPER_NORMALIZE", "false").lower() == "true"
