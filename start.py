import os
import uvicorn

port = int(os.environ.get("PORT", 8000))
print(f"[Startup] Starting server on port {port}")
uvicorn.run("web_app:app", host="0.0.0.0", port=port)
