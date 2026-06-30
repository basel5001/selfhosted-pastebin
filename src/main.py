"""Selfhosted Pastebin — encrypted paste service powered by FastAPI."""

import os
import secrets
import string
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates

from src.crypto import hash_password, verify_password
from src.database import (
    cleanup_expired,
    count_pastes,
    delete_paste,
    get_paste,
    increment_views,
    init_db,
    insert_paste,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MAX_PASTE_SIZE = int(os.getenv("MAX_PASTE_SIZE", 524288))  # 512 KB
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", 60))  # seconds
RATE_LIMIT_MAX = int(os.getenv("RATE_LIMIT_MAX", 10))  # per window
PASTE_ID_LENGTH = 8

EXPIRY_MAP: dict[str, timedelta | None] = {
    "1h": timedelta(hours=1),
    "1d": timedelta(days=1),
    "1w": timedelta(weeks=1),
    "1m": timedelta(days=30),
    "never": None,
}

# ---------------------------------------------------------------------------
# Rate limiter (in-memory, per-process)
# ---------------------------------------------------------------------------

_rate_store: dict[str, list[float]] = defaultdict(list)


def _check_rate_limit(ip: str) -> bool:
    """Return True if the request is within the rate limit."""
    now = time.time()
    window_start = now - RATE_LIMIT_WINDOW
    # Prune old entries
    _rate_store[ip] = [t for t in _rate_store[ip] if t > window_start]
    if len(_rate_store[ip]) >= RATE_LIMIT_MAX:
        return False
    _rate_store[ip].append(now)
    return True


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    cleanup_expired()
    yield


app = FastAPI(
    title="Selfhosted Pastebin",
    version="1.0.0",
    docs_url="/docs",
    lifespan=lifespan,
)

templates = Jinja2Templates(directory="templates")


def _generate_id(length: int = PASTE_ID_LENGTH) -> str:
    alphabet = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ---------------------------------------------------------------------------
# Routes — Pages
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Serve the paste creation form."""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "pastes": count_pastes()}


@app.get("/{paste_id}", response_class=HTMLResponse)
async def view_paste_page(request: Request, paste_id: str):
    """Render the paste view page."""
    paste = get_paste(paste_id)
    if paste is None:
        raise HTTPException(status_code=404, detail="Paste not found or expired")
    return templates.TemplateResponse(
        "view.html",
        {
            "request": request,
            "paste_id": paste_id,
            "has_password": paste["password_hash"] is not None,
        },
    )


# ---------------------------------------------------------------------------
# Routes — API
# ---------------------------------------------------------------------------


@app.post("/api/paste")
async def create_paste(request: Request):
    """Create a new paste.

    Expects JSON body:
        content: str (encrypted client-side)
        language: str (default "plain")
        expires_in: str (1h|1d|1w|1m|never, default "1d")
        password: str (optional)
        burn_after_read: bool (default false)
    """
    ip = _client_ip(request)
    if not _check_rate_limit(ip):
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Try again later.",
        )

    body = await request.json()
    content: str = body.get("content", "")
    language: str = body.get("language", "plain")
    expires_in: str = body.get("expires_in", "1d")
    password: str | None = body.get("password")
    burn_after_read: bool = body.get("burn_after_read", False)

    if not content:
        raise HTTPException(status_code=400, detail="Content is required")

    if len(content.encode("utf-8")) > MAX_PASTE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"Paste too large. Max {MAX_PASTE_SIZE // 1024}KB",
        )

    if expires_in not in EXPIRY_MAP:
        raise HTTPException(status_code=400, detail=f"Invalid expiry: {expires_in}")

    delta = EXPIRY_MAP[expires_in]
    expires_at = (
        (datetime.now(timezone.utc) + delta).isoformat() if delta else None
    )

    password_hash = hash_password(password) if password else None

    paste_id = _generate_id()
    insert_paste(
        paste_id=paste_id,
        content=content,
        language=language,
        expires_at=expires_at,
        password_hash=password_hash,
        burn_after_read=burn_after_read,
    )

    return JSONResponse(
        status_code=201,
        content={"id": paste_id, "url": f"/{paste_id}"},
    )


@app.get("/api/paste/{paste_id}")
async def get_paste_api(paste_id: str, password: str | None = None):
    """Return paste data as JSON. Checks expiry and optional password."""
    paste = get_paste(paste_id)
    if paste is None:
        raise HTTPException(status_code=404, detail="Paste not found or expired")

    # Password check
    if paste["password_hash"]:
        if not password:
            raise HTTPException(status_code=401, detail="Password required")
        if not verify_password(password, paste["password_hash"]):
            raise HTTPException(status_code=403, detail="Invalid password")

    views = increment_views(paste_id)

    response = {
        "id": paste_id,
        "content": paste["content"],
        "language": paste["language"],
        "created_at": paste["created_at"],
        "expires_at": paste["expires_at"],
        "views": views,
        "burn_after_read": bool(paste["burn_after_read"]),
    }

    # Burn after read: delete after first successful retrieval
    if paste["burn_after_read"]:
        delete_paste(paste_id)

    return response


@app.get("/api/paste/{paste_id}/raw")
async def get_paste_raw(paste_id: str, password: str | None = None):
    """Return raw paste content (still encrypted — decryption is client-side)."""
    paste = get_paste(paste_id)
    if paste is None:
        raise HTTPException(status_code=404, detail="Paste not found or expired")

    if paste["password_hash"]:
        if not password:
            raise HTTPException(status_code=401, detail="Password required")
        if not verify_password(password, paste["password_hash"]):
            raise HTTPException(status_code=403, detail="Invalid password")

    increment_views(paste_id)
    return PlainTextResponse(paste["content"])


@app.delete("/api/paste/{paste_id}")
async def delete_paste_api(paste_id: str):
    """Delete a paste by ID."""
    deleted = delete_paste(paste_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Paste not found")
    return {"detail": "Paste deleted"}
