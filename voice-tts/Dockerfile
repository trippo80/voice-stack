FROM python:3.11-slim

RUN apt-get update && apt-get install -y ffmpeg sox && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --no-cache-dir piper-tts

#RUN python -m piper.download_voices sv_SE-lisa-medium

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .
COPY voices voices

EXPOSE 5003
CMD ["python", "main.py"]
