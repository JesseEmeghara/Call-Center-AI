# app.py

import os
from typing import List
from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel, Field
from twilio.rest import Client

# ── CONFIG ────────────────────────────────────────────────────────────────
TWILIO_SID      = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_TOKEN    = os.getenv("TWILIO_AUTH_TOKEN")
API_KEY         = os.getenv("API_KEY")
FROM_NUMBER     = os.getenv("FROM_NUMBER")   # your Twilio number, e.g. "+18338790587"
API_BASE        = os.getenv("API_BASE")      # your Railway URL, e.g. "https://assistant.emeghara.tech"

if not all([TWILIO_SID, TWILIO_TOKEN, API_KEY, FROM_NUMBER, API_BASE]):
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

# ── IN-MEMORY TRANSCRIPT STORE (swap this for your Hostinger DB) ──────────
# key: call SID → list of transcript lines
TRANSCRIPT_STORE: dict[str, List[str]] = {}

# ── API-KEY VERIFICATION ───────────────────────────────────────────────────
@app.middleware("http")
async def verify_api_key(request: Request, call_next):
    # Skip auth on health, TwiML, and incoming webhook
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
        # initialize transcript
        TRANSCRIPT_STORE[call.sid] = []
        return {"callConnectionId": call.sid}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── STOP (HANG UP) A CALL ─────────────────────────────────────────────────
@app.post("/call/stop")
async def stop_call(payload: CallStopPayload):
    try:
        twilio_client.calls(payload.callConnectionId).update(status="completed")
        return {"status": "completed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── POLLING: GET TRANSCRIPT ─────────────────────────────────────────────────
@app.get("/call/transcript")
async def get_transcript(callConnectionId: str = Query(...)):
    """
    Returns the list of transcript lines for the given call SID.
    """
    return {"transcript": TRANSCRIPT_STORE.get(callConnectionId, [])}

# ── TWIML ENDPOINT ──────────────────────────────────────────────────────────
@app.post("/twiml")
async def twiml():
    # You can tune the <Say> text here, and pick a richer voice:
    # Twilio supports e.g. voice="Polly.Matthew-Neural" (US English neural)
    xml = """
<Response>
  <Say voice="Polly.Matthew-Neural">
    Hello! Thank you for calling our AI call center.
    To capture your details, please say your full name after the tone.
  </Say>
  <Record
    playBeep="true"
    maxLength="10"
    trim="trim-silence"
    action="/incoming"
    method="POST"
  />
  <Say voice="Polly.Matthew-Neural">
    We did not receive a recording. Goodbye.
  </Say>
  <Hangup/>
</Response>
"""
    return Response(content=xml, media_type="text/xml")

# ── INCOMING RECORDING CALLBACK ─────────────────────────────────────────────
@app.post("/incoming")
async def incoming(request: Request):
    # Twilio will POST form data including RecordingUrl, RecordingSid, etc.
    form = await request.form()
    sid = form.get("CallSid")
    recording_url = form.get("RecordingUrl")
    # Append a simple marker to your transcript store
    if sid in TRANSCRIPT_STORE:
        TRANSCRIPT_STORE[sid].append(f"[Recording] {recording_url}")
    return Response(status_code=204)

