FROM python:3.11-slim

# 1. Systempaket
# - ffmpeg/sox hjälper whisper med olika wav-format och resampling
# - build utils (gcc etc.) kan ibland krävas för faster-whisper/piper wheels beroende på arch
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        sox \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 2. Installera piper-tts först. Vi gör det före requirements så vi kan ladda ner rösten redan i build.
RUN pip install --no-cache-dir piper-tts

# 3. Ladda ner svensk röst till /app/voices
#    OBS: byt "sv_SE-nst-medium" om du använder annan röst.
#RUN mkdir -p /app/voices && \
#    python -m piper.download_voices sv_SE-nst-medium --directory /app/voices

# 4. Kopiera requirements och installera resten
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. Kopiera all källkod (de nya modulerna)
#    Vi kopierar hela mappen så att vi kan köra som ett paket
COPY . .

# 6. Exponera porten
EXPOSE 5002

# 7. Default envs (kan overrideas i docker-compose)
ENV LITELLM_URL="http://litellm:4000/v1/chat/completions" \
    LITELLM_MODEL="your-fast-model" \
    LITELLM_KEY="" \
    HA_URL="http://homeassistant:8123" \
    HA_TOKEN="CHANGE_ME" \
    WHISPER_MODEL_NAME="tiny" \
    VOICE_DIR="/app/voices/sv_SE-nst-medium" \
    PIPER_VOLUME="0.8" \
    PIPER_LENGTH_SCALE="0.75" \
    PIPER_NOISE_SCALE="1.0" \
    PIPER_NOISE_W_SCALE="1.0" \
    PIPER_NORMALIZE="false"

# 8. Starta servern
#    Vi kör uvicorn direkt mot main:app.
#    --host 0.0.0.0 så andra maskiner i nätet kan nå den
#    --port 5002 så den matchar din compose och ESP32-klient
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5002"]

