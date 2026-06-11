"""
WebSocket Audio Hub
===================
Manages WebSocket connections for the Output Media audio stream.

Why a dedicated module?
-----------------------
api_server.py is run as __main__.  Any module that does
  `from api_server import something`
causes Python to import api_server.py a SECOND time under the name
"api_server", producing a separate copy of every module-level dict/lock.

  __main__._audio_ws_clients  ← WebSocket handler writes here
  api_server._audio_ws_clients ← broadcast_pcm reads here  → always empty!

By keeping all hub state HERE, every importer (api_server, session_manager, …)
always gets the same ws_hub module from sys.modules — no duplicates.
"""

import asyncio
import json
import logging
from typing import Any, Dict, Optional, Set

logger = logging.getLogger(__name__)

# ── Shared hub state ──────────────────────────────────────────────────────────
# Maps  bot_id  →  set of active WebSocket connections from the output-media page
_clients: Dict[str, Set[Any]] = {}

# Maps  page_session_id  →  bot_id  (resolved on each WS connect)
_page_to_bot: Dict[str, str] = {}

# Asyncio lock — created lazily so it always belongs to the running event loop
_lock: Optional[asyncio.Lock] = None


def _get_lock() -> asyncio.Lock:
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    return _lock


# ── Session registration (synchronous, called from api_server join handler) ──

def register_page_session(page_session_id: str, bot_id: str) -> None:
    """Record that page_session_id maps to bot_id."""
    _page_to_bot[page_session_id] = bot_id
    logger.info(f"[ws_hub] Registered page_session {page_session_id[:8]}… → bot {bot_id[:8]}…")


def resolve_bot_id(page_session_id: str) -> str:
    """Return bot_id for a page_session_id, or page_session_id itself as fallback."""
    return _page_to_bot.get(page_session_id, page_session_id)


# ── Client management (async, called from the WebSocket endpoint) ─────────────

async def add_client(bot_id: str, ws: Any) -> None:
    async with _get_lock():
        _clients.setdefault(bot_id, set()).add(ws)
    logger.info(f"[ws_hub] Client added for bot {bot_id[:8]}… ({len(_clients.get(bot_id, set()))} total)")


async def remove_client(bot_id: str, ws: Any) -> None:
    async with _get_lock():
        if bot_id in _clients:
            _clients[bot_id].discard(ws)
            if not _clients[bot_id]:
                del _clients[bot_id]
    logger.info(f"[ws_hub] Client removed for bot {bot_id[:8]}…")


# ── Async broadcast helpers (run on the main event loop) ─────────────────────

async def broadcast_pcm(bot_id: str, pcm_bytes: bytes) -> None:
    """Push a raw Int16 PCM binary frame to every WebSocket listener for this bot."""
    async with _get_lock():
        clients = _clients.get(bot_id, set()).copy()

    if not clients:
        return

    dead: Set[Any] = set()
    for ws in clients:
        try:
            await ws.send_bytes(pcm_bytes)
        except Exception:
            dead.add(ws)

    if dead:
        async with _get_lock():
            if bot_id in _clients:
                _clients[bot_id] -= dead


async def send_control(bot_id: str, msg: dict) -> None:
    """Send a JSON control message (start_speaking / stop_speaking / ping) to all page clients."""
    text = json.dumps(msg)
    async with _get_lock():
        clients = _clients.get(bot_id, set()).copy()

    if not clients:
        return

    dead: Set[Any] = set()
    for ws in clients:
        try:
            await ws.send_text(text)
        except Exception:
            dead.add(ws)

    if dead:
        async with _get_lock():
            if bot_id in _clients:
                _clients[bot_id] -= dead


# ── Thread-safe synchronous wrappers (called from TTS worker thread) ──────────

def broadcast_pcm_sync(bot_id: str, pcm_bytes: bytes, timeout: float = 5.0) -> None:
    """
    Schedule broadcast_pcm on the main FastAPI event loop from any thread.
    Uses asyncio.run_coroutine_threadsafe — safe to call from TTS worker threads
    that have their own event loops.
    """
    import config as _cfg          # always the same module object
    loop = _cfg.main_event_loop
    if not loop or not loop.is_running():
        logger.warning(f"[ws_hub] Main loop not ready — dropping PCM for bot {bot_id[:8]}…")
        return
    future = asyncio.run_coroutine_threadsafe(broadcast_pcm(bot_id, pcm_bytes), loop)
    try:
        future.result(timeout=timeout)
    except Exception as e:
        logger.warning(f"[ws_hub] broadcast_pcm failed for bot {bot_id[:8]}…: {e}")


def send_control_sync(bot_id: str, msg: dict, timeout: float = 2.0) -> None:
    """Thread-safe wrapper around send_control."""
    import config as _cfg
    loop = _cfg.main_event_loop
    if not loop or not loop.is_running():
        return
    future = asyncio.run_coroutine_threadsafe(send_control(bot_id, msg), loop)
    try:
        future.result(timeout=timeout)
    except Exception:
        pass
