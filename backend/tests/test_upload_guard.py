"""Proteção de upload (C8): tamanho, extensão, magic bytes e CORS."""

import io

import pytest
from fastapi import HTTPException, UploadFile

from app.core.config import Settings
from app.core.upload_guard import download_headers, validate_upload

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
PDF = b"%PDF-1.7\n" + b"x" * 64


def _file(name: str, data: bytes) -> UploadFile:
    return UploadFile(file=io.BytesIO(data), filename=name)


@pytest.mark.parametrize(
    ("name", "data", "ctype"),
    [("a.jpg", JPEG, "image/jpeg"), ("a.png", PNG, "image/png"), ("a.pdf", PDF, "application/pdf")],
)
async def test_valid_files_pass(name, data, ctype):
    out, detected = await validate_upload(_file(name, data))
    assert out == data
    assert detected == ctype


async def test_csv_import_passes():
    out, detected = await validate_upload(_file("x.csv", b"name\nA\n"), category="import")
    assert out == b"name\nA\n"
    assert detected == "text/csv"


async def test_oversized_raises_413():
    big = JPEG + b"\x00" * (2 * 1024 * 1024)
    with pytest.raises(HTTPException) as exc:
        await validate_upload(_file("a.jpg", big), max_size_mb=1)
    assert exc.value.status_code == 413


async def test_logo_category_limit_is_2mb():
    big = PNG + b"\x00" * (2 * 1024 * 1024)
    with pytest.raises(HTTPException) as exc:
        await validate_upload(_file("l.png", big), category="logo")
    assert exc.value.status_code == 413


async def test_wrong_extension_raises_422():
    with pytest.raises(HTTPException) as exc:
        await validate_upload(_file("a.exe", b"MZ" + b"\x00" * 20))
    assert exc.value.status_code == 422


async def test_logo_rejects_gif_extension():
    with pytest.raises(HTTPException) as exc:
        await validate_upload(_file("a.gif", b"GIF89a" + b"\x00" * 20), category="logo")
    assert exc.value.status_code == 422


@pytest.mark.parametrize(
    ("name", "data"),
    [
        ("a.svg", b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>"),
        ("a.html", b"<html><script>alert(1)</script></html>"),
        ("a.png", b"<svg xmlns='http://www.w3.org/2000/svg'></svg>"),
        ("a.xml", b"<?xml version='1.0'?><svg xmlns='http://www.w3.org/2000/svg'/>"),
        ("a.csv", b"<!DOCTYPE html><html><body>x</body></html>"),
        ("a.pdf", b"<html><body>x</body></html>"),
    ],
)
async def test_svg_and_html_blocked_even_when_renamed(name, data):
    with pytest.raises(HTTPException) as exc:
        await validate_upload(_file(name, data))
    assert exc.value.status_code == 422


async def test_magic_byte_mismatch_detected():
    with pytest.raises(HTTPException) as exc:
        await validate_upload(_file("a.png", JPEG))
    assert exc.value.status_code == 422


async def test_binary_disguised_as_csv_rejected():
    with pytest.raises(HTTPException) as exc:
        await validate_upload(_file("a.csv", PDF), category="import")
    assert exc.value.status_code == 422


async def test_empty_file_rejected():
    with pytest.raises(HTTPException) as exc:
        await validate_upload(_file("a.png", b""))
    assert exc.value.status_code == 422


def test_cors_empty_falls_back_to_frontend_url():
    s = Settings(cors_origins="", frontend_url="https://app.example.com")
    assert s.cors_allowed_origins == ["https://app.example.com"]


def test_cors_comma_separated_list():
    s = Settings(cors_origins="https://a.example.com, https://b.example.com/ ")
    assert s.cors_allowed_origins == ["https://a.example.com", "https://b.example.com"]


def test_cors_never_allows_wildcard_with_credentials():
    s = Settings(cors_origins="*", frontend_url="https://app.example.com")
    assert s.cors_allowed_origins == ["https://app.example.com"]


def test_download_headers_inline_only_for_images_and_pdf():
    assert download_headers("a.png", "image/png")["Content-Disposition"].startswith("inline")
    assert download_headers("a.pdf", "application/pdf")["Content-Disposition"].startswith("inline")
    h = download_headers("a.xml", "application/xml")
    assert h["Content-Disposition"].startswith("attachment")
    assert h["X-Content-Type-Options"] == "nosniff"
