from fastapi import FastAPI

app = FastAPI()

@app.get("/health")
def health():
    return {"status": "ok"}

# … your /call/start, /call/stop, /call/transcript, etc. routes …
