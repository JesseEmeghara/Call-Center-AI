# app.py

import os
from fastapi import FastAPI, HTTPException, Request, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Gather
import smtplib
from email.mime.text import MIMEText

# ── CONFIG ────────────────────────────────────────────────────────────────
TWILIO_SID      = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_TOKEN    = os.getenv("TWILIO_AUTH_TOKEN")
API_KEY         = os.getenv("API_KEY")
FROM_NUMBER     = os.getenv("FROM_NUMBER")     # e.g. "+18338790587"
API_BASE        = os.getenv("API_BASE")        # e.g. "https://assistant.emeghara.tech"

SMTP_HOST       = os.getenv("SMTP_HOST")       # smtp.hostinger.com
SMTP_PORT       = int(os.getenv("SMTP_PORT", 587))
SMTP_USER       = os.getenv("SMTP_USER")       # info@emeghara.tech
SMTP_PASS       = os.getenv("SMTP_PASS")
LEADS_TO        = os.getenv("LEADS_TO")        # comma-separated emails

if not all([TWILIO_SID, TWILIO_TOKEN, API_KEY, FROM_NUMBER, API_BASE,
            SMTP_HOST, SMTP_USER, SMTP_PASS, LEADS_TO]):
    raise RuntimeError("One or more required env vars missing")

# ── APP & CLIENT SETUP ─────────────────────────────────────────────────────
app = FastAPI()
twilio_client = Client(TWILIO_SID, TWILIO_TOKEN)

# ── CORS ───────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://assistant.emeghara.tech",
        "https://www.emeghara.tech"
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API-KEY VERIFICATION ───────────────────────────────────────────────────
@app.middleware("http")
async def verify_api_key(request: Request, call_next):
    # allow these public endpoints
    if request.url.path in ("/health", "/incoming", "/handle-lead"):
        return await call_next(request)

    key = request.headers.get("x-api-key")
    if key != API_KEY:
        return JSONResponse({"detail": "Invalid API Key"}, status_code=401)

    return await call_next(request)

# ── STATIC UI (OPTIONAL) ──────────────────────────────────────────────────
app.mount(
    "/",
    StaticFiles(directory="public_html/assistant", html=True),
    name="static",
)

# ── HEALTH CHECK ───────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok"}

# ── OUTBOUND CALLS FOR “CALL ME” BUTTON ────────────────────────────────────
from pydantic import BaseModel, Field

class CallStartPayload(BaseModel):
    to: str
    from_: str | None = Field(None, alias="from")

class CallStopPayload(BaseModel):
    callConnectionId: str

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

@app.post("/call/stop")
async def stop_call(payload: CallStopPayload):
    try:
        twilio_client.calls(payload.callConnectionId).update(status="completed")
        return {"status": "completed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── INCOMING WEBHOOK: GATHER THE LEAD’S NAME ───────────────────────────────
@app.post("/incoming")
async def incoming():
    # ask caller to say their name, then press #
    resp = VoiceResponse()
    gather = Gather(input="speech", action="/handle-lead", method="POST", finishOnKey="#")
    gather.say("Hello! Please say your name after the tone, then press the pound key.")
    resp.append(gather)
    # if they never respond, hang up
    resp.say("We didn't receive any input. Goodbye.")
    resp.hangup()
    return Response(content=str(resp), media_type="text/xml")

# ── HANDLE-LEAD: SEND EMAIL & HANG UP ──────────────────────────────────────
@app.post("/handle-lead")
async def handle_lead(speechResult: str = Form(...), From: str = Form(...)):
    # speechResult → the name they spoke
    # From → the caller’s phone number
    try:
        msg = MIMEText(f"""
        <p><strong>Name:</strong> {speechResult}</p>
        <p><strong>Phone:</strong> {From}</p>
        """, "html")
        msg["Subject"] = "New Lead from Call-Center AI"
        msg["From"]    = SMTP_USER
        msg["To"]      = LEADS_TO

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
            smtp.starttls()
            smtp.login(SMTP_USER, SMTP_PASS)
            smtp.sendmail(SMTP_USER, LEADS_TO.split(","), msg.as_string())

    except Exception as e:
        # on error, tell them and hang up
        resp = VoiceResponse()
        resp.say("Sorry, we encountered an error saving your lead. Goodbye.")
        resp.hangup()
        return Response(content=str(resp), media_type="text/xml")

    # success: thank them
    resp = VoiceResponse()
    resp.say("Thank you! Your information has been received. Goodbye.")
    resp.hangup()
    return Response(content=str(resp), media_type="text/xml")
