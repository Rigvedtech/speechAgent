import os
from typing import Any, Dict

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

load_dotenv()

app = FastAPI(title="SpeechAgent HTTP API", version="1.0.0")


@app.get("/")
def root() -> Dict[str, str]:
    return {"status": "ok", "service": "speechagent-backend"}


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "healthy"}


@app.post("/api/messages")
async def microsoft_messages(request: Request) -> JSONResponse:
    """
    Minimal Bot Framework-compatible ingress route.
    This confirms the endpoint is reachable from Microsoft and ngrok.
    """
    activity: Dict[str, Any] = await request.json()
    activity_type = str(activity.get("type", "unknown"))
    text = str(activity.get("text", "")).strip()
    conversation_id = str(activity.get("conversation", {}).get("id", ""))

    # Keep response simple and deterministic for endpoint connectivity checks.
    return JSONResponse(
        status_code=200,
        content={
            "received": True,
            "activity_type": activity_type,
            "text": text,
            "conversation_id": conversation_id,
            "note": "Endpoint is live. Integrate Bot Framework adapter for full replies.",
        },
    )


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8000"))
    uvicorn.run("api_server:app", host=host, port=port, reload=False)
