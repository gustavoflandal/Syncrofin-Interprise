"""Parser para XML de NF-e (Nota Fiscal Eletrônica) versão 4.00/3.10.

Extrai os campos mínimos necessários para criar um título a pagar:
emissor, chave de acesso, número, datas de emissão e vencimento, e
valores totais.

Não valida assinatura digital — assume que o arquivo já foi emitido
e autorizado pela SEFAZ. Chaves duplicadas são detectadas na camada
de serviço pela constraint `uq_invoices_workspace_external`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Optional
from xml.etree import ElementTree as ET

# Namespace usado em todos os documentos NF-e (3.10 e 4.00)
_NS = "http://www.portalfiscal.inf.br/nfe"
_NS_MAP = {"nfe": _NS}

# A chave de acesso tem exatamente 44 dígitos
_CHAVE_RE = re.compile(r"^\d{44}$")


class NFeParseError(ValueError):
    """XML não é uma NF-e válida ou está malformado."""


@dataclass
class NFeData:
    chave: str           # 44 dígitos
    number: str          # nNF
    series: str          # serie
    issue_date: date
    due_date: date
    supplier_cnpj: Optional[str]   # CPF aceito quando CNPJ ausente
    supplier_name: str
    subtotal: Decimal    # vProd
    discount: Decimal    # vDesc
    tax_total: Decimal   # vTotTrib ou vICMS+vPIS+vCOFINS (melhor estimativa)
    total: Decimal       # vNF


def _find(element: ET.Element, path: str) -> Optional[ET.Element]:
    return element.find(path, _NS_MAP)


def _text(element: Optional[ET.Element], path: str) -> str:
    if element is None:
        return ""
    child = element.find(path, _NS_MAP)
    return (child.text or "").strip() if child is not None else ""


def _decimal(s: str) -> Decimal:
    try:
        return Decimal(s.strip().replace(",", "."))
    except (InvalidOperation, AttributeError):
        return Decimal("0")


def _parse_date(s: str) -> Optional[date]:
    """Converte dhEmi (ISO 8601 com fuso) ou dEmi (YYYY-MM-DD) em date."""
    s = s.strip()
    if not s:
        return None
    # datetime com fuso: 2020-06-12T10:30:00-03:00
    try:
        return datetime.fromisoformat(s).date()
    except ValueError:
        pass
    # data simples: 2020-06-12
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def parse_nfe_xml(xml_bytes: bytes) -> NFeData:
    """Lê os bytes de um XML de NF-e e retorna um NFeData.

    Aceita tanto o documento bruto (``<NFe>``) quanto o resultado de
    autorização da SEFAZ (``<nfeProc>``).

    Raises:
        NFeParseError: quando o XML não é reconhecido como NF-e.
    """
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise NFeParseError(f"XML inválido: {exc}") from exc

    # Normaliza: nfeProc > NFe > infNFe  ou  NFe > infNFe
    inf_nfe = root.find(f".//{{{_NS}}}infNFe")
    if inf_nfe is None:
        raise NFeParseError("Elemento <infNFe> não encontrado — não é um XML de NF-e")

    # ── Chave de acesso ──────────────────────────────────────────────────────
    raw_id = inf_nfe.get("Id", "")
    # O atributo é "NFe" + 44 dígitos; retiramos o prefixo.
    chave = raw_id[3:] if raw_id.startswith("NFe") else raw_id
    if not _CHAVE_RE.match(chave):
        # Fallback: tentar chNFe dentro de protNFe
        ch_elem = root.find(f".//{{{_NS}}}chNFe")
        if ch_elem is not None and ch_elem.text:
            chave = ch_elem.text.strip()
    if not _CHAVE_RE.match(chave):
        raise NFeParseError(f"Chave de acesso inválida: {chave!r}")

    # ── IDE ──────────────────────────────────────────────────────────────────
    ide = _find(inf_nfe, "nfe:ide")
    if ide is None:
        raise NFeParseError("Elemento <ide> não encontrado")

    nf_number = _text(ide, "nfe:nNF") or "0"
    series = _text(ide, "nfe:serie") or "1"
    raw_dh_emi = _text(ide, "nfe:dhEmi") or _text(ide, "nfe:dEmi")
    issue_date = _parse_date(raw_dh_emi)
    if issue_date is None:
        raise NFeParseError(f"Data de emissão inválida: {raw_dh_emi!r}")

    # ── EMITENTE ─────────────────────────────────────────────────────────────
    emit = _find(inf_nfe, "nfe:emit")
    if emit is None:
        raise NFeParseError("Elemento <emit> não encontrado")
    supplier_cnpj = _text(emit, "nfe:CNPJ") or _text(emit, "nfe:CPF") or None
    supplier_name = (
        _text(emit, "nfe:xNome") or _text(emit, "nfe:xFant") or "Desconhecido"
    )

    # ── TOTAIS ───────────────────────────────────────────────────────────────
    icms_tot = _find(inf_nfe, "nfe:total/nfe:ICMSTot")
    subtotal = _decimal(_text(icms_tot, "nfe:vProd")) if icms_tot is not None else Decimal("0")
    discount = _decimal(_text(icms_tot, "nfe:vDesc")) if icms_tot is not None else Decimal("0")
    total = _decimal(_text(icms_tot, "nfe:vNF")) if icms_tot is not None else Decimal("0")

    # Estimativa de tributos: vTotTrib (campo informativo, opcional)
    v_tot_trib = _find(inf_nfe, "nfe:total/nfe:retTrib/nfe:vTotRetTrib")
    if v_tot_trib is None:
        v_tot_trib = _find(inf_nfe, "nfe:infAdic/nfe:vTotTrib")
    tax_total = _decimal(v_tot_trib.text or "0") if v_tot_trib is not None else Decimal("0")

    if total <= 0:
        raise NFeParseError(f"Valor total inválido: {total}")

    # ── VENCIMENTO ───────────────────────────────────────────────────────────
    # Preferência: última duplicata em <cobr>; fallback: emissão + 30 dias.
    due_date: Optional[date] = None
    cobr = _find(inf_nfe, "nfe:cobr")
    if cobr is not None:
        dups = cobr.findall(f"{{{_NS}}}dup")
        if dups:
            last_d_venc = _text(dups[-1], "nfe:dVenc")
            due_date = _parse_date(last_d_venc)

    if due_date is None:
        due_date = issue_date + timedelta(days=30)

    return NFeData(
        chave=chave,
        number=nf_number,
        series=series,
        issue_date=issue_date,
        due_date=due_date,
        supplier_cnpj=supplier_cnpj,
        supplier_name=supplier_name,
        subtotal=subtotal,
        discount=discount,
        tax_total=tax_total,
        total=total,
    )
