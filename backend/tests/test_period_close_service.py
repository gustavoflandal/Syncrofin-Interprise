import pytest
from datetime import date
from app.models.period_close import PeriodClose
from app.services import period_close_service
from fastapi import HTTPException


@pytest.mark.asyncio
async def test_close_period_creates_record(session, test_workspace, test_user):
    pc = await period_close_service.close_period(
        session, test_workspace.id, test_user.id, 2026, 1, "Mês encerrado"
    )
    assert pc.year == 2026
    assert pc.month == 1
    assert pc.reopened_at is None


@pytest.mark.asyncio
async def test_is_period_closed_true(session, test_workspace, test_user):
    await period_close_service.close_period(
        session, test_workspace.id, test_user.id, 2026, 1, None
    )
    assert await period_close_service.is_period_closed(
        session, test_workspace, date(2026, 1, 15)
    ) is True


@pytest.mark.asyncio
async def test_is_period_closed_false_for_open_month(session, test_workspace, test_user):
    await period_close_service.close_period(
        session, test_workspace.id, test_user.id, 2026, 1, None
    )
    assert await period_close_service.is_period_closed(
        session, test_workspace, date(2026, 2, 1)
    ) is False


@pytest.mark.asyncio
async def test_close_already_closed_raises_409(session, test_workspace, test_user):
    await period_close_service.close_period(
        session, test_workspace.id, test_user.id, 2026, 1, None
    )
    with pytest.raises(HTTPException) as exc:
        await period_close_service.close_period(
            session, test_workspace.id, test_user.id, 2026, 1, None
        )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_reopen_period(session, test_workspace, test_user):
    await period_close_service.close_period(
        session, test_workspace.id, test_user.id, 2026, 1, None
    )
    pc = await period_close_service.reopen_period(
        session, test_workspace.id, test_user.id, 2026, 1, "Correção necessária"
    )
    assert pc.reopened_at is not None
    assert pc.reopen_reason == "Correção necessária"


@pytest.mark.asyncio
async def test_is_period_closed_false_after_reopen(session, test_workspace, test_user):
    await period_close_service.close_period(
        session, test_workspace.id, test_user.id, 2026, 1, None
    )
    await period_close_service.reopen_period(
        session, test_workspace.id, test_user.id, 2026, 1, None
    )
    assert await period_close_service.is_period_closed(
        session, test_workspace, date(2026, 1, 15)
    ) is False


@pytest.mark.asyncio
async def test_reopen_non_existent_raises_404(session, test_workspace, test_user):
    with pytest.raises(HTTPException) as exc:
        await period_close_service.reopen_period(
            session, test_workspace.id, test_user.id, 2026, 3, None
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_reclose_after_reopen(session, test_workspace, test_user):
    """Re-closing an already-reopened period must succeed without IntegrityError."""
    await period_close_service.close_period(
        session, test_workspace.id, test_user.id, 2026, 1, None
    )
    await period_close_service.reopen_period(
        session, test_workspace.id, test_user.id, 2026, 1, None
    )
    # Re-close should succeed without UniqueViolation / IntegrityError
    pc = await period_close_service.close_period(
        session, test_workspace.id, test_user.id, 2026, 1, "Re-fechado"
    )
    assert pc.reopened_at is None
    assert pc.reason == "Re-fechado"


@pytest.mark.asyncio
async def test_close_by_effective_date(session, test_workspace, test_user):
    test_workspace.period_close_by = "effective_date"
    await period_close_service.close_period(
        session, test_workspace.id, test_user.id, 2026, 1, None
    )
    # A transaction with date=2026-02-01 but effective_date=2026-01-31 should be blocked
    assert await period_close_service.is_period_closed(
        session, test_workspace, date(2026, 1, 31), effective_date=date(2026, 1, 31)
    ) is True
    # date=2026-02-01 with effective_date=2026-02-01 should be open
    assert await period_close_service.is_period_closed(
        session, test_workspace, date(2026, 2, 1), effective_date=date(2026, 2, 1)
    ) is False
