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
FROM_NUMBER  = os.getenv("FROM_NUMBER")   # e.g. "+18338790587"
API_BASE     = os.getenv("API_BASE")      # e.g. "https://assistant.emeghara.tech"

if not all([TWILIO_SID, TWILIO_TOKEN, API_KEY, FROM_NUMBER, API_BASE]):
    raise RuntimeError("One or more required env vars missing")

# ── APP & CLIENT SETUP ─────────────────────────────────────────────────────
app = FastAPI()
twilio_client = Client(TWILIO_SID, TWILIO_TOKEN)

# ── CORS ───────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://www.emeghara.tech"],  # or ["*"] for testing
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API-KEY VERIFICATION ───────────────────────────────────────────────────
@app.middleware("http")
async def verify_api_key(request: Request, call_next):
    # allow health and TwiML endpoints without API key
    if request.url.path in ("/health", "/twiml"):
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

# ── STOP (HANG UP) A CALL ─────────────────────────────────────────────────
@app.post("/call/stop")
async def stop_call(payload: CallStopPayload):
    try:
        twilio_client.calls(payload.callConnectionId).update(status="completed")
        return {"status": "completed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── TWIML ENDPOINT ──────────────────────────────────────────────────────────
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

# ── (OPTIONAL) SERVE STATIC UI ──────────────────────────────────────────────
from fastapi.staticfiles import StaticFiles
app.mount(
    "/", 
    StaticFiles(directory="public_html/assistant", html=True),
    name="static",
)
