import os
import uvicorn

# Railway injects PORT as an environment variable
# We read it here in Python to avoid shell expansion issues
port = int(os.environ.get("PORT", 8000))
print(f"[Startup] Starting server on port {port}", flush=True)
uvicorn.run("web_app:app", host="0.0.0.0", port=port)
