# app.py

import os
import json
import base64
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from twilio.rest import Client

# ── CONFIG ────────────────────────────────────────────────────────────────
TWILIO_SID      = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_TOKEN    = os.getenv("TWILIO_AUTH_TOKEN")
API_KEY         = os.getenv("API_KEY")
FROM_NUMBER     = os.getenv("FROM_NUMBER")      # e.g. "+18338790587"
API_BASE        = os.getenv("API_BASE")         # e.g. "https://assistant.emeghara.tech"
LEADS_TO        = os.getenv("LEADS_TO")         # comma-separated emails
SMTP_HOST       = os.getenv("SMTP_HOST")
SMTP_PORT       = int(os.getenv("SMTP_PORT", 587))
SMTP_USER       = os.getenv("SMTP_USER")
SMTP_PASS       = os.getenv("SMTP_PASS")

if not all([TWILIO_SID, TWILIO_TOKEN, API_KEY, FROM_NUMBER, API_BASE]):
    raise RuntimeError("One or more required env vars missing")

# ── APP & CLIENT SETUP ─────────────────────────────────────────────────────
app = FastAPI()
twilio_client = Client(TWILIO_SID, TWILIO_TOKEN)

# ── CORS ───────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
      "https://assistant.emeghara.tech",
      "https://www.emeghara.tech",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── VERIFY API-KEY ─────────────────────────────────────────────────────────
@app.middleware("http")
async def verify_api_key(request: Request, call_next):
    if request.url.path in ("/health", "/twiml", "/incoming", "/stream"):
        return await call_next(request)
    key = request.headers.get("x-api-key")
    if key != API_KEY:
        return JSONResponse({"detail": "Invalid API Key"}, status_code=401)
    return await call_next(request)

# ── PAYLOAD MODELS ─────────────────────────────────────────────────────────
class CallStartPayload(BaseModel):
    to: str
    from_: str | None = Field(None, alias="from")

class CallStopPayload(BaseModel):
    callConnectionId: str

# ── HEALTH CHECK ────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok"}

# ── START A CALL ────────────────────────────────────────────────────────────
@app.post("/call/start")
async def start_call(payload: CallStartPayload):
    to_number   = payload.to
    from_number = payload.from_ or FROM_NUMBER
    try:
        call = twilio_client.calls.create(
            to=to_number,
            from_=from_number,
            url=f"{API_BASE}/incoming"
        )
        return {"callConnectionId": call.sid}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── STOP (HANG UP) A CALL ───────────────────────────────────────────────────
@app.post("/call/stop")
async def stop_call(payload: CallStopPayload):
    try:
        twilio_client.calls(payload.callConnectionId).update(status="completed")
        return {"status": "completed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── INCOMING TWIML ───────────────────────────────────────────────────────────
@app.post("/incoming")
async def incoming():
    # Kick off a Media Stream into our /stream WS
    twiml = f"""
    <Response>
      <Start>
        <Stream url="wss://{os.getenv('HOSTNAME')}/stream"/>
      </Start>
      <!-- silence until WebSocket wire-up -->
      <Pause length="60"/>
      <Hangup/>
    </Response>
    """
    return Response(content=twiml, media_type="text/xml")

# ── MEDIA STREAM WS ─────────────────────────────────────────────────────────
@app.websocket("/stream")
async def media_stream(ws: WebSocket):
    await ws.accept()
    chat_history = []  # will hold {"role":...,"content":...}
    try:
        while True:
            frame = await ws.receive_text()
            msg = json.loads(frame)

            if msg.get("event") == "media":
                payload_b64 = msg["media"]["payload"]
                audio_bytes = base64.b64decode(payload_b64)
                # TODO: buffer & send to Whisper → transcribe
                # chat_history.append({"role":"user","content": transcript})
                # TODO: call OpenAI ChatCompletion
                # reply = ...
                # TODO: synthesize reply via TTS → reply_bytes
                # reply_b64 = base64.b64encode(reply_bytes).decode()
                # await ws.send_text(json.dumps({
                #   "event":"media",
                #   "media":{"payload": reply_b64}
                # }))
                pass

            if msg.get("event") == "stop":
                break

    except WebSocketDisconnect:
        pass
    finally:
        await ws.close()

# ── OPTIONAL: SERVE UI ───────────────────────────────────────────────────────
app.mount(
    "/", 
    StaticFiles(directory="public_html/assistant", html=True),
    name="static",
)
