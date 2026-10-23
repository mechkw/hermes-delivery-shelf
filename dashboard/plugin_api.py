"""Delivery Shelf: profile-bound metadata and explicitly registered safe files.

Mounted only by Hermes' authenticated plugin API loader. Never run standalone.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
import json
import os
from pathlib import Path, PurePosixPath
import re
import sqlite3
import stat
import time
from typing import Literal
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

PLUGIN_ID = "delivery-shelf"
VERSION = "0.1.0"
MAX_FILE = 10 * 1024 * 1024
TEXT_TYPES = {".txt", ".md", ".csv"}
FILE_TYPES = TEXT_TYPES | {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".gif"}
SENSITIVE = re.compile(r"(^|[._ -])(secret[s]?|credential[s]?|token[s]?|password[s]?|private|id_rsa|id_ed25519|auth|config|wallet|backup|env|db|database[s]?|key[s]?)([._ -]|$)", re.I)
KINDS = Literal["document", "image", "report", "code", "other"]


class FileRef(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    root: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    path: str = Field(min_length=1, max_length=1024)

    @field_validator("path")
    @classmethod
    def safe_path(cls, value):
        parts = value.split("/")
        if "\\" in value or any(ord(c) < 32 for c in value) or any(p in ("", ".", "..") or p.startswith(".") or ":" in p for p in parts):
            raise ValueError("Use a relative path without hidden files or traversal")
        if any(SENSITIVE.search(p) for p in parts) or PurePosixPath(value).suffix.lower() not in FILE_TYPES:
            raise ValueError("This file name or type is not available for delivery")
        return value


class EntryInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=4000)
    kind: KINDS = "document"
    project: str = Field(default="", max_length=100)
    tags: list[str] = Field(default_factory=list, max_length=20)
    file: FileRef | None = None
    session_id: str = Field(default="", max_length=160, pattern=r"^[A-Za-z0-9_.:-]*$")

    @field_validator("title", "project")
    @classmethod
    def clean_text(cls, value, info):
        value = value.strip()
        if info.field_name == "title" and not value:
            raise ValueError("Title is required")
        if any(ord(c) < 32 for c in value):
            raise ValueError("Control characters are not allowed")
        return value

    @field_validator("tags")
    @classmethod
    def clean_tags(cls, values):
        result = []
        for value in values:
            value = value.strip().lower()
            if not value or len(value) > 40 or any(ord(c) < 32 for c in value):
                raise ValueError("Tags must be 1–40 printable characters")
            if value not in result:
                result.append(value)
        return result


class EntryUpdate(EntryInput):
    revision: int = Field(ge=1)


def bound_home() -> Path:
    from hermes_constants import get_hermes_home
    return Path(get_hermes_home()).absolute()


def profile_name(home: Path) -> str:
    return home.name if home.parent.name == "profiles" else "default"


def data_dir(home: Path) -> Path:
    path = home / "plugin-data" / PLUGIN_ID
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


def allowed_roots(home: Path) -> dict[str, Path]:
    """Operator-owned policy, not writable via API/tool; malformed means deny."""
    policy = data_dir(home) / "allowed-roots.json"
    try:
        # Only genuine absence enables defaults. lstat does not follow a broken
        # symlink, and non-regular policies (including FIFOs) are never read.
        try:
            meta = policy.lstat()
        except FileNotFoundError:
            return {"workspaces": home / "workspaces", "workspace": home / "workspace"}
        if not stat.S_ISREG(meta.st_mode) or meta.st_size > 16384:
            raise ValueError()
        value = json.loads(policy.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or len(value) > 20:
            raise ValueError()
        roots = {}
        for key, raw in value.items():
            if not isinstance(key, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", key) or not isinstance(raw, str):
                raise ValueError()
            path = Path(raw).expanduser()
            if not path.is_absolute() or ".." in path.parts or path == Path(path.anchor):
                raise ValueError()
            roots[key] = path
        return roots
    except (OSError, ValueError, TypeError):
        raise HTTPException(503, "File root policy is invalid; ask the operator to repair it") from None


def open_file(home: Path, ref: FileRef):
    """Walk from filesystem root with dir_fd + O_NOFOLLOW, including root ancestors.

    Keep the final descriptor for reads: no check-then-reopen race. On platforms
    lacking these primitives file access is disabled, metadata remains usable.
    """
    roots = allowed_roots(home)
    if ref.root not in roots:
        raise HTTPException(403, "File root is not approved")
    if os.open not in os.supports_dir_fd or not hasattr(os, "O_NOFOLLOW"):
        raise HTTPException(501, "Safe file access is unavailable on this platform")
    path = roots[ref.root] / ref.path
    fd = None
    try:
        fd = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        for part in path.parts[1:-1]:
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        final = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        try:
            meta = os.fstat(final)
            if not stat.S_ISREG(meta.st_mode) or meta.st_nlink != 1:
                raise HTTPException(403, "Only ordinary non-linked files can be delivered")
            if meta.st_size > MAX_FILE:
                raise HTTPException(413, "File exceeds the 10 MiB delivery limit")
            return os.fdopen(final, "rb")
        except BaseException:
            os.close(final)
            raise
    except OSError:
        raise HTTPException(403, "File is unavailable or its path is unsafe") from None
    finally:
        if fd is not None:
            os.close(fd)


class Store:
    def __init__(self, home: Path):
        self.home = home
        self.path = data_dir(home) / "shelf.sqlite3"
        # SQLite state is not served by the file API.
        if self.path.is_symlink():
            raise HTTPException(503, "Catalog storage is unsafe")
        with self.connect() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS entries (id TEXT PRIMARY KEY, payload TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL, revision INTEGER NOT NULL)")
            conn.execute("CREATE INDEX IF NOT EXISTS entries_updated ON entries(updated DESC)")
        os.chmod(self.path, 0o600)

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    @staticmethod
    def decode(row):
        return {**json.loads(row["payload"]), "id": row["id"], "created": row["created"], "updated": row["updated"], "revision": row["revision"]}

    def get(self, entry_id):
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM entries WHERE id=?", (entry_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Delivery not found")
        return self.decode(row)

    def search(self, q="", tag="", kind="", project="", limit=50, offset=0):
        # JSON1 is part of the supported Python SQLite build. Parameter binding
        # prevents injection; instr makes %, _ and quotes literal search text.
        clauses, params = [], []
        if q:
            clauses.append("instr(lower(json_extract(payload,'$.title') || ' ' || json_extract(payload,'$.description')),lower(?)) > 0")
            params.append(q)
        for key, value in (("kind", kind), ("project", project)):
            if value:
                clauses.append(f"json_extract(payload,'$.{key}') = ?")
                params.append(value)
        if tag:
            clauses.append("EXISTS (SELECT 1 FROM json_each(payload,'$.tags') WHERE value=?)")
            params.append(tag.lower())
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self.connect() as conn:
            total = conn.execute("SELECT count(*) FROM entries" + where, params).fetchone()[0]
            rows = conn.execute("SELECT * FROM entries" + where + " ORDER BY updated DESC,id LIMIT ? OFFSET ?", [*params, limit, offset]).fetchall()
        return {"items": [self.decode(row) for row in rows], "total": total, "limit": limit, "offset": offset}

    def create(self, entry: EntryInput):
        if entry.file:
            with open_file(self.home, entry.file):
                pass
        entry_id, now = uuid.uuid4().hex, time.time()
        with self.connect() as conn:
            conn.execute("INSERT INTO entries VALUES (?,?,?,?,1)", (entry_id, entry.model_dump_json(), now, now))
        return self.get(entry_id)

    def update(self, entry_id, entry: EntryUpdate):
        current = self.get(entry_id)
        # Unchanged references can be edited or removed even if the file vanished.
        if entry.file and entry.file.model_dump() != current["file"]:
            with open_file(self.home, entry.file):
                pass
        payload = entry.model_dump(exclude={"revision"})
        with self.connect() as conn:
            changed = conn.execute("UPDATE entries SET payload=?,updated=?,revision=revision+1 WHERE id=? AND revision=?", (json.dumps(payload), time.time(), entry_id, entry.revision)).rowcount
        if not changed:
            raise HTTPException(409, "Delivery changed elsewhere; refresh before saving")
        return self.get(entry_id)

    def delete(self, entry_id, revision):
        self.get(entry_id)
        with self.connect() as conn:
            changed = conn.execute("DELETE FROM entries WHERE id=? AND revision=?", (entry_id, revision)).rowcount
        if not changed:
            raise HTTPException(409, "Delivery changed elsewhere; refresh before removing")


def request_store(profile: str | None = Query(default=None)):
    home = bound_home()
    if profile is not None and profile != profile_name(home):
        raise HTTPException(409, "Profile does not match the host-bound profile; reconnect to the intended profile")
    return Store(home)


router = APIRouter()


@router.get("/status")
def status(response: Response, store: Store = Depends(request_store)):
    response.headers["Cache-Control"] = "no-store"
    return {"version": VERSION, "profile": profile_name(store.home), "roots": list(allowed_roots(store.home)), "file_types": sorted(FILE_TYPES), "max_file_bytes": MAX_FILE}


@router.get("/entries")
def entries(response: Response, q: str = Query("", max_length=200), tag: str = Query("", max_length=40), kind: str = Query("", max_length=40), project: str = Query("", max_length=100), limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0, le=1000000), store: Store = Depends(request_store)):
    response.headers["Cache-Control"] = "no-store"
    return store.search(q, tag, kind, project, limit, offset)


@router.post("/entries", status_code=201)
def create(entry: EntryInput, store: Store = Depends(request_store)):
    return store.create(entry)


@router.get("/entries/{entry_id}")
def get_entry(entry_id: str, response: Response, store: Store = Depends(request_store)):
    response.headers["Cache-Control"] = "no-store"
    return store.get(entry_id)


@router.put("/entries/{entry_id}")
def update(entry_id: str, entry: EntryUpdate, store: Store = Depends(request_store)):
    return store.update(entry_id, entry)


@router.delete("/entries/{entry_id}")
def delete(entry_id: str, revision: int = Query(..., ge=1), store: Store = Depends(request_store)):
    store.delete(entry_id, revision)
    return {"deleted": entry_id, "files_deleted": False}


@router.get("/entries/{entry_id}/file")
def file_content(entry_id: str, response: Response, preview: bool = False, store: Store = Depends(request_store)):
    entry = store.get(entry_id)
    if not entry["file"]:
        raise HTTPException(404, "This delivery has no registered file")
    ref = FileRef.model_validate(entry["file"])
    if preview and PurePosixPath(ref.path).suffix.lower() not in TEXT_TYPES:
        raise HTTPException(415, "Only plain-text previews are available; download this file instead")
    with open_file(store.home, ref) as stream:
        content = stream.read(65537 if preview else MAX_FILE + 1)
    if not preview and len(content) > MAX_FILE:
        raise HTTPException(413, "File exceeds the 10 MiB delivery limit")
    response.headers.update({"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "Content-Security-Policy": "default-src 'none'; sandbox"})
    if preview:
        return {"text": content[:65536].decode("utf-8", errors="replace"), "truncated": len(content) > 65536}
    return {"name": PurePosixPath(ref.path).name, "base64": base64.b64encode(content).decode("ascii"), "media_type": "application/octet-stream"}
