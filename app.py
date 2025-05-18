# app.py

import os
from fastapi import FastAPI, HTTPException, Request, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel, Field
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Gather
from sqlalchemy import create_engine, Table, Column, String, DateTime, MetaData
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import smtplib
from email.message import EmailMessage

# ── CONFIG ────────────────────────────────────────────────────────────────
TWILIO_SID   = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
API_KEY      = os.getenv("API_KEY")
FROM_NUMBER  = os.getenv("FROM_NUMBER")    # e.g. "+18338790587"
API_BASE     = os.getenv("API_BASE")       # e.g. "https://assistant.emeghara.tech"
DB_URL       = os.getenv("DATABASE_URL")   # Your Railway MySQL URL

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
LEADS_TO   = os.getenv("LEADS_TO", "").split(",")

# check all
if not all([TWILIO_SID, TWILIO_TOKEN, API_KEY, FROM_NUMBER, API_BASE, DB_URL]):
    raise RuntimeError("Missing required env vars")

# ── APP & CLIENT ──────────────────────────────────────────────────────────
app = FastAPI()
twilio_client = Client(TWILIO_SID, TWILIO_TOKEN)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://www.emeghara.tech"],  # or ["*"] for testing
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def verify_api_key(request: Request, call_next):
    if request.url.path in ("/health", "/twiml", "/incoming", "/incoming/gather"):
        return await call_next(request)
    if request.headers.get("x-api-key") != API_KEY:
        return JSONResponse({"detail": "Invalid API Key"}, status_code=401)
    return await call_next(request)

# ── DB SETUP ──────────────────────────────────────────────────────────────
engine = create_engine(DB_URL)
Session = sessionmaker(bind=engine)
meta = MetaData()
leads = Table(
    "leads", meta,
    Column("call_sid", String(64), primary_key=True),
    Column("name", String(200)),
    Column("email", String(200)),
    Column("phone", String(50)),
    Column("created_at", DateTime, default=datetime.utcnow)
)
meta.create_all(engine)

def save_lead_to_db(call_sid, name, email, phone):
    sess = Session()
    sess.execute(
        leads.insert().values(
            call_sid=call_sid,
            name=name,
            email=email,
            phone=phone
        )
    )
    sess.commit()
    sess.close()

def send_lead_email(name, email, phone):
    msg = EmailMessage()
    msg["Subject"] = "📞 New Call-Center AI Lead"
    msg["From"]    = SMTP_USER
    msg["To"]      = ", ".join(LEADS_TO)
    msg.set_content(f"Name: {name}\nEmail: {email}\nPhone: {phone}\n")

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
        s.starttls()
        s.login(SMTP_USER, SMTP_PASS)
        s.send_message(msg)

# ── HEALTH & OUTBOUND CALLS ────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok"}

class CallStartPayload(BaseModel):
    to: str
    from_: str | None = Field(None, alias="from")

class CallStopPayload(BaseModel):
    callConnectionId: str

@app.post("/call/start")
async def start_call(payload: CallStartPayload):
    call = twilio_client.calls.create(
        to=payload.to,
        from_=(payload.from_ or FROM_NUMBER),
        url=f"{API_BASE}/twiml"
    )
    return {"callConnectionId": call.sid}

@app.post("/call/stop")
async def stop_call(payload: CallStopPayload):
    twilio_client.calls(payload.callConnectionId).update(status="completed")
    return {"status": "completed"}

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

# ── INBOUND LEAD FUNNEL ────────────────────────────────────────────────────
# 1) Initial greeting + ask for name
@app.post("/incoming")
async def inbound_call(From: str = Form(...), CallSid: str = Form(...)):
    vr = VoiceResponse()
    gather = Gather(
        action=f"/incoming/gather?step=name&CallSid={CallSid}",
        input="speech",
        timeout=5
    )
    gather.say("Hello! Welcome to Call Center A I. Please say your full name now.")
    vr.append(gather)
    vr.redirect(f"/incoming/gather?step=name&CallSid={CallSid}")
    return Response(content=str(vr), media_type="text/xml")

# 2) Handle each gather step
#    (we’ll keep partial answers in a simple in-memory dict for this call)
_call_cache: dict[str, dict] = {}

@app.post("/incoming/gather")
async def gather_step(
    step: str,
    CallSid: str,
    SpeechResult: str = Form(None)
):
    data = _call_cache.setdefault(CallSid, {})
    if SpeechResult:
        data[step] = SpeechResult

    vr = VoiceResponse()
    next_map = {"name": "email", "email": "phone", "phone": "done"}
    next_step = next_map[step]

    if next_step != "done":
        prompts = {
            "email": "Please say your email address after the tone.",
            "phone": "Finally, please say your phone number digits."
        }
        gather = Gather(
            action=f"/incoming/gather?step={next_step}&CallSid={CallSid}",
            input="speech",
            timeout=5
        )
        gather.say(prompts[next_step])
        vr.append(gather)
        vr.redirect(f"/incoming/gather?step={next_step}&CallSid={CallSid}")
    else:
        # Save + email
        save_lead_to_db(CallSid, data["name"], data["email"], data["phone"])
        send_lead_email(data["name"], data["email"], data["phone"])
        vr.say("Thank you; we have your info. Goodbye.")
        vr.hangup()
        _call_cache.pop(CallSid, None)

    return Response(content=str(vr), media_type="text/xml")
