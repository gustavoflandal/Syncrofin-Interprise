"""Provedor de pagamento fictício, para desenvolvimento e testes (F4).

Não move dinheiro nem fala com banco algum. É sem estado de propósito: o
`external_id` carrega o instante de criação (`sbx_<epoch>_<hex>`), então
qualquer processo (API, worker Celery) chega à mesma resposta.
"""
from __future__ import annotations

import secrets
import time
from datetime import datetime, timezone

from app.providers.payment_provider import PaymentRequest, PaymentResult

#: Segundos até a ordem fictícia ser "confirmada".
CONFIRM_AFTER_SECONDS = 5


def _created_at(external_id: str) -> float | None:
    parts = external_id.split("_")
    if len(parts) == 3 and parts[0] == "sbx":
        try:
            return float(parts[1])
        except ValueError:
            return None
    return None


class SandboxPaymentProvider:
    name = "sandbox"

    async def create_payment(self, request: PaymentRequest) -> PaymentResult:
        return PaymentResult(
            external_id=f"sbx_{time.time():.3f}_{secrets.token_hex(6)}",
            status="processing",
        )

    async def get_status(self, external_id: str) -> PaymentResult:
        created = _created_at(external_id)
        if created is None:
            return PaymentResult(external_id=external_id, status="failed", error="unknown sandbox payment")
        if time.time() - created >= CONFIRM_AFTER_SECONDS:
            return PaymentResult(
                external_id=external_id,
                status="confirmed",
                receipt_url=f"https://sandbox.invalid/receipts/{external_id}",
                completed_at=datetime.now(timezone.utc),
            )
        return PaymentResult(external_id=external_id, status="processing")

    async def cancel_payment(self, external_id: str) -> PaymentResult:
        return PaymentResult(external_id=external_id, status="cancelled")

    async def verify_webhook(self, headers: dict, body: bytes) -> bool:
        return True

    async def parse_webhook_event(self, body: dict) -> PaymentResult:
        return PaymentResult(
            external_id=str(body.get("external_id", "")),
            status=str(body.get("status", "processing")),
            error=body.get("error"),
            receipt_url=body.get("receipt_url"),
        )
