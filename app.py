from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

app = FastAPI()

# Serve all files under public_html/assistant at the site root
app.mount(
    "/",
    StaticFiles(directory="public_html/assistant", html=True),
    name="static",
)

@app.get("/health")
def health():
    return {"status": "ok"}

# … your existing /call/start, /call/stop, etc. routes go below this line …
