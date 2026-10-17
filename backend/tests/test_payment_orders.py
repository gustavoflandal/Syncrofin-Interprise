"""Tests for payment initiation with dual approval (F4)."""
import uuid as _uuid
from decimal import Decimal

import bcrypt as _bcrypt
import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.account import Account
from app.models.payment_order import PaymentApprovalEvent
from app.models.transaction import Transaction
from app.models.user import User
from app.services import payment_service as svc


async def _user(session, email):
    hashed = _bcrypt.hashpw(b"pass", _bcrypt.gensalt()).decode()
    u = User(id=_uuid.uuid4(), email=email, hashed_password=hashed, is_active=True, is_verified=True)
    session.add(u)
    await session.flush()
    return u


@pytest.fixture
async def approver1(session):
    return await _user(session, "pay_a1@x.com")


@pytest.fixture
async def approver2(session):
    return await _user(session, "pay_a2@x.com")


@pytest.fixture
async def sender(session):
    return await _user(session, "pay_sender@x.com")


@pytest.fixture
async def pay_account(session, test_user, test_workspace):
    acc = Account(
        id=_uuid.uuid4(), user_id=test_user.id, workspace_id=test_workspace.id,
        name="Conta Pagamentos", type="checking", currency="BRL",
    )
    session.add(acc)
    await session.flush()
    return acc


def _pix(**extra):
    data = {
        "method": "pix", "amount": Decimal("150.00"), "beneficiary_name": "Fornecedor LTDA",
        "pix_key": "fornecedor@x.com", "pix_key_type": "email",
    }
    data.update(extra)
    return data


async def _pending(session, ws, creator, **extra):
    order, _ = await svc.create_order(session, ws.id, creator.id, _pix(**extra))
    await svc.submit_for_approval(session, order.id, creator.id)
    return order


async def _approved(session, ws, creator, a1, a2, **extra):
    order = await _pending(session, ws, creator, **extra)
    await svc.approve(session, order.id, a1.id)
    await svc.approve(session, order.id, a2.id)
    return order


async def _code(coro):
    with pytest.raises(HTTPException) as exc:
        await coro
    return exc.value.status_code


@pytest.mark.asyncio
async def test_create_order_is_draft(session, test_workspace, test_user):
    order, created = await svc.create_order(session, test_workspace.id, test_user.id, _pix())
    assert created
    assert order.status == "draft"
    assert order.approval_status == "none"
    assert order.provider == "sandbox"


@pytest.mark.asyncio
async def test_validation_requires_method_fields(session, test_workspace, test_user):
    assert await _code(svc.create_order(
        session, test_workspace.id, test_user.id, {"method": "pix", "amount": Decimal("1"), "beneficiary_name": "X"}
    )) == 422
    assert await _code(svc.create_order(
        session, test_workspace.id, test_user.id, {"method": "ted", "amount": Decimal("1"), "beneficiary_name": "X"}
    )) == 422


@pytest.mark.asyncio
async def test_submit_moves_to_pending_approval(session, test_workspace, test_user):
    order = await _pending(session, test_workspace, test_user)
    assert order.status == "pending_approval"
    assert order.approval_status == "pending"


@pytest.mark.asyncio
async def test_first_approval_keeps_pending(session, test_workspace, test_user, approver1):
    order = await _pending(session, test_workspace, test_user)
    await svc.approve(session, order.id, approver1.id)
    assert order.status == "pending_approval"
    assert order.first_approver_id == approver1.id
    assert order.second_approver_id is None


@pytest.mark.asyncio
async def test_creator_cannot_approve_own_order(session, test_workspace, test_user):
    order = await _pending(session, test_workspace, test_user)
    assert await _code(svc.approve(session, order.id, test_user.id)) == 403


@pytest.mark.asyncio
async def test_second_approval_by_different_person_approves(
    session, test_workspace, test_user, approver1, approver2
):
    order = await _approved(session, test_workspace, test_user, approver1, approver2)
    assert order.status == "approved"
    assert order.approval_status == "approved"
    assert order.second_approver_id == approver2.id


@pytest.mark.asyncio
async def test_same_person_cannot_approve_twice(session, test_workspace, test_user, approver1):
    order = await _pending(session, test_workspace, test_user)
    await svc.approve(session, order.id, approver1.id)
    assert await _code(svc.approve(session, order.id, approver1.id)) == 403
    assert order.status == "pending_approval"


@pytest.mark.asyncio
async def test_reject_returns_to_draft_and_clears_approvals(session, test_workspace, test_user, approver1, approver2):
    order = await _pending(session, test_workspace, test_user)
    await svc.approve(session, order.id, approver1.id)
    await svc.reject(session, order.id, approver2.id, "valor errado")
    assert order.status == "draft"
    assert order.first_approver_id is None
    events = (await session.execute(
        select(PaymentApprovalEvent.action).where(PaymentApprovalEvent.payment_order_id == order.id)
    )).scalars().all()
    assert sorted(events) == ["approve", "reject", "submit"]


@pytest.mark.asyncio
async def test_send_requires_approved_status(session, test_workspace, test_user, sender):
    order = await _pending(session, test_workspace, test_user)
    assert await _code(svc.send_payment(session, order.id, sender.id)) == 409


@pytest.mark.asyncio
async def test_send_segregation(session, test_workspace, test_user, approver1, approver2, sender):
    order = await _approved(session, test_workspace, test_user, approver1, approver2)
    for u in (test_user, approver1, approver2):
        assert await _code(svc.send_payment(session, order.id, u.id)) == 403
    assert order.status == "approved"


@pytest.mark.asyncio
async def test_send_via_sandbox(session, test_workspace, test_user, approver1, approver2, sender):
    order = await _approved(session, test_workspace, test_user, approver1, approver2)
    await svc.send_payment(session, order.id, sender.id)
    assert order.status == "sent"
    assert order.sent_by_user_id == sender.id
    assert order.external_id.startswith("sbx_")


@pytest.mark.asyncio
async def test_webhook_confirms_and_creates_transaction(
    session, test_workspace, test_user, approver1, approver2, sender, pay_account
):
    order = await _approved(
        session, test_workspace, test_user, approver1, approver2, source_account_id=pay_account.id
    )
    await svc.send_payment(session, order.id, sender.id)
    # O sandbox confirma 5s depois de criada; recua o instante para o teste não esperar.
    order.external_id = "sbx_1000.000_abcdef"
    await session.flush()

    result = await svc.handle_webhook(
        session, test_workspace.id, "sandbox", {"external_id": order.external_id, "status": "confirmed"}
    )
    assert result.status == "confirmed"
    assert result.transaction_id is not None
    tx = await session.get(Transaction, result.transaction_id)
    assert tx.type == "debit"
    assert tx.amount == Decimal("150.00")
    assert tx.account_id == pay_account.id

    # Repetir o webhook não gera segundo lançamento.
    await svc.handle_webhook(
        session, test_workspace.id, "sandbox", {"external_id": order.external_id, "status": "confirmed"}
    )
    count = (await session.execute(
        select(Transaction).where(Transaction.account_id == pay_account.id)
    )).scalars().all()
    assert len(count) == 1


@pytest.mark.asyncio
async def test_webhook_confirmation_is_requeried(
    session, test_workspace, test_user, approver1, approver2, sender, pay_account
):
    """Um webhook que diz 'confirmed' para um pagamento ainda em processamento não baixa nada."""
    order = await _approved(
        session, test_workspace, test_user, approver1, approver2, source_account_id=pay_account.id
    )
    await svc.send_payment(session, order.id, sender.id)
    await svc.handle_webhook(
        session, test_workspace.id, "sandbox", {"external_id": order.external_id, "status": "confirmed"}
    )
    assert order.status == "sent"
    assert order.transaction_id is None


@pytest.mark.asyncio
async def test_check_status_confirms(
    session, test_workspace, test_user, approver1, approver2, sender, pay_account
):
    order = await _approved(
        session, test_workspace, test_user, approver1, approver2, source_account_id=pay_account.id
    )
    await svc.send_payment(session, order.id, sender.id)
    await svc.check_status(session, order.id)
    assert order.status == "sent"  # menos de 5s
    order.external_id = "sbx_1000.000_abcdef"
    await svc.check_status(session, order.id)
    assert order.status == "confirmed"
    assert order.transaction_id is not None


@pytest.mark.asyncio
async def test_cancel_draft_and_terminal(session, test_workspace, test_user):
    order, _ = await svc.create_order(session, test_workspace.id, test_user.id, _pix())
    await svc.cancel(session, order.id, test_user.id)
    assert order.status == "cancelled"
    assert await _code(svc.cancel(session, order.id, test_user.id)) == 409


@pytest.mark.asyncio
async def test_cancel_sent_order_goes_through_provider(
    session, test_workspace, test_user, approver1, approver2, sender
):
    order = await _approved(session, test_workspace, test_user, approver1, approver2)
    await svc.send_payment(session, order.id, sender.id)
    await svc.cancel(session, order.id, test_user.id)
    assert order.status == "cancelled"


@pytest.mark.asyncio
async def test_idempotency_key_prevents_duplicates(session, test_workspace, test_user):
    first, created1 = await svc.create_order(
        session, test_workspace.id, test_user.id, _pix(idempotency_key="invoice-42")
    )
    second, created2 = await svc.create_order(
        session, test_workspace.id, test_user.id, _pix(idempotency_key="invoice-42")
    )
    assert created1 and not created2
    assert first.id == second.id


@pytest.mark.asyncio
async def test_only_draft_can_be_edited(session, test_workspace, test_user):
    order = await _pending(session, test_workspace, test_user)
    assert await _code(svc.update_order(
        session, order.id, test_workspace.id, test_user.id, {"amount": Decimal("1.00")}
    )) == 409


@pytest.mark.asyncio
async def test_list_orders_filters_and_paginates(session, test_workspace, test_user):
    for i in range(3):
        await svc.create_order(session, test_workspace.id, test_user.id, _pix(idempotency_key=f"k{i}"))
    await _pending(session, test_workspace, test_user, idempotency_key="pend")
    rows, total = await svc.list_orders(session, test_workspace.id, "draft", 1, 2)
    assert total == 3 and len(rows) == 2
    rows, total = await svc.list_orders(session, test_workspace.id, "pending_approval", 1, 20)
    assert total == 1


def test_sandbox_provider_satisfies_protocol():
    from app.providers.payment_provider import PaymentProvider
    from app.providers.sandbox_payment import SandboxPaymentProvider

    assert isinstance(SandboxPaymentProvider(), PaymentProvider)


@pytest.mark.asyncio
async def test_api_requires_payment_permissions(client, auth_headers, viewer_auth_headers):
    body = {**{k: (str(v) if isinstance(v, Decimal) else v) for k, v in _pix().items()}}
    created = await client.post("/api/payments", json=body, headers=auth_headers)
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "draft"
    listed = await client.get("/api/payments", headers=auth_headers)
    assert listed.json()["total"] == 1
    denied = await client.post("/api/payments", json=body, headers=viewer_auth_headers)
    assert denied.status_code == 403
