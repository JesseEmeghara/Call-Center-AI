# app.py

import os
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel, Field
from twilio.rest import Client

# ── CONFIG ────────────────────────────────────────────────────────────────
TWILIO_SID   = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
API_KEY      = os.getenv("API_KEY")
FROM_NUMBER  = os.getenv("FROM_NUMBER")   # "+18338790587"
API_BASE     = os.getenv("API_BASE")      # "https://assistant.emeghara.tech"

if not all([TWILIO_SID, TWILIO_TOKEN, API_KEY, FROM_NUMBER, API_BASE]):
    raise RuntimeError("One or more required env vars missing")

app = FastAPI()
twilio = Client(TWILIO_SID, TWILIO_TOKEN)

# ── CORS (allow both your API hostname and your UI hostname) ──────────────
app.add_middleware(
  CORSMiddleware,
  allow_origins=[
    "https://assistant.emeghara.tech",
    "https://www.emeghara.tech"
  ],
  allow_methods=["*"],
  allow_headers=["*"],
)

# ── API KEY CHECK ──────────────────────────────────────────────────────────
@app.middleware("http")
async def check_key(req: Request, call_next):
    if req.url.path in ("/health", "/twiml"):
        return await call_next(req)
    if req.headers.get("x-api-key") != API_KEY:
        return JSONResponse({"detail": "Invalid API Key"}, status_code=401)
    return await call_next(req)

# ── MODELS ─────────────────────────────────────────────────────────────────
class CallStart(BaseModel):
    to: str
    from_: str | None = Field(None, alias="from")

class CallStop(BaseModel):
    callConnectionId: str

# ── HEALTH ─────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok"}

# ── START CALL ─────────────────────────────────────────────────────────────
@app.post("/call/start")
async def start(payload: CallStart):
    to = payload.to
    frm = payload.from_ or FROM_NUMBER
    try:
        c = twilio.calls.create(to=to, from_=frm, url=f"{API_BASE}/twiml")
        return {"callConnectionId": c.sid}
    except Exception as e:
        raise HTTPException(500, str(e))

# ── STOP CALL ──────────────────────────────────────────────────────────────
@app.post("/call/stop")
async def stop(payload: CallStop):
    try:
        twilio.calls(payload.callConnectionId).update(status="completed")
        return {"status": "completed"}
    except Exception as e:
        raise HTTPException(500, str(e))

# ── TRANSCRIPT STUB ────────────────────────────────────────────────────────
@app.get("/call/transcript")
async def transcript(callConnectionId: str):
    return {"transcript": []}

# ── TWIML ───────────────────────────────────────────────────────────────────
@app.post("/twiml")
async def twiml():
    xml = """
<Response>
  <Say voice="alice">Hello! This is Call-Center AI calling you back.</Say>
  <Pause length="30"/>
  <Hangup/>
</Response>
"""
    return Response(xml, media_type="text/xml")
