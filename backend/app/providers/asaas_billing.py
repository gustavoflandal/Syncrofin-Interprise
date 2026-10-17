"""Adaptador Asaas para cobrança por boleto e PIX (B2).

Asaas é o provedor de cobrança mais comum em PMEs brasileiras. Suporta:
  - Boleto bancário (vencimento, linha digitável, PDF)
  - PIX dinâmico (QR Code, copia-e-cola)
  - Webhooks de confirmação de pagamento

Docs: https://docs.asaas.com/
Ambientes:
  - Sandbox:    https://sandbox.asaas.com/api/v3
  - Produção:   https://api.asaas.com/api/v3
"""
from __future__ import annotations

import logging
from decimal import Decimal

import httpx

from app.providers.billing_provider import (
    ChargeRequest,
    ChargeResult,
    ChargeStatus,
)

logger = logging.getLogger(__name__)

_BASE = {
    "sandbox": "https://sandbox.asaas.com/api/v3",
    "production": "https://api.asaas.com/api/v3",
}

# Map Asaas status strings → our canonical BILLING_STATUSES
_STATUS_MAP = {
    "PENDING": "awaiting_payment",
    "AWAITING_RISK_ANALYSIS": "awaiting_payment",
    "CONFIRMED": "confirmed",
    "RECEIVED": "received",
    "OVERDUE": "overdue",
    "REFUNDED": "cancelled",
    "REFUND_REQUESTED": "cancelled",
    "REFUND_IN_PROGRESS": "cancelled",
    "CHARGEBACK_REQUESTED": "cancelled",
    "CHARGEBACK_DISPUTE": "cancelled",
    "AWAITING_CHARGEBACK_REVERSAL": "cancelled",
    "DUNNING_REQUESTED": "overdue",
    "DUNNING_RECEIVED": "received",
    "AWAITING_CUSTOMER_ACTION": "awaiting_payment",
    "CANCELLED": "cancelled",
}

_METHOD_MAP = {
    "boleto": "BOLETO",
    "pix": "PIX",
}


class AsaasBillingProvider:
    """Asaas REST API v3."""

    @property
    def name(self) -> str:
        return "asaas"

    def _client(self, api_key: str, environment: str) -> httpx.AsyncClient:
        base = _BASE.get(environment, _BASE["sandbox"])
        return httpx.AsyncClient(
            base_url=base,
            headers={"access_token": api_key, "Content-Type": "application/json"},
            timeout=30.0,
        )

    async def _ensure_customer(
        self,
        client: httpx.AsyncClient,
        req: ChargeRequest,
    ) -> str:
        """Return Asaas customer id, creating one if needed."""
        # Search for existing customer by cpfCnpj
        r = await client.get("/customers", params={"cpfCnpj": req.payer_cpf_cnpj})
        r.raise_for_status()
        data = r.json()
        if data.get("totalCount", 0) > 0:
            return data["data"][0]["id"]

        payload = {
            "name": req.payer_name,
            "cpfCnpj": req.payer_cpf_cnpj,
            "email": req.payer_email or "",
            "mobilePhone": req.payer_phone or "",
            "address": req.payer_address,
            "addressNumber": req.payer_address_number,
            "complement": req.payer_complement,
            "province": req.payer_neighborhood,
            "city": req.payer_city,
            "state": req.payer_state,
            "postalCode": req.payer_zip,
        }
        r = await client.post("/customers", json=payload)
        r.raise_for_status()
        return r.json()["id"]

    async def create_charge(
        self,
        req: ChargeRequest,
        api_key: str,
        environment: str = "sandbox",
    ) -> ChargeResult:
        async with self._client(api_key, environment) as client:
            customer_id = await self._ensure_customer(client, req)
            payload = {
                "customer": customer_id,
                "billingType": _METHOD_MAP.get(req.method, "PIX"),
                "value": float(req.amount),
                "dueDate": req.due_date.isoformat(),
                "description": req.description or req.reference,
                "externalReference": req.reference,
            }
            r = await client.post("/payments", json=payload)
            r.raise_for_status()
            data = r.json()

        status = _STATUS_MAP.get(data.get("status", ""), "pending")
        result = ChargeResult(
            external_id=data["id"],
            status=status,
            boleto_url=data.get("bankSlipUrl") or data.get("invoiceUrl"),
            boleto_barcode=None,
            boleto_line=data.get("nossoNumero"),
            pix_qrcode=data.get("pixQrCodeImage"),
            pix_copy_paste=data.get("pixCopiaECola"),
        )
        # Fetch QR code separately for PIX if not in create response
        if req.method == "pix" and not result.pix_copy_paste:
            try:
                async with self._client(api_key, environment) as client:
                    r2 = await client.get(f"/payments/{data['id']}/pixQrCode")
                    if r2.is_success:
                        qr = r2.json()
                        result.pix_qrcode = qr.get("encodedImage")
                        result.pix_copy_paste = qr.get("payload")
            except Exception:
                logger.warning("asaas: could not fetch PIX QR for %s", data["id"])
        return result

    async def get_charge_status(
        self, external_id: str, api_key: str, environment: str = "sandbox"
    ) -> ChargeStatus:
        async with self._client(api_key, environment) as client:
            r = await client.get(f"/payments/{external_id}")
            r.raise_for_status()
            data = r.json()
        return _parse_payment(data)

    async def cancel_charge(
        self, external_id: str, api_key: str, environment: str = "sandbox"
    ) -> None:
        async with self._client(api_key, environment) as client:
            r = await client.delete(f"/payments/{external_id}")
            r.raise_for_status()

    def verify_webhook(self, token: str, expected_token: str) -> bool:
        """Asaas sends $asaasApiKey in the `access_token` header of the webhook."""
        import hmac
        return hmac.compare_digest(token or "", expected_token or "")

    def parse_webhook_event(self, payload: dict) -> ChargeStatus:
        """Parse an Asaas webhook payload into a ChargeStatus."""
        payment = payload.get("payment", {})
        return _parse_payment(payment)


def _parse_payment(data: dict) -> ChargeStatus:
    raw_status = data.get("status", "")
    status = _STATUS_MAP.get(raw_status, "pending")
    paid_at = data.get("paymentDate") or data.get("confirmedDate")
    paid_net = data.get("netValue") or data.get("value")
    return ChargeStatus(
        external_id=data.get("id", ""),
        status=status,
        paid_at=paid_at,
        paid_amount=Decimal(str(paid_net)) if paid_net else None,
        extra={"raw_status": raw_status},
    )
