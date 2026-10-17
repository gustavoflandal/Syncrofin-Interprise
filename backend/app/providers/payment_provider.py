"""Protocol para provedores de iniciação de pagamento PIX/TED (F4).

Diferente dos provedores bancários de leitura (Pluggy, Enable Banking), estes
movimentam dinheiro. Por isso o contrato exige uma chave de idempotência em
`create_payment`: reenviar a mesma ordem nunca pode pagar duas vezes.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional, Protocol, runtime_checkable

#: Estados normalizados devolvidos por qualquer adaptador.
PROVIDER_STATUSES = frozenset({"pending", "processing", "confirmed", "failed", "cancelled"})


@dataclass
class PaymentRequest:
    idempotency_key: str
    amount: Decimal
    currency: str
    method: str  # "pix" | "ted"
    # PIX
    pix_key: Optional[str] = None
    pix_key_type: Optional[str] = None  # cpf | cnpj | email | phone | random
    # TED
    bank_code: Optional[str] = None
    branch: Optional[str] = None
    account_number: Optional[str] = None
    account_type: Optional[str] = None  # checking | savings
    # Favorecido
    beneficiary_name: Optional[str] = None
    beneficiary_tax_id: Optional[str] = None
    description: str = ""


@dataclass
class PaymentResult:
    external_id: str
    status: str  # ver PROVIDER_STATUSES
    error: Optional[str] = None
    receipt_url: Optional[str] = None
    completed_at: Optional[datetime] = None


@runtime_checkable
class PaymentProvider(Protocol):
    """Interface que todo adaptador de iniciação de pagamento deve implementar."""

    name: str

    async def create_payment(self, request: PaymentRequest) -> PaymentResult: ...

    async def get_status(self, external_id: str) -> PaymentResult: ...

    async def cancel_payment(self, external_id: str) -> PaymentResult: ...

    async def verify_webhook(self, headers: dict, body: bytes) -> bool: ...

    async def parse_webhook_event(self, body: dict) -> PaymentResult: ...
