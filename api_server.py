import os
from api import app

# --- Script Entrypoint ---
if __name__ == "__main__":
    import uvicorn
    # Default to binding on all interfaces so the API can be reached over LAN/Tailscale
    # when intentionally exposed (for example via a VPS reverse proxy).
    host = os.environ.get("API_HOST", "0.0.0.0")
    port = int(os.environ.get("API_PORT", "9001"))
    reload = os.environ.get("UVICORN_RELOAD", "1") == "1"
    uvicorn.run("api_server:app", host=host, port=port, reload=reload)
