import express from 'express';
import FormData from 'form-data';
import multer from 'multer';
import fetch from 'node-fetch';

const app = express();
app.use(express.json());

const upload = multer();

const LITELLM_URL = process.env.LITELLM_URL;
const LITELLM_MODEL = process.env.LITELLM_MODEL;
const LITELLM_TOKEN = process.env.LITELLM_TOKEN;
const HA_URL = process.env.HA_URL;
const HA_TOKEN = process.env.HA_TOKEN;
const STT_URL = process.env.STT_URL || 'http://voice-stt:5001/stt';
const TTS_URL = process.env.TTS_URL || 'http://voice-tts:5003/tts';

const buildSystemPrompt = (room) => {
	return `
Du är en lokal röstassistemt i rummet "${room}".
Om användaren försöker styra hemmet ska du svara med strikt JSON:
{
	"action": "homeassistant.call_service",
	"domain": "<domain>",
	"service": "<service>",
	"entity_id": "<entity_id>",
	"reply": "<vad du ska säga till användaren>"
}

Annars svarar du strikt JSON:
{
	"action": "say",
	"reply": "<vad du ska säga til användaren>"
}

VIKTIGT:
- Svara bara med ett (1) JSON-objekt.
- Inga förklaringar, ingen tankegång, inget <think>. Inget utanför JSON.
- Svara kortfattat.
- Skriv på svenska.
`;
}

const askLLM = async (userText, room) => {
  const llmResp = await fetch(LITELLM_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${LITELLM_TOKEN}`
    },
    body: JSON.stringify({
      model: LITELLM_MODEL,
      messages: [
        { role: 'system', content: buildSystemPrompt(room || 'unknown_room' )},
        { role: 'user', content: userText }
      ],
      temperature: 0.2
    })
  });
  if (!llmResp.ok) {
    const errText = await llmResp.text();
    console.error('LiteLLM error:', llmResp.status, errText);
    return {
      action: 'say',
      reply: 'Jag kunde inte tänka klart just nu.'
    };
  }

  const llmJson = await llmResp.json();
  const rawContent = llmJson.choices?.[0]?.message?.content ?? '';

  try {
    return JSON.parse(rawContent);
  } catch {
    return { action: 'say', reply: 'Jag förstod inte riktigt' };
  }
};

const maybeCallHA = async (actionObj) => {
  if (actionObj.action === 'homeassistant.call_service') {
    try {
      await fetch(`${HA_URL}/api/services/${actionObj.domain}/${actionObj.service}`, {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${HA_TOKEN}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ entity_id: actionObj.entity_id })
      });
    } catch (e) {
      console.error("Home Assistant call failed:", e);
    }
  }
};

async function synthesizeVoice(textToSpeak) {
  const ttsResp = await fetch(TTS_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: textToSpeak })
  });

  if (!ttsResp.ok) {
    const errText = await ttsResp.text();
    console.error("TTS error:", ttsResp.status, errText);
    return null;
  }

  const wavBuf = Buffer.from(await ttsResp.arrayBuffer());
  return wavBuf;
};

app.post('/brain', async (req, res) => {
	const { text, room } = req.body;

  const actionObj = await askLLM(text, room);
  await maybeCallHA(actionObj);

  return res.json({
    reply: actionObj.reply || 'Okej.',
    action: actionObj.action,
    domain: actionObj?.domain,
    service: actionObj?.service,
    entity_id: actionObj?.entity_id
  });
});

app.post("/pipeline", upload.fields([{ name: "audio" }, { name: "room" }]), async (req, res) => {
  try {
    // 1. plocka ut ljudet och rummet
    const room = req.body.room || "unknown";
    const audioFile = req.files["audio"]?.[0];
    if (!audioFile) {
      return res.status(400).json({ error: "Missing audio file" });
    }

    // 2. skicka ljudet till STT
    const sttForm = new FormData();
    sttForm.append("file", audioFile.buffer, {
        filename: "user.wav",
        contentType: audioFile.mimetype || "audio/wav",
    });

    const sttResp = await fetch(STT_URL, {
      method: "POST",
      body: sttForm,
      headers: sttForm.getHeaders()
    });

    if (!sttResp.ok) {
      const errText = await sttResp.text();
      console.error("STT error:", sttResp.status, errText);
      return res.status(500).json({ error: "STT failed", detail: errText });
    }

    const sttJson = await sttResp.json();
    const userText = sttJson.text || "";

    // 3. kör hjärnan på texten
    const actionObj = await askLLM(userText, room);

    // 4. ev. kör Home Assistant
    await maybeCallHA(actionObj);

    const replyText = actionObj.reply || "Okej.";

    // 5. TTS -> wav buffer
    const wavBuf = await synthesizeVoice(replyText);
    if (!wavBuf) {
        return res.status(500).json({ error: "TTS failed" });
    }

    // 6. svara direkt med ljudet
    res.setHeader("Content-Type", "audio/wav");
    return res.send(wavBuf);

  } catch (e) {
    console.error("pipeline error:", e);
    return res.status(500).json({ error: "pipeline crashed", detail: String(e) });
  }
});

app.listen(5002, () => {
	console.log('voice-brain listening on :5002');
});

