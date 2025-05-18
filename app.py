# app.py

import os
from fastapi import FastAPI, HTTPException, Request, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel, Field
from twilio.rest import Client
import smtplib
from email.message import EmailMessage

# ── CONFIG ────────────────────────────────────────────────────────────────
TWILIO_SID      = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_TOKEN    = os.getenv("TWILIO_AUTH_TOKEN")
API_KEY         = os.getenv("API_KEY")
FROM_NUMBER     = os.getenv("FROM_NUMBER")   # e.g. "+18338790587"
API_BASE        = os.getenv("API_BASE")      # e.g. "https://assistant.emeghara.tech"

# Hostinger SMTP
SMTP_HOST       = os.getenv("SMTP_HOST")     # smtp.hostinger.com
SMTP_PORT       = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER       = os.getenv("SMTP_USER")     # info@emeghara.tech
SMTP_PASS       = os.getenv("SMTP_PASS")
LEADS_TO        = os.getenv("LEADS_TO")      # comma-separated

if not all([TWILIO_SID, TWILIO_TOKEN, API_KEY, FROM_NUMBER, API_BASE,
            SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, LEADS_TO]):
    raise RuntimeError("One or more required env vars missing")

# ── APP & CLIENT SETUP ─────────────────────────────────────────────────────
app = FastAPI()
twilio_client = Client(TWILIO_SID, TWILIO_TOKEN)

# ── CORS ───────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
      "https://assistant.emeghara.tech",  # your API host
      "https://www.emeghara.tech"         # your UI host
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API-KEY VERIFICATION ────────────────────────────────────────────────────
@app.middleware("http")
async def verify_api_key(request: Request, call_next):
    # allow health, twiml & incoming without x-api-key
    if request.url.path in ("/health", "/twiml", "/incoming"):
        return await call_next(request)

    key = request.headers.get("x-api-key")
    if key != API_KEY:
        return JSONResponse({"detail": "Invalid API Key"}, status_code=401)

    return await call_next(request)

# ── MODELS ─────────────────────────────────────────────────────────────────
class CallStartPayload(BaseModel):
    to: str
    from_: str | None = Field(None, alias="from")

class CallStopPayload(BaseModel):
    callConnectionId: str

# ── HEALTH CHECK ────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok"}

# ── START A CALL ───────────────────────────────────────────────────────────
@app.post("/call/start")
async def start_call(payload: CallStartPayload):
    to_number   = payload.to
    from_number = payload.from_ or FROM_NUMBER

    try:
        call = twilio_client.calls.create(
            to=to_number,
            from_=from_number,
            url=f"{API_BASE}/twiml"
        )
        return {"callConnectionId": call.sid}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── STOP (HANG UP) A CALL ──────────────────────────────────────────────────
@app.post("/call/stop")
async def stop_call(payload: CallStopPayload):
    try:
        twilio_client.calls(payload.callConnectionId).update(status="completed")
        return {"status": "completed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── INCOMING CALL WEBHOOK ──────────────────────────────────────────────────
@app.post("/incoming")
async def incoming_call(
    From: str = Form(...),
    CallSid: str = Form(...),
):
    """
    Handle an inbound call:
    1) Twilio will POST caller → we gather name/email via <Gather> and then
       Twilio will POST digits to /incoming again with the collected data.
    2) Once we have everything, send an email via SMTP.
    """
    # Simplest: just respond with TwiML to gather digits or speak
    # (For brevity, this endpoint needs TwiML logic to collect name/email via keypad or speech.)
    xml = f"""
<Response>
  <Say voice="alice">Thanks for calling! Please leave your name, then press pound.</Say>
  <Record maxLength="20" finishOnKey="#"/>
  <Say voice="alice">Goodbye.</Say>
  <Hangup/>
</Response>
"""
    return Response(content=xml, media_type="text/xml")

# ── TWIML FOR CALLBACK ──────────────────────────────────────────────────────
@app.post("/twiml")
async def twiml():
    xml = """
<Response>
  <Say voice="alice">Hello! This is Call-Center AI calling you back.</Say>
  <Pause length="30"/>
  <Hangup/>
</Response>
"""
    return Response(content=xml, media_type="text/xml")
