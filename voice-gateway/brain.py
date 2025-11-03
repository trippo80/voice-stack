import json
import httpx
import re
from config import LITELLM_URL, LITELLM_MODEL, LITELLM_KEY, HA_URL, HA_TOKEN

def build_system_prompt(room: str) -> str:
    return f"""
Du är en lokal röstassistent i rummet \"{room}\".
Om användaren försöker styra hemmet ska du svara med strikt JSON:
{{
 "action":"homeassistant.call_service",
 "domain":"<domain>",
 "service":"<service>",
 "entity_id":"<entity_id>",
 "reply":"<vad du ska säga till användaren>"
}}

Annars svarar du strikt JSON:
{{
 "action":"say",
 "reply":"<vad du ska säga till användaren>"
}}

VIKTIGT:
- Svara bara med ett (1) JSON-objekt.
- Inga förklaringar, ingen tankegång, inget <think>. Inget utanför JSON.
- Svara kortfattat.
- Svara på svenska.
""".strip()

async def ask_llm(user_text: str, room: str) -> dict:
    headers = {"Content-Type": "application/json"}
    if LITELLM_KEY:
        headers["Authorization"] = f"Bearer {LITELLM_KEY}"

    payload = {
        "model": LITELLM_MODEL,
        "messages": [
            {"role": "system", "content": build_system_prompt(room)},
            {"role": "user", "content": user_text},
        ],
        "temperature": 0.2,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(LITELLM_URL, json=payload, headers=headers)

    raw = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
    m = re.search(r"\{[\s\S]*\}", raw)
    if not m:
        return {"action": "say", "reply": "Jag förstod inte riktigt."}

    try:
        return json.loads(m.group(0))
    except Exception:
        return {"action": "say", "reply": "Jag förstod inte riktigt."}

async def call_home_assistant_if_needed(action_obj: dict):
    if action_obj.get("action") != "homeassistant.call_service":
        return

    domain = action_obj.get("domain")
    service = action_obj.get("service")
    entity_id = action_obj.get("entity_id")
    if not (domain and service and entity_id):
        return

    url = f"{HA_URL}/api/services/{domain}/{service}"
    headers = {
        "Authorization": f"Bearer {HA_TOKEN}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        await client.post(url, json={"entity_id": entity_id}, headers=headers)

