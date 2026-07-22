"""
REST API Server for Recall.ai Bot Control
Use with Postman to join/leave meetings.
"""

import os
import asyncio
import logging
from pathlib import Path
from typing import Optional, List, Literal

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, File, UploadFile, Form, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator
from dotenv import load_dotenv
import uvicorn
import requests
from uuid import UUID
from sqlalchemy.orm import Session

from recall_bot_service import (
    RecallBotService,
    BotConfig,
    normalize_meeting_url,
    resolve_meeting_url_for_recall,
    bot_phase_message,
)
from session_manager import SessionManager
from audio_receiver import AudioReceiver
from transcript_log import log_transcript
from report_html import render_not_completed_html, render_report_html
from report_service import resolve_interview_report
from report_store import list_reports, load_report
from feedback_store import feedback_exists, load_feedback, save_feedback
from n8n_extraction import extract_cv_file, extract_jd_file, generate_questions
from language_profiles import resolve_language_mode, get_ui_strings
import config as app_config
import ws_hub
from auth.deps import get_optional_db, get_optional_user
from db.models import User
from extraction_store import (
    save_cv_extraction,
    save_jd_extraction,
    save_question_generation,
)
from routers.interviews import router as interviews_router
from routers.documents import router as documents_router
from routers.ats import router as ats_router
import interview_persist
import document_store
load_dotenv()

# Setup logging (console + full file under backend/logs/)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
from file_logging import setup_file_logging

_run_log = setup_file_logging(prefix="api_server")
logger = logging.getLogger(__name__)
logger.info("Server log file: %s", _run_log)

# Initialize FastAPI
app = FastAPI(title="Recall.ai Bot API", version="1.0.0")

_cors_origins = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173",
).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins if o.strip()],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

# Phase 0–1: auth + candidates + job postings (requires DATABASE_URL)
from auth.routes import router as auth_router
from auth.routes import users_router
from routers.candidates import router as candidates_router
from routers.job_postings import router as job_postings_router
from routers.extractions import router as extractions_router

app.include_router(auth_router)
app.include_router(users_router)
app.include_router(candidates_router)
app.include_router(job_postings_router)
app.include_router(extractions_router)
app.include_router(interviews_router)
app.include_router(documents_router)
app.include_router(ats_router)

# Serve audio-worklet-processor.js and other static assets
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Initialize services and env config (before startup handlers)
recall_service = RecallBotService()
session_manager = SessionManager(recall_service)

BOT_NAME = os.getenv("BOT_NAME", "Prabhat")
LOBBY_TIMEOUT_MINUTES = int(os.getenv("LOBBY_TIMEOUT_MINUTES", "15"))
PUBLIC_WEBSOCKET_URL = os.getenv("PUBLIC_WEBSOCKET_URL")
WEBSOCKET_PORT = int(os.getenv("WEBSOCKET_PORT", "8765"))

# TTS Configuration
TTS_RATE = os.getenv("TTS_RATE", "+35%")
TTS_REDUCE_PAUSES = os.getenv("TTS_REDUCE_PAUSES", "true").lower() == "true"


@app.on_event("startup")
async def _capture_main_loop():
    """
    Store the running event loop in config.main_event_loop so TTS worker threads
    can schedule broadcasts via asyncio.run_coroutine_threadsafe.

    Stored in config (not here) to avoid the Python 'double module' problem:
    when api_server.py is run as __main__, any module that later does
    `from api_server import ...` gets a SECOND copy of this module with its own
    globals — meaning a module-level _main_loop here would never be visible to
    importers.  config.py is always imported under the same key in sys.modules.
    """
    import config as _cfg
    from db.session import init_db
    from auth.security import validate_jwt_config

    _cfg.main_event_loop = asyncio.get_running_loop()
    logger.info("[startup] Main event loop captured in config.main_event_loop")
    validate_jwt_config()
    init_db()
    asyncio.create_task(_lobby_janitor_loop())


async def _lobby_janitor_loop():
    """Periodically remove bots abandoned in the lobby before interview start."""
    interval_sec = 60
    max_age_sec = LOBBY_TIMEOUT_MINUTES * 60
    logger.info(
        f"[janitor] Lobby cleanup every {interval_sec}s "
        f"(timeout={LOBBY_TIMEOUT_MINUTES} min)"
    )
    while True:
        await asyncio.sleep(interval_sec)
        try:
            session_manager.cleanup_stale_lobby_bots(max_age_sec)
        except Exception as e:
            logger.error(f"[janitor] Lobby cleanup failed: {e}")


@app.on_event("shutdown")
async def _shutdown_sessions():
    logger.info("[shutdown] Cleaning up active bot sessions")
    session_manager.shutdown_all()

# All WebSocket hub state and broadcast helpers live in ws_hub.py
# (avoids the Python __main__ double-module problem — see ws_hub.py for details)

# Request/Response Models
class QuestionBankItem(BaseModel):
    id: str
    difficulty: str
    source: str
    question: str

    @field_validator("id", mode="before")
    @classmethod
    def coerce_id_to_str(cls, v):
        if v is None:
            raise ValueError("id is required")
        return str(v).strip()


class JoinMeetingRequest(BaseModel):
    meeting_url: str
    bot_name: Optional[str] = None
    candidate_name: Optional[str] = None
    jdText: Optional[str] = None
    cvText: Optional[str] = None
    questions: Optional[List[QuestionBankItem]] = None
    language_mode: Optional[Literal["english", "hinglish"]] = None
    greeting_message: Optional[str] = None
    replace_existing: bool = False
    # Persistence (auth required when set)
    interview_id: Optional[UUID] = None
    candidate_id: Optional[UUID] = None
    job_posting_id: Optional[UUID] = None
    job_title: Optional[str] = None
    document_extraction_id: Optional[UUID] = None


class PlannedQuestionSummary(BaseModel):
    slot: int
    id: str
    difficulty: str
    source: str
    question: str
    spoken_question: str


class JoinMeetingResponse(BaseModel):
    success: bool
    bot_id: str
    bot_name: str
    meeting_url: str
    status: str
    message: Optional[str] = None
    interview_configured: bool = False
    language_mode: Optional[str] = None
    localization_status: Optional[str] = None
    questions_planned: Optional[int] = None
    planned_questions: Optional[List[PlannedQuestionSummary]] = None
    interview_id: Optional[UUID] = None


class LeaveResponse(BaseModel):
    success: bool
    bot_id: str
    message: str


class StatusResponse(BaseModel):
    bot_id: str
    status: str
    meeting_url: Optional[str]
    is_active: bool
    recall_phase: Optional[str] = None
    interview_configured: bool = False
    interview_started: bool = False
    localization_status: Optional[str] = None
    ready_to_start: bool = False
    questions_planned: Optional[int] = None
    candidate_name: Optional[str] = None
    language_mode: Optional[str] = None
    planned_questions: Optional[List[PlannedQuestionSummary]] = None
    current_question_slot: Optional[int] = None
    questions_scored: Optional[int] = None
    interview_phase: Optional[str] = None
    interview_ended: Optional[bool] = None


class SubmitFeedbackRequest(BaseModel):
    overall_rating: int
    clarity_rating: int
    tech_issues: Literal["none", "minor", "major"]
    improve_text: str
    would_repeat: Optional[Literal["yes", "maybe", "no"]] = None

    @field_validator("overall_rating", "clarity_rating")
    @classmethod
    def rating_range(cls, v: int) -> int:
        if not 1 <= v <= 5:
            raise ValueError("rating must be between 1 and 5")
        return v

    @field_validator("improve_text")
    @classmethod
    def improve_nonempty(cls, v: str) -> str:
        text = (v or "").strip()
        if not text:
            raise ValueError("improve_text is required")
        if len(text) > 500:
            raise ValueError("improve_text must be at most 500 characters")
        return text


def _feedback_bot_context(bot_id: str) -> dict:
    """Resolve interview identity for feedback; 404 if bot unknown."""
    session = session_manager.get_session(bot_id)
    report = None
    try:
        from interview_persist import load_report_by_bot_id

        report = load_report_by_bot_id(bot_id)
    except Exception:
        report = None
    if not report:
        report = load_report(bot_id)
    if not session and not report:
        # Last chance: interview session exists in DB even without a report yet
        try:
            from interview_persist import find_interview_id_by_bot

            if not find_interview_id_by_bot(bot_id):
                raise HTTPException(status_code=404, detail="Interview not found")
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=404, detail="Interview not found")

    candidate_name = None
    if session:
        if session.state.interview_orchestrator:
            candidate_name = session.state.interview_orchestrator.candidate_name
        elif session.scheduled_candidate_name:
            candidate_name = session.scheduled_candidate_name
    if not candidate_name and report:
        candidate_name = report.get("candidate_name")
    return {"bot_id": bot_id, "candidate_name": candidate_name}


# ─── Output Media Webpage ────────────────────────────────────────────────────

@app.get("/voice-agent", response_class=HTMLResponse)
async def voice_agent_page():
    """
    Recall.ai loads this URL inside its headless Chromium bot.
    Pass ?bot_id=<uuid>&name=<display_name> in the URL.
    """
    html_path = STATIC_DIR / "output-media.html"
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


# ─── Audio-stream WebSocket endpoint ────────────────────────────────────────

@app.websocket("/ws/audio-stream/{page_session_id}")
async def audio_stream_ws(websocket: WebSocket, page_session_id: str):
    """
    Recall.ai's output-media page connects here to receive PCM audio.
    The path param is the page_session_id embedded in the page URL at bot creation.

    Protocol:
      Server → Client (binary)  : raw Int16 PCM, 24 kHz mono (Sarvam bulbul:v3)
      Server → Client (text)    : JSON control {type: "start_speaking" | "stop_speaking" | "ping"}
      Client → Server (text)    : JSON {type: "pong"} heartbeat reply
    """
    await websocket.accept()

    # Resolve page_session_id → bot_id via ws_hub (shared module, no double-copy issue)
    bot_id = ws_hub.resolve_bot_id(page_session_id)
    logger.info(f"[audio-stream] Page connected — session={page_session_id[:8]}… bot={bot_id[:8]}…")

    await ws_hub.add_client(bot_id, websocket)

    import json as _json
    try:
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=25)
                try:
                    msg = _json.loads(data)
                    if msg.get('type') == 'playback_done':
                        # Browser ring buffer drained — audio has finished playing.
                        session = session_manager.get_session(bot_id)
                        if session:
                            session_manager.on_playback_done(session)
                    # pong and unknown messages are silently ignored
                except Exception:
                    pass
            except asyncio.TimeoutError:
                await websocket.send_text(_json.dumps({"type": "ping"}))
    except WebSocketDisconnect:
        logger.info(f"[audio-stream] Page disconnected — session={page_session_id[:8]}…")
    except Exception as e:
        logger.warning(f"[audio-stream] Error — session={page_session_id[:8]}…: {e}")
    finally:
        await ws_hub.remove_client(bot_id, websocket)
        logger.info(f"[audio-stream] Cleaned up — session={page_session_id[:8]}…")


# ─── API Endpoints ────────────────────────────────────────────────────────────

def _interview_config_provided(request: JoinMeetingRequest) -> bool:
    return bool(
        request.candidate_name
        or request.jdText
        or request.cvText
        or request.questions
        or request.language_mode
    )


def _validate_interview_config(request: JoinMeetingRequest) -> tuple[str, str, str, list, str]:
    """Validate full interview payload on join. Returns (candidate, jd, cv, bank, language)."""
    candidate_name = (request.candidate_name or "").strip()
    jd_text = (request.jdText or "").strip()
    cv_text = (request.cvText or "").strip()
    if not candidate_name:
        raise HTTPException(status_code=400, detail="candidate_name is required")
    if not jd_text:
        raise HTTPException(status_code=400, detail="jdText is required")
    if not cv_text:
        raise HTTPException(status_code=400, detail="cvText is required")
    if not request.questions:
        raise HTTPException(status_code=400, detail="questions list cannot be empty")
    try:
        resolved_language = resolve_language_mode(request.language_mode)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    from interview_engine import parse_bank_questions

    try:
        bank = parse_bank_questions([q.model_dump() for q in request.questions])
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    return candidate_name, jd_text, cv_text, bank, resolved_language


async def _attach_interview_to_session(
    session,
    bot_id: str,
    candidate_name: str,
    jd_text: str,
    cv_text: str,
    bank,
    resolved_language: str,
    greeting_message: Optional[str],
    *,
    planned=None,
    db_interview_id: Optional[str] = None,
) -> None:
    from interview_engine import InterviewOrchestrator

    orchestrator = InterviewOrchestrator.create(
        bot_id=bot_id,
        candidate_name=candidate_name,
        jd_text=jd_text,
        cv_text=cv_text,
        bank=bank,
        language_mode=resolved_language,
        planned=planned,
        db_interview_id=db_interview_id,
    )
    session_manager.configure_interview_session(
        session, orchestrator, resolved_language, greeting_message
    )
    session.db_interview_id = db_interview_id
    await session_manager.apply_language_profile(session, resolved_language)
    session_manager.start_question_localization(session)


@app.post("/api/join", response_model=JoinMeetingResponse)
async def join_meeting(
    request: JoinMeetingRequest,
    user: Optional[User] = Depends(get_optional_user),
    db: Optional[Session] = Depends(get_optional_db),
):
    """
    Join a Teams/Zoom/Google Meet meeting.
    One bot per meeting URL — duplicate joins return 409 with a clear message.
    Pass interview_id to send a scheduled interview to lobby, or candidate_id +
    job_posting_id to persist a new interview row when authenticated.
    """
    bot_name = request.bot_name or BOT_NAME
    raw_meeting_url = request.meeting_url.strip()
    if not raw_meeting_url:
        raise HTTPException(status_code=400, detail="meeting_url is required")

    planned_from_db = None
    db_interview_id: Optional[str] = None
    persist_candidate_id = request.candidate_id
    persist_job_id = request.job_posting_id
    persist_job_title = request.job_title
    persist_extraction_id = request.document_extraction_id

    if request.interview_id is not None:
        if user is None or db is None:
            raise HTTPException(
                status_code=401,
                detail="Authentication required to send a scheduled interview to lobby",
            )
        payload = interview_persist.load_join_payload(db, user, request.interview_id)
        if payload["interview"].bot_id is not None and not request.replace_existing:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "This interview already has a bot in lobby.",
                    "bot_id": str(payload["interview"].bot_id),
                    "interview_id": str(request.interview_id),
                },
            )
        raw_meeting_url = payload["meeting_url"]
        bot_name = payload["bot_name"] or bot_name
        request.candidate_name = payload["candidate_name"]
        request.jdText = payload["jdText"]
        request.cvText = payload["cvText"]
        request.questions = [
            QuestionBankItem(**q) for q in payload["questions"]
        ]
        request.language_mode = payload["language_mode"]
        if payload.get("greeting_message") and not request.greeting_message:
            request.greeting_message = payload["greeting_message"]
        planned_from_db = payload["planned_bank"]
        db_interview_id = str(request.interview_id)
        persist_candidate_id = payload["candidate_id"]
        persist_job_id = payload["job_posting_id"]
        persist_job_title = payload["job_title"]
        persist_extraction_id = payload.get("document_extraction_id")
    elif request.candidate_id or request.job_posting_id:
        if user is None or db is None:
            raise HTTPException(
                status_code=401,
                detail="Authentication required to persist interview entities",
            )
        if not request.candidate_id or not request.job_posting_id:
            raise HTTPException(
                status_code=400,
                detail="Both candidate_id and job_posting_id are required to persist",
            )

    try:
        meeting_url = resolve_meeting_url_for_recall(raw_meeting_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if meeting_url != raw_meeting_url:
        logger.info(
            "Resolved meeting URL: %s... -> %s...",
            raw_meeting_url[:55],
            meeting_url[:55],
        )

    meeting_key = normalize_meeting_url(meeting_url)

    # ── Phase 1: check local map under lock ───────────────────────────────
    existing_bot_id: Optional[str] = None
    with session_manager.sessions_lock:
        existing = session_manager.meeting_to_bot.get(meeting_key)
        if existing == "CREATING":
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "A bot is already being created for this meeting. Please wait.",
                    "phase": "joining",
                },
            )
        if existing:
            existing_bot_id = existing

    # ── Phase 2: verify existing bot with Recall (outside lock) ───────────
    if existing_bot_id:
        try:
            phase, status_code = recall_service.get_bot_phase(existing_bot_id)
        except Exception as e:
            logger.warning(f"Could not verify existing bot {existing_bot_id[:8]}: {e}")
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "Another bot is already registered for this meeting.",
                    "bot_id": existing_bot_id,
                    "phase": "unknown",
                },
            )

        if phase == "ended":
            session_manager.cleanup_stale_bot(existing_bot_id, meeting_url)
        elif request.replace_existing:
            logger.info(
                f"Replacing existing bot {existing_bot_id[:8]} for meeting "
                f"(phase={phase})"
            )
            session_manager.end_session(existing_bot_id)
        else:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": bot_phase_message(phase),
                    "bot_id": existing_bot_id,
                    "phase": phase,
                    "recall_status": status_code,
                },
            )

    # ── Phase 3: atomically reserve slot (double-check after stale cleanup) ─
    with session_manager.sessions_lock:
        existing = session_manager.meeting_to_bot.get(meeting_key)
        if existing == "CREATING":
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "A bot is already being created for this meeting. Please wait.",
                    "phase": "joining",
                },
            )
        if existing:
            # Another request won the race after our stale cleanup
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "Another bot is already active for this meeting.",
                    "bot_id": existing,
                    "phase": "unknown",
                },
            )
        session_manager.meeting_to_bot[meeting_key] = "CREATING"

    # ── Phase 4: create bot (Recall API — slow, outside lock) ───────────────
    try:
        import uuid as _uuid

        logger.info(f"Creating bot '{bot_name}' for meeting: {meeting_url[:50]}...")

        public_base = os.getenv("PUBLIC_NGROK_URL", "").rstrip("/")
        page_session_id = str(_uuid.uuid4())
        output_media_page_url: Optional[str] = None

        if app_config.RECALL_USE_OUTPUT_MEDIA and public_base:
            import urllib.parse
            output_media_page_url = (
                f"{public_base}/voice-agent"
                f"?page_session_id={page_session_id}"
                f"&name={urllib.parse.quote(bot_name)}"
            )
            logger.info(f"Output Media page URL: {output_media_page_url}")
        elif app_config.RECALL_USE_OUTPUT_MEDIA:
            logger.warning(
                "RECALL_USE_OUTPUT_MEDIA=true but PUBLIC_NGROK_URL is not set — "
                "falling back to file-upload. Add PUBLIC_NGROK_URL to .env."
            )

        config = BotConfig(
            meeting_url=meeting_url,
            bot_name=bot_name,
            websocket_url=PUBLIC_WEBSOCKET_URL,
            use_output_media=app_config.RECALL_USE_OUTPUT_MEDIA,
            output_media_url=output_media_page_url,
            enable_camera_integrity=bool(app_config.CAMERA_INTEGRITY_ENABLED),
            include_bot_audio_in_recording=bool(
                app_config.RECALL_INCLUDE_BOT_AUDIO_IN_RECORDING
            ),
        )

        bot_data = recall_service.create_bot(config)
        bot_id = bot_data["id"]

        use_webpage = bool(output_media_page_url)
        if use_webpage:
            ws_hub.register_page_session(page_session_id, bot_id)

        session_manager.create_session(
            bot_id, meeting_url, bot_data=bot_data, use_webpage=use_webpage
        )

        session = session_manager.get_session(bot_id)
        interview_configured = False
        localization_status = None
        questions_planned = None
        resolved_language = None
        orch = None

        if session and _interview_config_provided(request):
            if not all(
                [request.candidate_name, request.jdText, request.cvText, request.questions]
            ):
                session_manager.end_session(bot_id)
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Partial interview config on join. Provide candidate_name, "
                        "jdText, cvText, questions, and optional language_mode together."
                    ),
                )
            candidate_name, jd_text, cv_text, bank, resolved_language = (
                _validate_interview_config(request)
            )

            # Persist / attach DB interview before wiring orchestrator
            if user is not None and db is not None and (
                request.interview_id is not None
                or (persist_candidate_id and persist_job_id)
            ):
                try:
                    if request.interview_id is not None:
                        row = interview_persist.attach_bot_to_interview(
                            db,
                            user,
                            request.interview_id,
                            bot_id,
                            replace_existing=request.replace_existing,
                        )
                        db_interview_id = str(row.id)
                    else:
                        from interview_engine import QuestionSelector
                        import config as _cfg

                        planned_persist = planned_from_db or QuestionSelector.select(
                            bank, _cfg.MAX_QUESTIONS
                        )
                        row = interview_persist.create_interview_with_bot(
                            db,
                            user,
                            bot_id=bot_id,
                            meeting_url=meeting_url,
                            candidate_id=persist_candidate_id,
                            job_posting_id=persist_job_id,
                            candidate_name=candidate_name,
                            job_title=persist_job_title
                            or request.job_title
                            or "Interview",
                            jd_text=jd_text,
                            cv_text=cv_text,
                            planned=planned_persist,
                            language_mode=resolved_language,
                            bot_name=bot_name,
                            greeting_message=request.greeting_message,
                            document_extraction_id=persist_extraction_id,
                        )
                        db_interview_id = str(row.id)
                        planned_from_db = planned_persist
                except HTTPException:
                    session_manager.end_session(bot_id)
                    raise
                except Exception as persist_ex:
                    logger.warning(
                        "[interview] persist on join failed bot=%s: %s",
                        bot_id[:8],
                        persist_ex,
                        exc_info=True,
                    )

            await _attach_interview_to_session(
                session,
                bot_id,
                candidate_name,
                jd_text,
                cv_text,
                bank,
                resolved_language,
                request.greeting_message,
                planned=planned_from_db,
                db_interview_id=db_interview_id,
            )
            interview_configured = True
            orch = session.state.interview_orchestrator
            localization_status = orch.localization_status if orch else None
            questions_planned = len(orch.planned_questions) if orch else None

        if bot_data.get("media_url"):
            logger.info(f"Bot '{bot_name}' created with WebRTC streaming. ID: {bot_id}")
        else:
            logger.info(f"Bot '{bot_name}' created with file upload. ID: {bot_id}")

        return JoinMeetingResponse(
            success=True,
            bot_id=bot_id,
            bot_name=bot_name,
            meeting_url=meeting_url,
            status="joining",
            message=(
                "Bot created and joining the meeting. Interview configured — "
                "call POST /api/start when the bot is admitted and you are ready."
                if interview_configured
                else "Bot created and joining the meeting."
            ),
            interview_configured=interview_configured,
            language_mode=resolved_language,
            localization_status=localization_status,
            questions_planned=questions_planned,
            planned_questions=(
                orch.planned_questions_summary() if orch else None
            ),
            interview_id=UUID(db_interview_id) if db_interview_id else None,
        )

    except HTTPException:
        session_manager.release_meeting_reservation(meeting_url)
        raise
    except requests.HTTPError as e:
        session_manager.release_meeting_reservation(meeting_url)
        recall_detail = e.response.text if e.response is not None else str(e)
        try:
            recall_detail = e.response.json()
        except Exception:
            pass
        logger.error(f"Recall rejected meeting URL: {recall_detail}")
        raise HTTPException(
            status_code=400,
            detail=recall_detail if isinstance(recall_detail, str) else recall_detail,
        ) from e
    except Exception as e:
        session_manager.release_meeting_reservation(meeting_url)
        logger.error(f"Failed to create bot: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


class StartInterviewRequest(BaseModel):
    """Optional body for POST /api/start — interview config should be sent on join."""
    greeting_message: Optional[str] = None
    # Legacy: full config on start if join did not include interview setup
    candidate_name: Optional[str] = None
    jdText: Optional[str] = None
    cvText: Optional[str] = None
    questions: Optional[List[QuestionBankItem]] = None
    language_mode: Optional[Literal["english", "hinglish"]] = None


@app.post("/api/start/{bot_id}")
async def start_interview(bot_id: str, request: StartInterviewRequest = None):
    """
    Begin speaking — send greeting and open the interview.

    Interview config (JD, CV, questions, language) should be sent on POST /api/join.
    This endpoint verifies the bot is in_meeting and setup is ready, then speaks.
    """
    try:
        session = session_manager.get_session(bot_id)

        if not session:
            raise HTTPException(status_code=404, detail=f"Bot {bot_id} not found")

        if not session.is_active:
            raise HTTPException(status_code=400, detail="Bot session is not active")

        if session.state.is_started.is_set():
            raise HTTPException(
                status_code=409,
                detail={
                    "success": False,
                    "bot_id": bot_id,
                    "message": "Interview already started",
                },
            )

        body = request or StartInterviewRequest()
        orchestrator = session.state.interview_orchestrator

        # Legacy path: config on start when join did not configure interview
        if orchestrator is None:
            if not all([body.candidate_name, body.jdText, body.cvText, body.questions]):
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Interview not configured. Send candidate_name, jdText, cvText, "
                        "questions on POST /api/join, or include them in this start request."
                    ),
                )
            candidate_name = (body.candidate_name or "").strip()
            jd_text = (body.jdText or "").strip()
            cv_text = (body.cvText or "").strip()
            try:
                resolved_language = resolve_language_mode(body.language_mode)
            except ValueError as ve:
                raise HTTPException(status_code=400, detail=str(ve))
            from interview_engine import InterviewOrchestrator, parse_bank_questions

            try:
                bank = parse_bank_questions([q.model_dump() for q in body.questions])
                orchestrator = InterviewOrchestrator.create(
                    bot_id=bot_id,
                    candidate_name=candidate_name,
                    jd_text=jd_text,
                    cv_text=cv_text,
                    bank=bank,
                    language_mode=resolved_language,
                )
            except ValueError as ve:
                raise HTTPException(status_code=400, detail=str(ve))
            session_manager.configure_interview_session(
                session, orchestrator, resolved_language, body.greeting_message
            )
            await session_manager.apply_language_profile(session, resolved_language)
            session_manager.start_question_localization(session)

        resolved_language = session.state.interview_language or "english"
        greeting_message = body.greeting_message or session.pending_greeting_message

        if orchestrator.language_mode == "hinglish":
            if orchestrator.localization_status == "pending":
                raise HTTPException(
                    status_code=409,
                    detail={
                        "message": "Hinglish question localization still in progress. Retry shortly.",
                        "bot_id": bot_id,
                        "localization_status": "pending",
                    },
                )
            if orchestrator.localization_status == "failed":
                raise HTTPException(
                    status_code=503,
                    detail={
                        "message": "Hinglish localization failed during join setup.",
                        "bot_id": bot_id,
                        "localization_status": "failed",
                        "error": orchestrator.localization_error,
                    },
                )

        try:
            phase, status_code = recall_service.get_bot_phase(bot_id)
        except Exception as e:
            logger.error(f"Failed to verify bot status before start: {e}")
            raise HTTPException(
                status_code=503,
                detail={
                    "message": "Could not verify bot meeting status. Try again shortly.",
                    "bot_id": bot_id,
                },
            )

        if phase == "ended":
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "Bot is no longer in the meeting. Create a new bot with /api/join.",
                    "bot_id": bot_id,
                    "phase": phase,
                    "recall_status": status_code,
                },
            )

        if phase in ("lobby", "joining"):
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "Bot has not entered the meeting yet. Admit the bot from the lobby first.",
                    "bot_id": bot_id,
                    "phase": phase,
                    "recall_status": status_code,
                },
            )

        if phase != "in_meeting":
            raise HTTPException(
                status_code=409,
                detail={
                    "message": f"Bot is not ready to start (status: {status_code}). Wait until it joins the meeting.",
                    "bot_id": bot_id,
                    "phase": phase,
                    "recall_status": status_code,
                },
            )

        candidate_name = orchestrator.candidate_name

        if greeting_message:
            session.state.is_started.set()
            session_manager.arm_camera_integrity(session)
            session.state.llm_queue.put(greeting_message)
        else:
            ui = get_ui_strings(resolved_language)
            greeting_text = ui.greeting_template.format(
                name=candidate_name,
                bot_name=BOT_NAME,
            )

            session.state.is_started.set()
            session_manager.arm_camera_integrity(session)
            log_transcript(bot_id, "assistant", greeting_text)
            session.state.tts_queue.put(greeting_text)
            session.state.tts_queue.put("<END_OF_TURN>")

            orchestrator.on_greeting_sent()

            logger.info(
                "[INTERVIEW GREETING] bot=%s fixed greeting sent to TTS",
                bot_id[:8],
            )

        db_id = getattr(session, "db_interview_id", None) or getattr(
            orchestrator, "db_interview_id", None
        )
        if db_id:
            try:
                interview_persist.mark_interview_started(db_id)
            except Exception as ex:
                logger.warning("[interview] mark started failed: %s", ex)

        logger.info(
            "Interview started for bot %s candidate=%s language=%s planned_questions=%d",
            bot_id,
            candidate_name,
            resolved_language,
            len(orchestrator.planned_questions),
        )

        return {
            "success": True,
            "bot_id": bot_id,
            "message": "Interview started",
            "candidate_name": candidate_name,
            "language_mode": resolved_language,
            "questions_planned": len(orchestrator.planned_questions),
            "planned_questions": orchestrator.planned_questions_summary(),
            "planned_question_ids": [q.id for q in orchestrator.planned_questions],
            "phase": orchestrator.phase.value,
            "localization_status": orchestrator.localization_status,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start interview: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


class GenerateQuestionsRequest(BaseModel):
    jdText: str
    cvText: str
    candidate_name: Optional[str] = None
    language_mode: Optional[str] = None
    candidate_id: Optional[UUID] = None
    job_posting_id: Optional[UUID] = None
    extraction_id: Optional[UUID] = None


@app.post("/api/extract-cv")
async def extract_cv(
    cv_file: UploadFile = File(...),
    candidate_id: Optional[UUID] = Form(None),
    user: Optional[User] = Depends(get_optional_user),
    db: Optional[Session] = Depends(get_optional_db),
):
    """
    Proxy CV upload to n8n.
    When authenticated: save file to documents + link document_extractions.cv_document_id.
    """
    logger.info("[EXTRACT-CV] received cv=%s auth=%s", bool(cv_file), bool(user))
    if not cv_file.filename:
        raise HTTPException(status_code=400, detail="Upload a CV file")

    cv_bytes = await cv_file.read()
    if not cv_bytes:
        raise HTTPException(status_code=400, detail="CV file is empty")

    doc_row = None
    if user is not None and db is not None:
        try:
            doc_row = document_store.create_uploaded_document(
                db,
                user,
                document_type="cv",
                file_bytes=cv_bytes,
                original_filename=cv_file.filename,
                mime_type=cv_file.content_type,
                candidate_id=candidate_id,
                source="upload",
            )
        except HTTPException:
            raise
        except Exception as ex:
            logger.warning("[EXTRACT-CV] document persist failed: %s", ex, exc_info=True)

    try:
        result = await asyncio.to_thread(
            extract_cv_file,
            cv_bytes=cv_bytes,
            cv_filename=cv_file.filename,
        )
    except ValueError as ve:
        if doc_row is not None and db is not None:
            document_store.mark_document_failed(db, doc_row.id, error=str(ve))
        raise HTTPException(status_code=502, detail=str(ve))

    payload = {"success": True, **result}
    if user is not None and db is not None:
        try:
            if doc_row is not None:
                document_store.mark_document_ready(
                    db,
                    doc_row.id,
                    extracted_text=result.get("cvText") or "",
                )
            row = save_cv_extraction(
                db,
                user,
                cv_text=result.get("cvText") or "",
                candidate_id=candidate_id,
                cv_document_id=doc_row.id if doc_row else None,
                raw_response=result.get("cvStructured"),
            )
            payload["extraction_id"] = str(row.id)
            if doc_row is not None:
                payload["document_id"] = str(doc_row.id)
        except HTTPException:
            raise
        except Exception as ex:
            logger.warning("[EXTRACT-CV] extraction persist failed: %s", ex, exc_info=True)
    return payload


@app.post("/api/extract-jd")
async def extract_jd(
    jd_file: UploadFile = File(...),
    job_posting_id: Optional[UUID] = Form(None),
    user: Optional[User] = Depends(get_optional_user),
    db: Optional[Session] = Depends(get_optional_db),
):
    """
    Proxy JD upload to n8n.
    When authenticated: save file to documents + link document_extractions.jd_document_id.
    """
    logger.info("[EXTRACT-JD] received jd=%s auth=%s", bool(jd_file), bool(user))
    if not jd_file.filename:
        raise HTTPException(status_code=400, detail="Upload a JD file")

    jd_bytes = await jd_file.read()
    if not jd_bytes:
        raise HTTPException(status_code=400, detail="JD file is empty")

    doc_row = None
    if user is not None and db is not None:
        try:
            doc_row = document_store.create_uploaded_document(
                db,
                user,
                document_type="jd",
                file_bytes=jd_bytes,
                original_filename=jd_file.filename,
                mime_type=jd_file.content_type,
                job_posting_id=job_posting_id,
                source="upload",
            )
        except HTTPException:
            raise
        except Exception as ex:
            logger.warning("[EXTRACT-JD] document persist failed: %s", ex, exc_info=True)

    try:
        result = await asyncio.to_thread(
            extract_jd_file,
            jd_bytes=jd_bytes,
            jd_filename=jd_file.filename,
        )
    except ValueError as ve:
        if doc_row is not None and db is not None:
            document_store.mark_document_failed(db, doc_row.id, error=str(ve))
        raise HTTPException(status_code=502, detail=str(ve))

    payload = {"success": True, **result}
    if user is not None and db is not None:
        try:
            if doc_row is not None:
                document_store.mark_document_ready(
                    db,
                    doc_row.id,
                    extracted_text=result.get("jdText") or "",
                )
            row = save_jd_extraction(
                db,
                user,
                jd_text=result.get("jdText") or "",
                job_posting_id=job_posting_id,
                jd_document_id=doc_row.id if doc_row else None,
                raw_response=result.get("jdStructured"),
            )
            payload["extraction_id"] = str(row.id)
            if doc_row is not None:
                payload["document_id"] = str(doc_row.id)
        except HTTPException:
            raise
        except Exception as ex:
            logger.warning("[EXTRACT-JD] extraction persist failed: %s", ex, exc_info=True)
    return payload


@app.post("/api/generate-questions")
async def generate_questions_endpoint(
    body: GenerateQuestionsRequest,
    user: Optional[User] = Depends(get_optional_user),
    db: Optional[Session] = Depends(get_optional_db),
):
    """Forward JD/CV to n8n; persist questions_json when authenticated."""
    logger.info(
        "[GENERATE-QUESTIONS] jd_len=%s cv_len=%s auth=%s",
        len(body.jdText),
        len(body.cvText),
        bool(user),
    )

    try:
        result = await asyncio.to_thread(
            generate_questions,
            jd_text=body.jdText,
            cv_text=body.cvText,
            candidate_name=body.candidate_name,
            language_mode=body.language_mode,
        )
    except ValueError as ve:
        if user is not None and db is not None:
            save_question_generation(
                db,
                user,
                jd_text=body.jdText,
                cv_text=body.cvText,
                questions=None,
                candidate_id=body.candidate_id,
                job_posting_id=body.job_posting_id,
                extraction_id=body.extraction_id,
                error_message=str(ve),
                success=False,
            )
        raise HTTPException(status_code=502, detail=str(ve))

    payload = {"success": True, **result}
    if user is not None and db is not None:
        row = save_question_generation(
            db,
            user,
            jd_text=body.jdText,
            cv_text=body.cvText,
            questions=result.get("questions"),
            candidate_id=body.candidate_id,
            job_posting_id=body.job_posting_id,
            extraction_id=body.extraction_id,
            raw_response=result,
            success=True,
        )
        payload["extraction_id"] = str(row.id)
    return payload


@app.get("/api/reports")
async def list_interview_reports():
    """List interview report summaries from DB (preferred), merged with disk fallback."""
    from interview_persist import list_db_report_summaries

    db_rows = list_db_report_summaries()
    by_bot: dict[str, dict] = {}
    for row in db_rows:
        bid = row.get("bot_id")
        if bid:
            by_bot[str(bid)] = row

    for row in list_reports():
        bid = row.get("bot_id")
        if not bid or str(bid) in by_bot:
            continue
        row = dict(row)
        row["has_feedback"] = feedback_exists(str(bid))
        by_bot[str(bid)] = row

    summaries = list(by_bot.values())
    summaries.sort(key=lambda r: r.get("completed_at") or "", reverse=True)
    for row in summaries:
        bid = row.get("bot_id")
        if bid and "has_feedback" not in row:
            row["has_feedback"] = feedback_exists(str(bid))
    return {"reports": summaries}


@app.get("/api/feedback/{bot_id}/context")
async def get_feedback_context(bot_id: str):
    """Public: validate feedback link and whether form was already submitted."""
    ctx = _feedback_bot_context(bot_id)
    return {
        "success": True,
        "bot_id": bot_id,
        "candidate_name": ctx.get("candidate_name"),
        "already_submitted": feedback_exists(bot_id),
    }


@app.get("/api/feedback/{bot_id}")
async def get_interview_feedback(bot_id: str):
    """Recruiter/admin: load submitted candidate feedback for an interview."""
    _feedback_bot_context(bot_id)
    feedback = load_feedback(bot_id)
    if not feedback:
        raise HTTPException(status_code=404, detail="No feedback submitted yet")
    return {"success": True, "feedback": feedback}


@app.post("/api/feedback/{bot_id}")
async def submit_interview_feedback(bot_id: str, body: SubmitFeedbackRequest):
    """Public: candidate submits post-interview feedback (one per bot_id)."""
    ctx = _feedback_bot_context(bot_id)
    if feedback_exists(bot_id):
        raise HTTPException(status_code=409, detail="Feedback already submitted")

    try:
        save_feedback(
            bot_id,
            {
                **body.model_dump(),
                "candidate_name": ctx.get("candidate_name"),
            },
        )
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

    logger.info("[FEEDBACK] bot=%s overall=%s clarity=%s", bot_id[:8], body.overall_rating, body.clarity_rating)
    return {"success": True, "message": "Thank you for your feedback"}


@app.get("/api/interview/{bot_id}/report")
async def get_interview_report(bot_id: str):
    """
    Get structured interview report card (scores, develop/fix areas).
    Prefers Postgres; falls back to disk / live session.
    """
    report = resolve_interview_report(bot_id, session_manager)
    logger.info(
        "[REPORT] bot=%s scored=%d overall_avg=%s stopped=%s",
        bot_id[:8],
        report.get("questions_scored"),
        report.get("overall_average"),
        report.get("stopped_reason"),
    )
    return {"success": True, "report": report}


@app.get("/api/interview/{bot_id}/report.html", response_class=HTMLResponse)
async def get_interview_report_html(bot_id: str):
    """
    Paper-style HTML report card for browser / Postman preview.
    Returns 409 until the interview ends; serves from disk after session cleanup.
    """
    try:
        report = resolve_interview_report(bot_id, session_manager)
    except HTTPException as exc:
        if exc.status_code == 409:
            return HTMLResponse(
                content=render_not_completed_html(bot_id),
                status_code=409,
            )
        raise

    logger.info(
        "[REPORT HTML] bot=%s scored=%d overall_avg=%s",
        bot_id[:8],
        report.get("questions_scored"),
        report.get("overall_average"),
    )
    return HTMLResponse(content=render_report_html(report), status_code=200)


@app.post("/api/interviews/{bot_id}/cancel", response_model=LeaveResponse)
async def cancel_interview_setup(bot_id: str):
    """
    Cancel live interview setup — removes Recall bot from meeting lobby.
    Distinct from POST /api/interviews/scheduled/{id}/cancel (DB-only schedule cancel).
    """
    try:
        logger.info(f"Cancelling interview setup for bot {bot_id}")
        recall_removed = session_manager.end_session(bot_id)
        try:
            interview_persist.detach_bot_after_lobby_cancel(bot_id)
        except Exception as db_ex:
            logger.warning(
                "[interview] detach after lobby cancel failed bot=%s: %s",
                bot_id[:8],
                db_ex,
            )
        if not recall_removed:
            raise HTTPException(
                status_code=502,
                detail=(
                    "Interview cancelled locally but the bot may still be in the "
                    "meeting lobby. Click Cancel again or deny the bot in Teams."
                ),
            )
        return LeaveResponse(
            success=True,
            bot_id=bot_id,
            message="Interview setup cancelled; bot removed from meeting",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cancel interview setup: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/rejoin/{bot_id}")
async def rejoin_bot_to_lobby(bot_id: str):
    """
    Rejoin bot to meeting lobby after denial.
    Creates new bot instance while preserving session state (CV, JD, questions).
    
    Path Parameter:
    - bot_id: Current bot ID to rejoin
    
    Response:
    {
        "success": true,
        "old_bot_id": "abc-123",
        "new_bot_id": "def-456",
        "message": "Bot rejoined to lobby"
    }
    """
    try:
        session = session_manager.get_session(bot_id)
        if not session:
            raise HTTPException(status_code=404, detail=f"Session not found for bot {bot_id}")
        
        if session.state.is_started.is_set():
            raise HTTPException(
                status_code=400,
                detail="Cannot rejoin - interview already started"
            )
        
        meeting_url = session.meeting_url
        
        # Build bot config (same as original join)
        import uuid as _uuid
        public_base = os.getenv("PUBLIC_NGROK_URL", "").rstrip("/")
        page_session_id = str(_uuid.uuid4())
        output_media_page_url: Optional[str] = None
        
        if app_config.RECALL_USE_OUTPUT_MEDIA and public_base:
            import urllib.parse
            output_media_page_url = (
                f"{public_base}/voice-agent"
                f"?page_session_id={page_session_id}"
                f"&name={urllib.parse.quote(BOT_NAME)}"
            )
        
        config = BotConfig(
            meeting_url=meeting_url,
            bot_name=BOT_NAME,
            websocket_url=PUBLIC_WEBSOCKET_URL,
            use_output_media=app_config.RECALL_USE_OUTPUT_MEDIA,
            output_media_url=output_media_page_url,
            enable_camera_integrity=bool(app_config.CAMERA_INTEGRITY_ENABLED),
            include_bot_audio_in_recording=bool(
                app_config.RECALL_INCLUDE_BOT_AUDIO_IN_RECORDING
            ),
        )
        
        # Rejoin bot (creates new bot, preserves session)
        logger.info(f"Rejoining bot {bot_id[:8]} to lobby for {meeting_url[:50]}...")
        new_bot_id = session_manager.rejoin_bot(bot_id, config)
        
        # Register new page session if using output media
        if output_media_page_url:
            ws_hub.register_page_session(page_session_id, new_bot_id)
        
        logger.info(
            f"Bot rejoined successfully: {bot_id[:8]} → {new_bot_id[:8]}"
        )
        
        return {
            "success": True,
            "old_bot_id": bot_id,
            "new_bot_id": new_bot_id,
            "message": "Bot rejoined to lobby - admit from Teams to continue",
        }
        
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to rejoin bot: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/leave/{bot_id}", response_model=LeaveResponse)
async def leave_meeting(bot_id: str):
    """
    Leave a meeting (remove bot).
    
    Path Parameter:
    - bot_id: Bot ID returned from /join
    
    Response:
    {
        "success": true,
        "bot_id": "abc-123",
        "message": "Bot removed from meeting"
    }
    """
    try:
        logger.info(f"Removing bot {bot_id} from meeting")
        
        recall_removed = session_manager.end_session(bot_id)
        if not recall_removed:
            raise HTTPException(
                status_code=502,
                detail=(
                    "Session ended locally but the bot may still be in the meeting. "
                    "Try again or remove it from Teams."
                ),
            )
        
        return LeaveResponse(
            success=True,
            bot_id=bot_id,
            message="Bot removed from meeting"
        )
        
    except Exception as e:
        logger.error(f"Failed to leave meeting: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _resolve_meeting_url(status_data: dict, session) -> Optional[str]:
    """Recall may return meeting_url as a string or a nested object."""
    if session and getattr(session, "meeting_url", None):
        return session.meeting_url
    raw = status_data.get("meeting_url")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    if isinstance(raw, dict):
        for key in ("meeting_url", "url", "join_url", "meeting_link"):
            val = raw.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    return None


@app.get("/api/status/{bot_id}", response_model=StatusResponse)
async def get_bot_status(bot_id: str):
    """
    Get bot status.
    
    Path Parameter:
    - bot_id: Bot ID
    
    Response:
    {
        "bot_id": "abc-123",
        "status": "in_call",
        "meeting_url": "...",
        "is_active": true
    }
    """
    try:
        status_data = recall_service.get_bot_status(bot_id)
        session = session_manager.get_session(bot_id)
        recall_phase = None
        try:
            recall_phase, _ = recall_service.get_bot_phase(bot_id)
        except Exception:
            pass

        orch = session.state.interview_orchestrator if session else None
        interview_configured = orch is not None
        localization_status = orch.localization_status if orch else None
        ready_to_start = (
            bool(session and session.is_active and orch and not session.state.is_started.is_set())
            and recall_phase == "in_meeting"
            and (orch.is_localization_ready() if orch else False)
        )

        interview_started = session.state.is_started.is_set() if session else False
        interview_ended = session.state.interview_ended.is_set() if session else False
        current_slot = None
        questions_scored = None
        planned_questions = None
        interview_phase = None
        if orch:
            planned_questions = orch.planned_questions_summary()
            questions_scored = len(orch.answer_records)
            interview_phase = orch.phase.value
            if interview_started and not interview_ended:
                current_slot = orch.current_index + 1

        return StatusResponse(
            bot_id=bot_id,
            status=status_data.get("status_changes", [{}])[-1].get("code", "unknown") if status_data.get("status_changes") else "unknown",
            meeting_url=_resolve_meeting_url(status_data, session),
            is_active=session.is_active if session else False,
            recall_phase=recall_phase,
            interview_configured=interview_configured,
            interview_started=interview_started,
            localization_status=localization_status,
            ready_to_start=ready_to_start,
            questions_planned=len(orch.planned_questions) if orch else None,
            candidate_name=orch.candidate_name if orch else None,
            language_mode=session.state.interview_language if session else None,
            planned_questions=planned_questions,
            current_question_slot=current_slot,
            questions_scored=questions_scored,
            interview_phase=interview_phase,
            interview_ended=interview_ended,
        )
        
    except Exception as e:
        logger.error(f"Failed to get status: {e}")
        raise HTTPException(status_code=404, detail=f"Bot {bot_id} not found")


@app.get("/api/sessions")
async def list_active_sessions():
    """
    List all active bot sessions with start status.
    
    Response:
    {
        "active_sessions": 2,
        "bots": [
            {
                "bot_id": "abc-123",
                "meeting_url": "...",
                "is_started": true
            }
        ]
    }
    """
    sessions = session_manager.get_active_sessions()
    
    return {
        "active_sessions": len(sessions),
        "bots": [
            {
                "bot_id": bot_id,
                "meeting_url": session.meeting_url,
                "is_active": session.is_active,
                "is_started": session.state.is_started.is_set(),
                "interview_ended": session.state.interview_ended.is_set(),
                "interview_phase": (
                    session.state.interview_orchestrator.phase.value
                    if session.state.interview_orchestrator
                    else None
                ),
                "localization_status": (
                    session.state.interview_orchestrator.localization_status
                    if session.state.interview_orchestrator
                    else None
                ),
                "language_mode": session.state.interview_language,
                "candidate_name": (
                    session.state.interview_orchestrator.candidate_name
                    if session.state.interview_orchestrator
                    else None
                ),
                "questions_scored": (
                    len(session.state.interview_orchestrator.answer_records)
                    if session.state.interview_orchestrator
                    else 0
                ),
            }
            for bot_id, session in sessions.items()
        ]
    }


@app.get("/api/diagnostic/audio")
async def audio_diagnostic():
    """
    Production diagnostic endpoint - explains bot audio behavior and mute state.
    
    This endpoint provides critical information about how Recall.ai bots work.
    """
    sessions = session_manager.get_active_sessions()
    
    diagnostic_info = {
        "bot_audio_behavior": {
            "why_bot_shows_muted": "Recall.ai bots join meetings with microphone OFF by default. This is normal and expected.",
            "does_mute_prevent_speaking": False,
            "explanation": "The 'muted' icon is cosmetic. When you send audio via output_audio API, the bot WILL speak into the meeting regardless of the mute indicator.",
            "api_limitation": "Recall.ai does not provide an API to change the visual mute indicator. All production implementations work this way.",
            "how_bot_speaks": "Bot plays audio when triggered via POST /bot/{id}/output_audio/ endpoint (happens automatically when AI responds)"
        },
        "current_bot_status": {
            "active_bots": len(sessions),
            "bots": [
                {
                    "bot_id": bot_id[:8] + "...",
                    "can_speak": session.is_active and session.audio_sender is not None,
                    "meeting_url": session.meeting_url[:50] + "..." if len(session.meeting_url) > 50 else session.meeting_url
                }
                for bot_id, session in sessions.items()
            ]
        },
        "troubleshooting": {
            "if_bot_not_speaking": [
                "1. Check logs for '✓ Audio sent successfully' messages",
                "2. Verify bot status is 'in_call_recording' via GET /api/status/{bot_id}",
                "3. Check for 'kind field required' errors (should be fixed)",
                "4. Ensure automatic_audio_output is configured (should be present)",
                "5. Verify MP3 format is being used (not WAV)"
            ],
            "common_errors": {
                "kind_field_required": "Fixed - MP3 format with 'kind' field is now included",
                "cannot_command_completed_bot": "Bot has left meeting - create new bot",
                "bot_shows_muted": "Not an error - this is normal behavior"
            }
        },
        "production_status": {
            "audio_output_api": "✓ Configured with automatic_audio_output",
            "mp3_format": "✓ Using MP3 (required by Recall.ai)",
            "kind_field": "✓ Included in payload",
            "error_handling": "✓ Production-grade with retries",
            "bot_status_verification": "✓ Checks bot state before sending audio"
        }
    }
    
    return diagnostic_info


@app.get("/api/active_meetings")
async def list_active_meetings():
    """
    List all active meetings with their bot IDs.
    Useful for debugging duplicate bot issues.
    
    Response:
    {
        "active_meetings": 1,
        "meetings": [
            {
                "meeting_url": "https://teams.microsoft.com/...",
                "bot_id": "abc-123",
                "status": "active"
            }
        ]
    }
    """
    with session_manager.sessions_lock:
        meetings = []
        for meeting_url, bot_id in session_manager.meeting_to_bot.items():
            session = session_manager.sessions.get(bot_id)
            meetings.append({
                "meeting_url": meeting_url,
                "bot_id": bot_id,
                "status": "active" if (session and session.is_active) else "inactive"
            })
        
        return {
            "active_meetings": len(meetings),
            "meetings": meetings
        }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "recall-bot-api",
        "websocket_url": PUBLIC_WEBSOCKET_URL,
        "bot_name": BOT_NAME,
        "lobby_timeout_minutes": LOBBY_TIMEOUT_MINUTES,
    }


if __name__ == "__main__":
    # Start WebSocket receiver in background
    import threading
    import asyncio
    
    def start_websocket():
        receiver = AudioReceiver(
            host="0.0.0.0",
            port=WEBSOCKET_PORT,
            audio_callback=session_manager.handle_audio_chunk,
            transcript_callback=session_manager.handle_recall_transcript,
            video_callback=session_manager.handle_video_frame,
        )
        receiver.run()
    
    websocket_thread = threading.Thread(target=start_websocket, daemon=True)
    websocket_thread.start()
    
    logger.info("=" * 60)
    logger.info("Recall.ai Bot API Started")
    logger.info("=" * 60)
    logger.info(f"API Server: http://0.0.0.0:8000")
    logger.info(f"WebSocket: ws://0.0.0.0:{WEBSOCKET_PORT}")
    logger.info(f"Docs: http://0.0.0.0:8000/docs")
    logger.info(f"Bot Name: {BOT_NAME}")
    logger.info(
        "Camera integrity: %s",
        "ON" if app_config.CAMERA_INTEGRITY_ENABLED else "OFF",
    )
    logger.info("=" * 60)
    
    # Start FastAPI server
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
