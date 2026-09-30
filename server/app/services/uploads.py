"""Files attached to tasks and announcements: stored on disk under random names, served only through the API.

A file is accepted by its extension and only if its first bytes match that type, so a renamed program
or an HTML page cannot pass for a PDF.
"""
import os
import re
import uuid
from typing import AsyncIterator, Iterable, Optional, Tuple

from fastapi import HTTPException

from app.core.config import settings

# extension -> (content type, the signature the file must start with)
_ZIP = b"PK\x03\x04"
ALLOWED = {
    ".pdf": ("application/pdf", (b"%PDF",)),
    ".png": ("image/png", (b"\x89PNG\r\n\x1a\n",)),
    ".jpg": ("image/jpeg", (b"\xff\xd8\xff",)),
    ".jpeg": ("image/jpeg", (b"\xff\xd8\xff",)),
    ".webp": ("image/webp", (b"RIFF",)),
    ".docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", (_ZIP,)),
    ".xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", (_ZIP,)),
    ".pptx": ("application/vnd.openxmlformats-officedocument.presentationml.presentation", (_ZIP,)),
    ".zip": ("application/zip", (_ZIP,)),
}
ALLOWED_HINT = "PDF, изображения (PNG, JPG, WebP), документы Word, Excel, PowerPoint и ZIP"
_STORED_NAME = re.compile(r"^[0-9a-f]{32}\.[a-z]{3,4}$")


def clean_filename(name: str) -> str:
    """A display name without directories or control characters."""
    name = os.path.basename((name or "").replace("\\", "/")).strip()
    name = re.sub(r"[\x00-\x1f<>:\"|?*]", "_", name)
    return name[:150] or "файл"


def _check_signature(ext: str, head: bytes) -> bool:
    if ext == ".webp":
        return head[:4] == b"RIFF" and head[8:12] == b"WEBP"
    return any(head.startswith(sig) for sig in ALLOWED[ext][1])


def check_declared_size(request) -> None:
    """Refuses a body that announces itself as too big before reading any of it."""
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"Файл больше {settings.MAX_UPLOAD_MB} МБ")


def path_of(stored_name: str) -> str:
    if not _STORED_NAME.match(stored_name or ""):
        raise HTTPException(status_code=404, detail="Файл не найден")
    return os.path.join(settings.UPLOAD_DIR, stored_name)


async def save(chunks: AsyncIterator[bytes], filename: str) -> Tuple[str, int, str]:
    """Streams the body to disk; returns (stored name, size, content type). Rejects too big or foreign files."""
    display = clean_filename(filename)
    ext = os.path.splitext(display)[1].lower()
    if ext not in ALLOWED:
        raise HTTPException(status_code=415, detail=f"Такой тип файла не подходит. Можно: {ALLOWED_HINT}.")
    limit = settings.MAX_UPLOAD_MB * 1024 * 1024
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    stored = f"{uuid.uuid4().hex}{ext}"
    final_path = os.path.join(settings.UPLOAD_DIR, stored)
    temp_path = final_path + ".part"
    size, head = 0, b""
    try:
        with open(temp_path, "wb") as out:
            async for chunk in chunks:
                size += len(chunk)
                if size > limit:
                    raise HTTPException(status_code=413, detail=f"Файл больше {settings.MAX_UPLOAD_MB} МБ")
                if len(head) < 16:
                    head += chunk[:16 - len(head)]
                out.write(chunk)
        if size == 0:
            raise HTTPException(status_code=400, detail="Пустой файл")
        if not _check_signature(ext, head):
            raise HTTPException(status_code=415, detail="Содержимое файла не совпадает с его расширением")
        os.replace(temp_path, final_path)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
    return stored, size, ALLOWED[ext][0]


def delete(stored_names: Iterable[Optional[str]]) -> None:
    """Removes files after their rows are gone; a missing file is not an error."""
    for name in stored_names:
        if not name:
            continue
        try:
            os.remove(path_of(name))
        except (FileNotFoundError, HTTPException):
            pass
