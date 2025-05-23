import os
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel, Field
from twilio.rest import Client

# ── CONFIG ────────────────────────────────────────────────────────────────
TWILIO_SID   = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
API_KEY      = os.getenv("API_KEY")
FROM_NUMBER  = os.getenv("FROM_NUMBER")
API_BASE     = os.getenv("API_BASE")
HOSTNAME     = os.getenv("HOSTNAME")

if not all([TWILIO_SID, TWILIO_TOKEN, API_KEY, FROM_NUMBER, API_BASE, HOSTNAME]):
    raise RuntimeError("One or more required env vars missing")

# ── DATABASE INIT ──────────────────────────────────────────────────────────
from db import init_db, save_lead
init_db()   # will read MYSQL_URL from env and create tables

# ── APP & CLIENT SETUP ─────────────────────────────────────────────────────
app    = FastAPI()
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
    # 1) Let CORS preflight through
    if request.method == "OPTIONS":
        return await call_next(request)

    # 2) Skip auth on public/Twilio callbacks
    if request.url.path in ("/health", "/incoming", "/twiml", "/stream"):
        return await call_next(request)

    # 3) Otherwise require x-api-key
    if request.headers.get("x-api-key") != API_KEY:
        return JSONResponse({"detail": "Invalid API Key"}, status_code=401)

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
    return {"status": "ok"}

# ── START A CALL ───────────────────────────────────────────────────────────
@app.post("/call/start")
async def start_call(payload: StartPayload):
    to  = payload.to
    frm = payload.from_ or FROM_NUMBER
    try:
        call = twilio.calls.create(
            to=to,
            from_=frm,
            url=f"{API_BASE}/incoming"
        )
        return {"callConnectionId": call.sid}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── STOP (HANG UP) A CALL ─────────────────────────────────────────────────
@app.post("/call/stop")
async def stop_call(payload: StopPayload):
    try:
        twilio.calls(payload.callConnectionId).update(status="completed")
        return {"status": "completed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── TWIML FOR INCOMING (OUTBOUND) ───────────────────────────────────────────
@app.post("/incoming")
async def incoming():
    twiml = f"""
<Response>
  <Start>
    <Stream url="wss://{HOSTNAME}/stream"/>
  </Start>
  <Pause length="60"/>
  <Hangup/>
</Response>"""
    return Response(content=twiml, media_type="text/xml")

# ── STREAMING WS FOR TWILIO MEDIA ──────────────────────────────────────────
@app.websocket("/stream")
async def stream(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            frame = await ws.receive_text()
            # echo‐back or process Twilio media JSON here…
            await ws.send_text(frame)
    except WebSocketDisconnect:
        pass
    finally:
        await ws.close()
