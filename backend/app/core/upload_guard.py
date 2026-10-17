"""Proteção central de uploads (C8).

Todo endpoint que recebe arquivo passa por :func:`validate_upload`: leitura em
pedaços com teto de tamanho (não carrega um arquivo gigante inteiro na memória
antes de recusar), extensão em allowlist e conferência dos *magic bytes* contra a
extensão. SVG e HTML são recusados sempre — executam script quando servidos da
mesma origem, então não importa o nome que o cliente deu ao arquivo.
"""

from __future__ import annotations

import os

from fastapi import HTTPException, UploadFile

from app.core.config import get_settings

_CHUNK = 1024 * 1024

# categoria -> (tamanho máximo em MB, extensões). "attachment" vem das settings.
_PRESETS: dict[str, tuple[int, set[str]]] = {
    # txt/ret/rem: o importador também lê CNAB, que costuma ter essas extensões.
    "import": (50, {"csv", "ofx", "qfx", "qif", "xml", "txt", "ret", "rem", "cnab"}),
    "logo": (2, {"jpg", "jpeg", "png", "webp"}),
    "knowledge": (20, {"pdf", "txt", "md", "csv"}),
}

# extensão -> (content type, assinaturas aceitas). Assinatura vazia = texto puro.
_BINARY: dict[str, tuple[str, tuple[bytes, ...]]] = {
    "jpg": ("image/jpeg", (b"\xff\xd8\xff",)),
    "jpeg": ("image/jpeg", (b"\xff\xd8\xff",)),
    "png": ("image/png", (b"\x89PNG",)),
    "gif": ("image/gif", (b"GIF8",)),
    "pdf": ("application/pdf", (b"%PDF",)),
    "zip": ("application/zip", (b"PK",)),
    "xlsx": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        (b"PK",),
    ),
}
_TEXT: dict[str, str] = {
    "csv": "text/csv",
    "txt": "text/plain",
    "md": "text/markdown",
    "ofx": "application/x-ofx",
    "qfx": "application/x-ofx",
    "qif": "application/x-qif",
    "ret": "text/plain",
    "rem": "text/plain",
    "cnab": "text/plain",
    "xml": "application/xml",
}

# Assinaturas binárias conhecidas: um arquivo "texto" que começa com uma delas é disfarce.
_ANY_BINARY_MAGIC = (b"\xff\xd8\xff", b"\x89PNG", b"GIF8", b"%PDF", b"PK", b"RIFF", b"MZ", b"\x7fELF")
_ACTIVE_MARKERS = (b"<svg", b"<html", b"<!doctype html", b"<script", b"<iframe", b"<body")


def _fail_type(detail: str = "File type not allowed") -> HTTPException:
    return HTTPException(status_code=422, detail=detail)


def _too_large(max_mb: int) -> HTTPException:
    return HTTPException(
        status_code=413,
        detail=f"File exceeds the maximum size of {max_mb}MB",
    )


def _extension(filename: str | None) -> str:
    return os.path.splitext(filename or "")[1].lstrip(".").lower()


def _looks_active(head: bytes) -> bool:
    low = head.lstrip(b"\xef\xbb\xbf \t\r\n").lower()
    return any(m in low[:2048] for m in _ACTIVE_MARKERS)


def _webp(head: bytes) -> bool:
    return head[:4] == b"RIFF" and head[8:12] == b"WEBP"


def _heic(head: bytes) -> bool:
    return head[4:8] == b"ftyp"


def sniff_content_type(ext: str, data: bytes) -> str:
    """Confere o conteúdo contra a extensão e devolve o content type; 422 se não bater."""
    head = data[:4096]
    if _looks_active(head):
        raise _fail_type()
    if ext == "webp":
        if not _webp(head):
            raise _fail_type()
        return "image/webp"
    if ext == "heic":
        if not _heic(head):
            raise _fail_type()
        return "image/heic"
    if ext in _BINARY:
        ctype, sigs = _BINARY[ext]
        if not any(head.startswith(s) for s in sigs):
            raise _fail_type()
        return ctype
    if ext in _TEXT:
        if head.startswith(_ANY_BINARY_MAGIC) or b"\x00" in head:
            raise _fail_type()
        if ext == "xml" and not head.lstrip(b"\xef\xbb\xbf \t\r\n").startswith(b"<"):
            raise _fail_type()
        return _TEXT[ext]
    # extensão permitida mas sem regra de assinatura: recusa por segurança
    raise _fail_type()


def parse_extensions(raw: str) -> set[str]:
    return {e.strip().lower().lstrip(".") for e in raw.split(",") if e.strip()}


async def validate_upload(
    file: UploadFile,
    *,
    max_size_mb: int | None = None,
    allowed_extensions: set[str] | None = None,
    category: str = "attachment",
) -> tuple[bytes, str]:
    """Lê, limita e valida um upload. Devolve ``(bytes, content_type detectado)``.

    413 para arquivo acima do teto, 422 para tipo não permitido ou conteúdo que
    não corresponde à extensão.
    """
    settings = get_settings()
    if category == "attachment":
        preset_mb = settings.storage_max_file_size_mb
        preset_ext = parse_extensions(settings.storage_allowed_extensions)
    elif category in _PRESETS:
        preset_mb, preset_ext = _PRESETS[category]
    else:
        raise ValueError(f"unknown upload category: {category}")

    limit_mb = max_size_mb if max_size_mb is not None else preset_mb
    allowed = {e.lower().lstrip(".") for e in allowed_extensions} if allowed_extensions is not None else preset_ext

    ext = _extension(file.filename)
    # svg/html/htm nunca entram, mesmo que alguém os ponha na allowlist
    if not ext or ext in {"svg", "svgz", "html", "htm", "xhtml"} or ext not in allowed:
        raise _fail_type()

    limit = limit_mb * 1024 * 1024
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise _too_large(limit_mb)
        chunks.append(chunk)
    data = b"".join(chunks)
    if not data:
        raise _fail_type("Empty file")

    return data, sniff_content_type(ext, data)


# --- Servir arquivos de volta -------------------------------------------------

_INLINE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp", "application/pdf"}


def download_headers(filename: str, content_type: str) -> dict[str, str]:
    """Cabeçalhos seguros: inline só para imagem/PDF; sempre nosniff."""
    disposition = "inline" if content_type.lower() in _INLINE_TYPES else "attachment"
    safe = filename.replace('"', "").replace("\r", "").replace("\n", "")
    return {
        "Content-Disposition": f'{disposition}; filename="{safe}"',
        "X-Content-Type-Options": "nosniff",
    }
