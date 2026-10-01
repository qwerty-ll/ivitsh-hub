"""Files attached to tasks and announcements: stored on disk under random names, served only through the API.

A file is accepted by its extension and only if its first bytes match that type, so a renamed program
or an HTML page cannot pass for a PDF. Then the content itself is checked: pictures are decoded and saved
anew (whatever was glued to them, and the EXIF with its geotags, is gone), PDFs must be whole and free of
scripts, Office files and ZIP archives must open and hold no macros, programs or escaping paths.
"""
import os
import re
import uuid
import warnings
import zipfile
from typing import AsyncIterator, Iterable, Optional, Tuple

from fastapi import HTTPException
from PIL import Image, ImageOps
from starlette.concurrency import run_in_threadpool

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
_IMAGES = {".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG", ".webp": "WEBP"}
_OFFICE = {".docx", ".xlsx", ".pptx"}
# Enough for a phone photo or a scan, refuses "decompression bombs"
MAX_IMAGE_PIXELS = 50_000_000
# What an archive may unpack to at most, and how many files it may hold
_MAX_UNPACKED = 500 * 1024 * 1024
_MAX_ENTRIES = 5000
_PDF_ACTIVE = (b"/JavaScript", b"/JS ", b"/JS(", b"/JS<", b"/Launch")
_RISKY_IN_ZIP = re.compile(
    r"\.(exe|com|bat|cmd|scr|pif|msi|msp|dll|cpl|jar|js|jse|vbs|vbe|wsf|wsh|ps1|psm1|hta|lnk|reg|apk|"
    r"sh|app|html?|xhtml|svg|docm|xlsm|pptm|dotm|xltm|potm)$",
    re.IGNORECASE,
)
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


async def save(chunks: AsyncIterator[bytes], filename: str, *, images_only: bool = False,
               max_side: Optional[int] = None) -> Tuple[str, int, str]:
    """Streams the body to disk; returns (stored name, size, content type). Rejects too big or foreign files.
    images_only takes pictures alone; max_side also shrinks them to fit that square."""
    display = clean_filename(filename)
    ext = os.path.splitext(display)[1].lower()
    if images_only and ext not in _IMAGES:
        raise HTTPException(status_code=415, detail="Нужна картинка: PNG, JPG или WebP.")
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
        size = await run_in_threadpool(inspect, ext, temp_path, max_side)
        os.replace(temp_path, final_path)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
    return stored, size, ALLOWED[ext][0]


def _refuse(detail: str) -> HTTPException:
    return HTTPException(status_code=415, detail=detail)


def _reencode_image(ext: str, path: str, max_side: Optional[int] = None) -> None:
    """Decodes the picture and writes only its pixels back: no trailing payload, no metadata."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        try:
            with Image.open(path) as img:
                if img.format != _IMAGES[ext] and not (ext in (".jpg", ".jpeg") and img.format == "MPO"):
                    raise _refuse("Содержимое файла не совпадает с его расширением")
                if img.width * img.height > MAX_IMAGE_PIXELS:
                    raise _refuse("Слишком большое изображение")
                img.seek(0)  # animations keep their first frame
                picture = ImageOps.exif_transpose(img)  # keep the orientation the EXIF described
                picture.load()
                if max_side:
                    picture.thumbnail((max_side, max_side))
        except HTTPException:
            raise
        except (OSError, ValueError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning):
            raise _refuse("Изображение повреждено или не читается")
    fmt = _IMAGES[ext]
    if fmt == "JPEG":
        picture = picture.convert("RGB")
        picture.save(path, "JPEG", quality=90, optimize=True)
    elif fmt == "PNG":
        if picture.mode not in ("1", "L", "LA", "P", "RGB", "RGBA", "I", "I;16"):
            picture = picture.convert("RGBA")
        picture.save(path, "PNG", optimize=True)
    else:
        if picture.mode not in ("RGB", "RGBA"):
            picture = picture.convert("RGBA")
        picture.save(path, "WEBP", quality=90)


def _check_pdf(path: str) -> None:
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        f.seek(max(0, size - 2048))
        if b"%%EOF" not in f.read():
            raise _refuse("PDF повреждён или недокачан")
        f.seek(0)
        tail = b""
        while True:
            block = f.read(1024 * 1024)
            if not block:
                break
            # Overlap so a marker split between blocks is still found
            window = tail + block
            if any(marker in window for marker in _PDF_ACTIVE):
                raise _refuse("PDF со встроенными скриптами не принимается — сохраните его заново как обычный PDF")
            tail = block[-16:]


def _check_zip(ext: str, path: str) -> None:
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
    except (zipfile.BadZipFile, OSError, ValueError):
        raise _refuse("Файл повреждён: архив не открывается")
    if len(entries) > _MAX_ENTRIES or sum(e.file_size for e in entries) > _MAX_UNPACKED:
        raise _refuse("Архив распаковывается в слишком большой объём")
    names = [e.filename for e in entries]
    for name in names:
        clean = name.replace("\\", "/")
        if clean.startswith("/") or ".." in clean.split("/") or re.match(r"^[A-Za-z]:", clean):
            raise _refuse("В архиве есть файлы с путями за его пределы")
    if ext in _OFFICE:
        if "[Content_Types].xml" not in names:
            raise _refuse("Документ повреждён или не является файлом Office")
        if any(n.lower().endswith("vbaproject.bin") for n in names):
            raise _refuse("Документы с макросами не принимаются")
        return
    risky = next((n for n in names if _RISKY_IN_ZIP.search(n.rstrip("/"))), None)
    if risky:
        raise _refuse(f"В архиве есть программа, скрипт или страница ({os.path.basename(risky.rstrip('/'))}) — такие архивы не принимаются")


def inspect(ext: str, path: str, max_side: Optional[int] = None) -> int:
    """Checks the content beyond the signature; pictures are rewritten in place. Returns the final size."""
    if ext in _IMAGES:
        _reencode_image(ext, path, max_side)
    elif ext == ".pdf":
        _check_pdf(path)
    else:
        _check_zip(ext, path)
    return os.path.getsize(path)


def delete(stored_names: Iterable[Optional[str]]) -> None:
    """Removes files after their rows are gone; a missing file is not an error."""
    for name in stored_names:
        if not name:
            continue
        try:
            os.remove(path_of(name))
        except (FileNotFoundError, HTTPException):
            pass
