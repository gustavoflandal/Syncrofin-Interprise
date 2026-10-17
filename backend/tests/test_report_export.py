"""Tests for G2 report exports (PDF + XLSX) and workspace logo endpoints.

Covers:
  - DRE / DFC as PDF
  - Net Worth / Income-Expenses as XLSX and PDF
  - Export permission gate (viewer must be denied)
  - Workspace logo upload / download / delete cycle
"""
import io
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.transaction import Transaction
from app.models.user import User
from app.models.workspace import Workspace


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ws_headers(auth_headers: dict, workspace: Workspace) -> dict:
    """Auth headers with the workspace context."""
    return {**auth_headers, "X-Workspace-Id": str(workspace.id)}


# ---------------------------------------------------------------------------
# PDF exports
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dre_pdf_returns_pdf(
    client: AsyncClient,
    auth_headers: dict,
    test_workspace: Workspace,
    test_account: Account,
):
    headers = _ws_headers(auth_headers, test_workspace)
    now = datetime.now(timezone.utc)
    resp = await client.get(
        f"/api/reports/dre/pdf?year={now.year}&month={now.month}",
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert "content-disposition" in resp.headers
    # A valid PDF starts with %PDF
    assert resp.content[:5] == b"%PDF-"


@pytest.mark.asyncio
async def test_dfc_pdf_returns_pdf(
    client: AsyncClient,
    auth_headers: dict,
    test_workspace: Workspace,
    test_account: Account,
):
    headers = _ws_headers(auth_headers, test_workspace)
    now = datetime.now(timezone.utc)
    resp = await client.get(
        f"/api/reports/dfc/pdf?year={now.year}&month={now.month}",
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:5] == b"%PDF-"


# ---------------------------------------------------------------------------
# XLSX exports
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_net_worth_xlsx_returns_xlsx(
    client: AsyncClient,
    auth_headers: dict,
    test_workspace: Workspace,
    test_account: Account,
):
    headers = _ws_headers(auth_headers, test_workspace)
    resp = await client.get("/api/reports/net-worth/export", headers=headers)
    assert resp.status_code == 200
    assert "spreadsheetml" in resp.headers["content-type"]
    assert "content-disposition" in resp.headers


@pytest.mark.asyncio
async def test_income_expenses_xlsx_returns_xlsx(
    client: AsyncClient,
    auth_headers: dict,
    test_workspace: Workspace,
    test_account: Account,
):
    headers = _ws_headers(auth_headers, test_workspace)
    resp = await client.get("/api/reports/income-expenses/export", headers=headers)
    assert resp.status_code == 200
    assert "spreadsheetml" in resp.headers["content-type"]


# ---------------------------------------------------------------------------
# PDF exports for Net Worth and Income/Expenses
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_net_worth_pdf_returns_pdf(
    client: AsyncClient,
    auth_headers: dict,
    test_workspace: Workspace,
    test_account: Account,
):
    headers = _ws_headers(auth_headers, test_workspace)
    resp = await client.get("/api/reports/net-worth/pdf", headers=headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:5] == b"%PDF-"


@pytest.mark.asyncio
async def test_income_expenses_pdf_returns_pdf(
    client: AsyncClient,
    auth_headers: dict,
    test_workspace: Workspace,
    test_account: Account,
):
    headers = _ws_headers(auth_headers, test_workspace)
    resp = await client.get("/api/reports/income-expenses/pdf", headers=headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:5] == b"%PDF-"


# ---------------------------------------------------------------------------
# Permission gate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_export_requires_permission(
    client: AsyncClient,
    viewer_auth_headers: dict,
):
    """A viewer (no export.read permission) must not reach the export endpoints."""
    now = datetime.now(timezone.utc)
    for path in (
        f"/api/reports/dre/pdf?year={now.year}&month={now.month}",
        f"/api/reports/dfc/pdf?year={now.year}&month={now.month}",
        "/api/reports/net-worth/export",
        "/api/reports/income-expenses/export",
        "/api/reports/net-worth/pdf",
        "/api/reports/income-expenses/pdf",
    ):
        resp = await client.get(path, headers=viewer_auth_headers)
        assert resp.status_code == 403, f"Expected 403 for viewer on {path}, got {resp.status_code}"


# ---------------------------------------------------------------------------
# Workspace logo CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_workspace_logo_upload_download_delete(
    client: AsyncClient,
    auth_headers: dict,
    test_workspace: Workspace,
):
    """Full cycle: upload a logo, download it, delete it."""
    headers = auth_headers

    # Create a minimal valid PNG (1x1 red pixel)
    import struct
    import zlib

    def _make_png():
        """Produce a minimal 1x1 RGBA PNG."""

        def _chunk(chunk_type, data):
            c = chunk_type + data
            return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

        header = b"\x89PNG\r\n\x1a\n"
        ihdr = _chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0))
        raw = b"\x00\xff\x00\x00\xff"
        idat = _chunk(b"IDAT", zlib.compress(raw))
        iend = _chunk(b"IEND", b"")
        return header + ihdr + idat + iend

    png_bytes = _make_png()

    # Mock storage provider so we don't need real object storage
    mock_storage = AsyncMock()
    mock_storage.upload = AsyncMock()
    mock_storage.download = AsyncMock(return_value=png_bytes)

    with patch("app.providers.get_storage_provider", return_value=mock_storage):
        # Upload
        resp = await client.post(
            f"/api/workspaces/{test_workspace.id}/logo",
            headers=headers,
            files={"file": ("logo.png", io.BytesIO(png_bytes), "image/png")},
        )
        # The normalise call happens outside the mock, but PIL should handle the minimal PNG
        assert resp.status_code == 200, resp.text
        assert "storage_key" in resp.json()

    with patch("app.providers.get_storage_provider", return_value=mock_storage):
        # Download
        resp = await client.get(
            f"/api/workspaces/{test_workspace.id}/logo",
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"

    with patch("app.providers.get_storage_provider", return_value=mock_storage):
        # Delete
        resp = await client.delete(
            f"/api/workspaces/{test_workspace.id}/logo",
            headers=headers,
        )
        assert resp.status_code == 204

    # After delete, download should 404 (logo_storage_key is None)
    resp = await client.get(
        f"/api/workspaces/{test_workspace.id}/logo",
        headers=headers,
    )
    assert resp.status_code == 404
