from fastapi import APIRouter, File, Form, UploadFile, Response
from typing import Dict, Any, List

from stt import transcribe_wav
from tts import synthesize_chunks, build_wav
from brain import ask_llm, call_home_assistant_if_needed
from websocket_handler import clients, broadcast_tts

router = APIRouter()

@router.get("/health")
async def health():
    return {
        "ok": True,
        "connected_clients": list(clients.keys()),
    }

@router.post("/pipeline-http")
async def pipeline_http(room: str = Form(...), audio: UploadFile = File(...)):
    """
    För test via curl/Postman utan WebSocket.
    Tar en WAV + room. Returnerar färdig TTS-WAV.
    """
    wav_in = await audio.read()

    # 1. STT
    user_text = transcribe_wav(wav_in)

    # 2. Brain/LLM + HA
    action = await ask_llm(user_text, room)
    await call_home_assistant_if_needed(action)
    reply = action.get("reply", "Okej.")

    # 3. TTS
    meta, chunks = await synthesize_chunks(reply)
    out_wav = build_wav(chunks, meta)

    return Response(content=out_wav, media_type="audio/wav")

@router.post("/announce")
async def announce(body: Dict[str, Any]):
    """
    Broadcast text-till-röst till en eller flera enheter.
    Body-exempel:
    {
      "targets": ["vardagsrum", "kitchen"]
    }
    eller
    {
      "targets": ["*"]
    }
    och
    {
      "text": "Maten är klar!"
    }
    """
    targets: List[str] = body.get("targets", [])
    text: str = body.get("text", "")

    if not targets:
        return {"ok": False, "error": "No targets"}
    if not text:
        return {"ok": False, "error": "No text"}

    await broadcast_tts(targets, text)
    return {"ok": True, "sent_to": targets}

