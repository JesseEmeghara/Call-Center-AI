# app.py

import os
import base64
from fastapi import FastAPI, HTTPException, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from twilio.rest import Client
import openai  # for chat
# import your STT/TTS helpers here
# from your_module import stt_recognize, tts_synthesize

# ── CONFIG ────────────────────────────────────────────────────────────────
TWILIO_SID      = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_TOKEN    = os.getenv("TWILIO_AUTH_TOKEN")
API_KEY         = os.getenv("API_KEY")
FROM_NUMBER     = os.getenv("FROM_NUMBER")    # "+18338790587"
API_BASE        = os.getenv("API_BASE")       # "https://assistant.emeghara.tech"
OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY")
openai.api_key  = OPENAI_API_KEY

if not all([TWILIO_SID, TWILIO_TOKEN, API_KEY, FROM_NUMBER, API_BASE, OPENAI_API_KEY]):
    raise RuntimeError("Missing one or more required env vars")

# ── FASTAPI + CLIENTS ─────────────────────────────────────────────────────
app = FastAPI()
twilio = Client(TWILIO_SID, TWILIO_TOKEN)

# ── CORS ───────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://www.emeghara.tech"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API KEY VERIFICATION ───────────────────────────────────────────────────
@app.middleware("http")
async def verify_api_key(request: Request, call_next):
    if request.url.path in ("/health", "/twiml", "/incoming", "/stream"):
        return await call_next(request)
    key = request.headers.get("x-api-key")
    if key != API_KEY:
        return JSONResponse({"detail": "Invalid API Key"}, status_code=401)
    return await call_next(request)

# ── MODELS ─────────────────────────────────────────────────────────────────
class CallStart(BaseModel):
    to: str
    from_: str | None = Field(None, alias="from")

class CallStop(BaseModel):
    callConnectionId: str

# ── IN-MEMORY STORE ─────────────────────────────────────────────────────────
TRANSCRIPTS: dict[str, list[str]] = {}

# ── HEALTH CHECK ────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok"}

# ── START A CALL ───────────────────────────────────────────────────────────
@app.post("/call/start")
async def start_call(payload: CallStart):
    to_number   = payload.to
    from_number = payload.from_ or FROM_NUMBER

    try:
        call = twilio.calls.create(
            to=to_number,
            from_=from_number,
            url=f"{API_BASE}/incoming"
        )
        # initialize transcript list
        TRANSCRIPTS[call.sid] = []
        return {"callConnectionId": call.sid}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── STOP A CALL ────────────────────────────────────────────────────────────
@app.post("/call/stop")
async def stop_call(payload: CallStop):
    try:
        twilio.calls(payload.callConnectionId).update(status="completed")
        return {"status": "completed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── TRANSCRIPT ROUTE ───────────────────────────────────────────────────────
@app.get("/call/transcript")
async def get_transcript(callConnectionId: str):
    lines = TRANSCRIPTS.get(callConnectionId, [])
    return {"transcript": lines}

# ── INCOMING CALL TWIML ─────────────────────────────────────────────────────
@app.post("/incoming")
async def incoming():
    # start Twilio MediaStreams on connect
    xml = f"""
<Response>
  <Start>
    <Stream url="{API_BASE.replace('https','wss')}/stream"/>
  </Start>
  <!-- silence until your WebSocket kicks in -->
  <Pause length="60"/>
  <Hangup/>
</Response>
"""
    return Response(content=xml, media_type="text/xml")

# ── WEBSOCKET FOR MEDIASTREAM ───────────────────────────────────────────────
@app.websocket("/stream")
async def media_stream(ws: WebSocket):
    # query string may carry CallSid
    call_sid = ws.query_params.get("callSid", "")
    await ws.accept()

    # send an initial greeting via TTS
    greeting = "Hello! Thanks for calling our AI call center. How can I help you today?"
    greeting_pcm = await tts_synthesize(greeting)
    await ws.send_json({"event":"media","media":{"payload":base64.b64encode(greeting_pcm).decode()}})

    # loop over incoming audio events
    async for msg in ws.iter_json():
        if msg.get("event") != "media":
            continue

        # decode and transcribe
        pcm_chunk = base64.b64decode(msg["media"]["payload"])
        user_text = await stt_recognize(pcm_chunk)
        if not user_text.strip():
            continue

        # store the line
        TRANSCRIPTS.setdefault(call_sid, []).append("User: " + user_text)

        # call GPT for a response
        resp = await openai.ChatCompletion.acreate(
            model="gpt-4o-audio-preview",
            messages=[
                {"role":"system","content":"You are a helpful phone receptionist."},
                *[
                  {"role":"user","content":ln}
                  for ln in TRANSCRIPTS[call_sid] if ln.startswith("User:")
                ]
            ]
        )
        reply_text = resp.choices[0].message.content
        TRANSCRIPTS[call_sid].append("AI: " + reply_text)

        # synthesize TTS & send back
        reply_pcm = await tts_synthesize(reply_text)
        await ws.send_json({
            "event":"media",
            "media":{"payload":base64.b64encode(reply_pcm).decode()}
        })

    await ws.close()
