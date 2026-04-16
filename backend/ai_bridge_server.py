from typing import Any, Dict

from fastapi import FastAPI
from pydantic import BaseModel


class FixedLineRequest(BaseModel):
    room_id: str
    call_id: str
    phrase: str


app = FastAPI(title="SpeechAgent AI Bridge", version="1.0.0")


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "healthy", "service": "speechagent-ai-bridge"}


@app.post("/v1/interview/fixed-line")
def fixed_line(req: FixedLineRequest) -> Dict[str, Any]:
    """
    Phase-2 bridge contract:
    - Receives fixed phrase requests from meeting-bot callback on call established.
    - Returns audio_uri for the media runtime when available.
    For now this keeps orchestration and AI service API aligned.
    """
    return {
        "ok": True,
        "room_id": req.room_id,
        "call_id": req.call_id,
        "phrase": req.phrase,
        "audio_uri": None,
        "note": "Wire this endpoint to TTS/media runtime in Phase 2.",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("ai_bridge_server:app", host="0.0.0.0", port=8010, reload=False)
