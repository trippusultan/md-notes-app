"""
Markdown Note-Taking REST API
─────────────────────────────
Endpoints
─────────
POST  /notes/grammar           — check grammar of raw markdown text (or uploaded file)
POST  /notes                   — save a new note  { "name": str, "content": str }
GET   /notes                   — list all saved notes
GET   /notes/{note_id}         — get rendered HTML of a note
GET   /notes/{note_id}/raw     — get raw markdown of a note
DELETE /notes/{note_id}        — delete a note
GET  /docs                     — interactive Swagger / ReDoc (FastAPI auto)
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from fastapi import (
    FastAPI,
    File,
    HTTPException,
    Query,
    UploadFile,
)
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from markdown_it import MarkdownIt
from pydantic import BaseModel, Field

# ── configuration ─────────────────────────────────────────────────────────────
NOTES_DIR = Path(os.getenv("NOTES_DIR", "/home/spoidy/workspace/md-notes-app/notes"))
NOTES_DIR.mkdir(parents=True, exist_ok=True)

INDEX_FILE  = NOTES_DIR / ".index.json"
LANGUAGETOOL_URL = os.getenv("LANGUAGETOOL_URL", "https://api.languagetool.org/v2/check").strip()

app = FastAPI(
    title="Markdown Note-Taking API",
    description="Upload, save, render and grammar-check markdown notes.",
    version="1.0.0",
)

# ── helpers ───────────────────────────────────────────────────────────────────
_md = MarkdownIt()

def _load_index() -> dict[str, dict]:
    if INDEX_FILE.exists():
        return json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    return {}

def _save_index(idx: dict) -> None:
    INDEX_FILE.write_text(json.dumps(idx, indent=2), encoding="utf-8")

def _gen_note_id(name: str) -> str:
    seed = f"{name}-{datetime.now(timezone.utc).isoformat()}"
    return hashlib.sha256(seed.encode()).hexdigest()[:12]

def _load_note(note_id: str) -> str | None:
    p = NOTES_DIR / f"{note_id}.md"
    return p.read_text(encoding="utf-8") if p.exists() else None

def _save_note(note_id: str, name: str, content: str) -> None:
    (NOTES_DIR / f"{note_id}.md").write_text(content, encoding="utf-8")
    idx = _load_index()
    idx[note_id] = {
        "name": name,
        "id": note_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _save_index(idx)

def _delete_note(note_id: str) -> bool:
    p = NOTES_DIR / f"{note_id}.md"
    if p.exists():
        p.unlink()
        idx = _load_index()
        idx.pop(note_id, None)
        _save_index(idx)
        return True
    return False

def _render(content: str) -> str:
    """Render Markdown → safe-ish HTML (used internally for response)."""
    return _md.render(content)

# ── pydantic models ───────────────────────────────────────────────────────────
class NoteText(BaseModel):
    name: str = Field(..., min_length=1, max_length=200, description="Display name for the note")
    content: str = Field(..., min_length=1, description="Raw markdown text")


class GrammarResult(BaseModel):
    note_id: str
    note_name: str
    total_issues: int
    issues: list[dict[str, Any]]


class NoteListItem(BaseModel):
    id: str
    name: str
    created_at: str


# ── endpoints ─────────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
def root():
    return {"service": "Markdown Note-Taking API", "docs": "/docs", "version": "1.0.0"}


# 1. Grammar check
# ──────────────────────────────────────────────────────────────────────────────
@app.post("/notes/grammar", response_model=GrammarResult, summary="Check grammar")
async def check_grammar(
    # Body option 1
    body: NoteText | None = None,
    # Body option 2 — raw markdown string
    markdown: str | None = Query(None, description="Raw markdown text as query param"),
    # File option
    file: UploadFile | None = File(None, description="Upload a .md file"),
):
    """
    Check the grammar of note content.

    Pass content via **JSON body**, **multipart file**, or **?markdown=** query param.
    If a file is uploaded the file content wins.
    """
    content: str = ""
    note_name: str = "untitled"

    if file is not None:
        raw = await file.read()
        content = raw.decode("utf-8", errors="replace")
        note_name = file.filename or note_name
    elif body is not None:
        content = body.content
        note_name = body.name
    elif markdown is not None:
        content = markdown
    else:
        raise HTTPException(400, detail="Provide content via body, ?markdown=, or file upload")

    if content.strip():
        issues = await _check_grammar(content)
    else:
        issues = []

    return GrammarResult(
        note_id="",
        note_name=note_name,
        total_issues=len(issues),
        issues=issues,
    )


async def _check_grammar(text: str) -> list[dict]:
    """Call LanguageTool public API; return list of issue dicts."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                LANGUAGETOOL_URL,
                data={
                    "text": text,
                    "language": "en-US",
                    "enabledOnly": "0",
                },
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        return [{"message": f"Grammar service unavailable: {exc}", "category": "error"}]

    raw_issues: list[dict] = data.get("matches", [])
    return [
        {
            "message": i.get("message", ""),
            "category": i.get("rule", {}).get("category", {}).get("name", "unknown"),
            "rule_id": i.get("rule", {}).get("id", ""),
            "offset": i.get("offset", 0),
            "length": i.get("length", 0),
            "sentence": i.get("sentence", ""),
            "suggestions": [s.get("value", "") for s in i.get("replacements", [])],
        }
        for i in raw_issues
    ]


# 2. Save note
# ──────────────────────────────────────────────────────────────────────────────
@app.post("/notes", response_model=NoteListItem, status_code=201, summary="Save a note")
def save_note(body: NoteText):
    """
    Save a new markdown note. A unique `note_id` is generated and returned.
    """
    note_id = _gen_note_id(body.name)
    _save_note(note_id, body.name, body.content)
    return NoteListItem(
        id=note_id,
        name=body.name,
        created_at=datetime.now(timezone.utc).isoformat(),
    )


# 3. List notes
# ──────────────────────────────────────────────────────────────────────────────
@app.get("/notes", response_model=list[NoteListItem], summary="List all saved notes")
def list_notes():
    """Return every saved note's id, name, and creation timestamp."""
    idx = _load_index()
    return [
        NoteListItem(id=k, name=v["name"], created_at=v["created_at"])
        for k, v in sorted(idx.items(), key=lambda x: x[1]["created_at"], reverse=True)
    ]


# 4. Get rendered HTML note
# ──────────────────────────────────────────────────────────────────────────────
@app.get("/notes/{note_id}", summary="Get rendered HTML of a note")
def get_note_html(note_id: str):
    """Return the HTML-rendered version of a saved markdown note."""
    content = _load_note(note_id)
    if content is None:
        raise HTTPException(404, detail=f"Note '{note_id}' not found")
    idx = _load_index()
    meta = idx.get(note_id, {})
    return {
        "id": note_id,
        "name": meta.get("name", "untitled"),
        "created_at": meta.get("created_at", ""),
        "html": _render(content),
    }


# 5. (bonus) Get raw markdown
# ──────────────────────────────────────────────────────────────────────────────
@app.get("/notes/{note_id}/raw", response_class=PlainTextResponse, summary="Get raw markdown")
def get_note_raw(note_id: str):
    """Return the raw markdown source of a saved note."""
    content = _load_note(note_id)
    if content is None:
        raise HTTPException(404, detail=f"Note '{note_id}' not found")
    return content


# 6. (bonus) Delete a note
# ──────────────────────────────────────────────────────────────────────────────
@app.delete("/notes/{note_id}", summary="Delete a note")
def delete_note(note_id: str):
    if not _delete_note(note_id):
        raise HTTPException(404, detail=f"Note '{note_id}' not found")
    return {"message": f"Note '{note_id}' deleted"}


# ── static files ──────────────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory="/home/spoidy/workspace/md-notes-app/static"), name="static")
