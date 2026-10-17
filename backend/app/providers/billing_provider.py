"""Protocol para provedores de cobrança por boleto/PIX (B2)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional, Protocol, runtime_checkable


@dataclass
class ChargeRequest:
    """Dados mínimos para criar uma cobrança."""
    method: str            # 'boleto' | 'pix'
    amount: Decimal
    due_date: date
    # Dados do pagador
    payer_name: str
    payer_cpf_cnpj: str    # somente dígitos
    payer_email: Optional[str] = None
    payer_phone: Optional[str] = None
    # Dados da cobrança
    description: str = ""
    reference: str = ""    # número da fatura; usado como nosso_numero / txid
    # Endereço do pagador (obrigatório para boleto Asaas)
    payer_address: str = ""
    payer_address_number: str = ""
    payer_complement: str = ""
    payer_neighborhood: str = ""
    payer_city: str = ""
    payer_state: str = ""
    payer_zip: str = ""


@dataclass
class ChargeResult:
    """Resposta do provedor após criação da cobrança."""
    external_id: str
    status: str
    boleto_url: Optional[str] = None
    boleto_barcode: Optional[str] = None
    boleto_line: Optional[str] = None
    pix_qrcode: Optional[str] = None
    pix_copy_paste: Optional[str] = None


@dataclass
class ChargeStatus:
    """Status atualizado de uma cobrança."""
    external_id: str
    status: str           # normalizado para BILLING_STATUSES
    paid_at: Optional[str] = None
    paid_amount: Optional[Decimal] = None
    extra: dict = field(default_factory=dict)


@runtime_checkable
class BillingProvider(Protocol):
    """Interface que todo adaptador de cobrança deve implementar."""

    @property
    def name(self) -> str: ...

    async def create_charge(self, req: ChargeRequest, api_key: str) -> ChargeResult: ...

    async def get_charge_status(self, external_id: str, api_key: str) -> ChargeStatus: ...

    async def cancel_charge(self, external_id: str, api_key: str) -> None: ...

    def verify_webhook(self, token: str, expected_token: str) -> bool: ...

    def parse_webhook_event(self, payload: dict) -> ChargeStatus: ...
