# app.py

import os
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel, Field
from twilio.rest import Client

# ── CONFIG ────────────────────────────────────────────────────────────────
TWILIO_SID      = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_TOKEN    = os.getenv("TWILIO_AUTH_TOKEN")
API_KEY         = os.getenv("API_KEY")
FROM_NUMBER     = os.getenv("FROM_NUMBER")   # your Twilio number
API_BASE        = os.getenv("API_BASE")      # e.g. https://assistant.emeghara.tech

# sanity check
if not all([TWILIO_SID, TWILIO_TOKEN, API_KEY, FROM_NUMBER, API_BASE]):
    raise RuntimeError("Missing one or more required env vars!")

# ── APP & TWILIO CLIENT ────────────────────────────────────────────────────
app = FastAPI()
twilio = Client(TWILIO_SID, TWILIO_TOKEN)

# ── CORS ───────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
      "https://www.emeghara.tech",
      "https://assistant.emeghara.tech",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API-KEY VERIFICATION ───────────────────────────────────────────────────
@app.middleware("http")
async def verify_api_key(request: Request, call_next):
    # Open endpoints:
    if request.url.path in ("/health", "/twiml", "/incoming", "/stream"):
        return await call_next(request)
    # Everything else needs x-api-key
    if request.headers.get("x-api-key") != API_KEY:
        return JSONResponse({"detail":"Invalid API Key"}, status_code=401)
    return await call_next(request)

# ── MODELS ─────────────────────────────────────────────────────────────────
class StartPayload(BaseModel):
    to: str
    from_: str | None = Field(None, alias="from")

class StopPayload(BaseModel):
    callConnectionId: str

# ── HEALTH CHECK ────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status":"ok"}

# ── START CALL ─────────────────────────────────────────────────────────────
@app.post("/call/start")
async def start_call(payload: StartPayload):
    to = payload.to
    frm = payload.from_ or FROM_NUMBER
    try:
        call = twilio.calls.create(
            to=to,
            from_=frm,
            url=f"{API_BASE}/incoming"
        )
        return {"callConnectionId": call.sid}
    except Exception as e:
        raise HTTPException(500, str(e))

# ── STOP CALL ──────────────────────────────────────────────────────────────
@app.post("/call/stop")
async def stop_call(payload: StopPayload):
    try:
        twilio.calls(payload.callConnectionId).update(status="completed")
        return {"status":"completed"}
    except Exception as e:
        raise HTTPException(500, str(e))

# ── INCOMING TWIML ──────────────────────────────────────────────────────────
@app.post("/incoming")
async def incoming():
    twiml = f"""
<Response>
  <Start><Stream url="wss://{os.getenv('HOSTNAME')}/stream"/></Start>
  <Pause length="60"/>
  <Hangup/>
</Response>"""
    return Response(content=twiml, media_type="text/xml")

# ── WEBSOCKET MEDIA STREAM ─────────────────────────────────────────────────
@app.websocket("/stream")
async def stream(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            msg = await ws.receive_text()   # you'll get JSON-encoded media frames here
            # TODO: decode → Whisper → GPT → TTS → ws.send_text(...)
    except WebSocketDisconnect:
        pass
    finally:
        await ws.close()
