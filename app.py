from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

app = FastAPI()

app.mount(
    "/", 
    StaticFiles(directory="public_html/assistant", html=True),
    name="static",
)

@app.get("/health")
def health():
    return {"status":"ok"}

# your /call/start, /call/stop routes…
