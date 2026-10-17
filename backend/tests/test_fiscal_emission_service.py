"""Testes unitários para fiscal_emission_service e nfe_parser (B1)."""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.fiscal.emission_provider import EmissionResult
from app.models.fiscal_emission import FiscalEmission, FiscalProviderConfig
from app.models.invoice import Invoice, InvoiceLine
from app.models.workspace import Workspace, WorkspaceMember
from app.services import fiscal_emission_service


# ────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────

async def _make_workspace(session: AsyncSession) -> Workspace:
    ws = Workspace(id=uuid.uuid4(), name="Empresa Teste", kind="business", locale="pt-BR")
    session.add(ws)
    await session.flush()
    return ws


async def _make_invoice(session: AsyncSession, workspace_id: uuid.UUID) -> Invoice:
    inv = Invoice(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        direction="receivable",
        origin="local",
        status="open",
        issue_date=date.today(),
        due_date=date.today(),
        currency="BRL",
        subtotal=Decimal("1000.00"),
        tax_total=Decimal("0"),
        total=Decimal("1000.00"),
    )
    session.add(inv)
    await session.flush()
    return inv


async def _make_config(session: AsyncSession, workspace_id: uuid.UUID) -> FiscalProviderConfig:
    from app.agents.services.crypto import encrypt
    cfg = FiscalProviderConfig(
        workspace_id=workspace_id,
        provider="focus_nfe",
        environment="homologation",
        api_key_encrypted=encrypt("test-api-key") or "",
        cnpj_emitente="12345678000195",
        serie_padrao="1",
    )
    session.add(cfg)
    await session.flush()
    return cfg


# ────────────────────────────────────────────────────────────────────────────
# Configuração do provedor
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_save_and_get_provider_config(async_session_maker):
    async with async_session_maker() as session:
        ws = await _make_workspace(session)
        cfg = await fiscal_emission_service.save_provider_config(
            session,
            ws.id,
            provider="focus_nfe",
            api_key="minha-chave",
            environment="homologation",
            cnpj_emitente="12345678000195",
        )
        await session.commit()

    async with async_session_maker() as session:
        result = await fiscal_emission_service.get_provider_config(session, cfg.workspace_id)
        assert result is not None
        assert result.provider == "focus_nfe"
        assert result.environment == "homologation"
        assert result.cnpj_emitente == "12345678000195"
        # A chave não é armazenada em claro
        assert result.api_key_encrypted != "minha-chave"


@pytest.mark.asyncio
async def test_save_provider_config_idempotent(async_session_maker):
    """Salvar duas vezes mantém apenas uma linha (upsert)."""
    async with async_session_maker() as session:
        ws = await _make_workspace(session)
        await fiscal_emission_service.save_provider_config(
            session, ws.id, provider="focus_nfe", api_key="k1", environment="homologation"
        )
        await session.commit()

    async with async_session_maker() as session:
        await fiscal_emission_service.save_provider_config(
            session, ws.id, provider="enotas", api_key="k2", environment="production"
        )
        await session.commit()

    async with async_session_maker() as session:
        cfg = await fiscal_emission_service.get_provider_config(session, ws.id)
        assert cfg is not None
        assert cfg.provider == "enotas"
        assert cfg.environment == "production"


# ────────────────────────────────────────────────────────────────────────────
# Emissão
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_emit_nfe_without_config_raises(async_session_maker):
    async with async_session_maker() as session:
        ws = await _make_workspace(session)
        inv = await _make_invoice(session, ws.id)
        with pytest.raises(fiscal_emission_service.FiscalError) as exc_info:
            await fiscal_emission_service.emit_nfe(session, ws.id, inv)
        assert exc_info.value.code == "no_provider_config"


@pytest.mark.asyncio
async def test_emit_nfe_success(async_session_maker):
    """Emissão bem-sucedida cria FiscalEmission com status=processing."""
    async with async_session_maker() as session:
        ws = await _make_workspace(session)
        inv = await _make_invoice(session, ws.id)
        cfg = await _make_config(session, ws.id)
        await session.flush()

        fake_result = EmissionResult(
            provider_ref="test-ref-123",
            status="processing",
        )
        with patch(
            "app.services.fiscal_emission_service.get_provider"
        ) as mock_get_prov:
            mock_provider = AsyncMock()
            mock_provider.emit = AsyncMock(return_value=fake_result)
            mock_get_prov.return_value = mock_provider

            emission = await fiscal_emission_service.emit_nfe(session, ws.id, inv)

        assert emission.status == "processing"
        assert emission.invoice_id == inv.id
        assert emission.provider == "focus_nfe"


@pytest.mark.asyncio
async def test_emit_nfe_duplicate_raises(async_session_maker):
    """Segunda emissão de uma fatura já emitida levanta FiscalError."""
    async with async_session_maker() as session:
        ws = await _make_workspace(session)
        inv = await _make_invoice(session, ws.id)
        cfg = await _make_config(session, ws.id)

        # Cria emissão já em estado 'issued'
        existing = FiscalEmission(
            workspace_id=ws.id,
            invoice_id=inv.id,
            provider="focus_nfe",
            environment="homologation",
            status="issued",
            provider_ref="old-ref",
        )
        session.add(existing)
        await session.flush()

        with pytest.raises(fiscal_emission_service.FiscalError) as exc_info:
            await fiscal_emission_service.emit_nfe(session, ws.id, inv)
        assert exc_info.value.code == "already_issued"


@pytest.mark.asyncio
async def test_refresh_emission_updates_status(async_session_maker):
    async with async_session_maker() as session:
        ws = await _make_workspace(session)
        inv = await _make_invoice(session, ws.id)
        cfg = await _make_config(session, ws.id)

        emission = FiscalEmission(
            workspace_id=ws.id,
            invoice_id=inv.id,
            provider="focus_nfe",
            environment="homologation",
            status="processing",
            provider_ref="ref-abc",
        )
        session.add(emission)
        await session.flush()

        issued_result = EmissionResult(
            provider_ref="ref-abc",
            status="issued",
            chave_acesso="35240112345678000195550010000012341123456785",
            nfe_number="1234",
            nfe_serie="1",
        )
        with patch("app.services.fiscal_emission_service.get_provider") as mock_get_prov:
            mock_provider = AsyncMock()
            mock_provider.check_status = AsyncMock(return_value=issued_result)
            mock_get_prov.return_value = mock_provider

            updated = await fiscal_emission_service.refresh_emission(session, emission)

        assert updated.status == "issued"
        assert updated.chave_acesso == "35240112345678000195550010000012341123456785"


@pytest.mark.asyncio
async def test_cancel_emission_not_issued_raises(async_session_maker):
    async with async_session_maker() as session:
        ws = await _make_workspace(session)
        inv = await _make_invoice(session, ws.id)
        cfg = await _make_config(session, ws.id)

        emission = FiscalEmission(
            workspace_id=ws.id,
            invoice_id=inv.id,
            provider="focus_nfe",
            environment="homologation",
            status="processing",
            provider_ref="ref-xyz",
        )
        session.add(emission)
        await session.flush()

        with pytest.raises(fiscal_emission_service.FiscalError) as exc_info:
            await fiscal_emission_service.cancel_emission(session, emission)
        assert exc_info.value.code == "not_issued"
