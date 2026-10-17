"""Parser de arquivos CNAB240 e CNAB400 (extratos bancários brasileiros).

CNAB (Centro Nacional de Automação Bancária) é o padrão do Febraban para
troca de arquivos entre empresas e bancos. Cada linha tem comprimento fixo:
- CNAB240: 240 caracteres
- CNAB400: 400 caracteres

O layout principal:
- CNAB240: posição 7 (0-indexed) = tipo de registro (0=header arquivo,
  1=header lote, 3=detalhe, 5=trailer lote, 9=trailer arquivo).
  Detalhes com segmento 'P' ou 'T' (cobrança) carregam os dados financeiros.
- CNAB400: posição 0 = tipo (0=header, 1=detalhe, 9=trailer).

Retorna uma lista de `CnabTransaction` que o serviço de importação converte
em `TransactionImport`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Optional


class CnabParseError(ValueError):
    """Arquivo não reconhecido ou malformado."""


@dataclass
class CnabTransaction:
    date: date
    amount: Decimal                # positivo = crédito; negativo = débito
    description: str
    document_ref: str = ""        # nosso número / número do documento
    bank_ref: str = ""            # código de barras / identificador do banco


# ────────────────────────────────────────────────────────────────────────────
# Utilitários
# ────────────────────────────────────────────────────────────────────────────

def _to_date_ddmmyy(s: str) -> Optional[date]:
    s = s.strip()
    if len(s) == 6 and s.isdigit():
        return date(2000 + int(s[4:6]), int(s[2:4]), int(s[0:2]))
    return None


def _to_date_ddmmaaaa(s: str) -> Optional[date]:
    s = s.strip()
    if len(s) == 8 and s.isdigit():
        return date(int(s[4:8]), int(s[2:4]), int(s[0:2]))
    return None


def _to_date_aaaammdd(s: str) -> Optional[date]:
    s = s.strip()
    if len(s) == 8 and s.isdigit():
        return date(int(s[0:4]), int(s[4:6]), int(s[6:8]))
    return None


def _to_decimal(s: str, decimals: int = 2) -> Optional[Decimal]:
    s = s.strip()
    if not s or not s.isdigit():
        return None
    try:
        value = Decimal(s) / Decimal(10 ** decimals)
        return value
    except InvalidOperation:
        return None


def _detect_line_length(content: bytes) -> int:
    """Detecta se o arquivo é CNAB240 ou CNAB400 pela largura das linhas."""
    text = content.decode("latin-1", errors="replace")
    lines = text.splitlines()
    for line in lines:
        length = len(line)
        if length in (239, 240):
            return 240
        if length in (399, 400):
            return 400
    raise CnabParseError(
        "Arquivo CNAB não reconhecido: largura de linha deve ser 240 ou 400 caracteres"
    )


# ────────────────────────────────────────────────────────────────────────────
# CNAB 240
# ────────────────────────────────────────────────────────────────────────────

def _parse_cnab240_line(line: str) -> Optional[CnabTransaction]:
    """Extrai transação de uma linha de detalhe CNAB240 (segmento P ou T).

    Segmento P — cobrança/pagamento (layout Febraban padrão):
      [7]    tipo = '3' (detalhe)
      [13]   segmento = 'P' | 'T'
      [73:93] nosso número (20)
      [114:120] data vencimento DDMMAA (6)
      [120:135] valor do título (15, 2 decimais implícitos)
      [218:228] data do pagamento DDMMAA (6) — nem sempre presente

    Segmento T — informações do pagador (usado para nome):
      [13]   segmento = 'T'
      [33:73] nome do pagador (40)
    """
    if len(line) < 240:
        return None
    tipo = line[7]
    if tipo != "3":
        return None
    segmento = line[13].upper()

    if segmento == "P":
        nosso_num = line[73:93].strip()
        venc_raw = line[114:120]
        valor_raw = line[120:135]
        # Data de liquidação / efetiva — posição 218 quando presente
        liq_raw = line[218:224] if len(line) >= 224 else ""

        dt = _to_date_ddmmyy(venc_raw) or _to_date_ddmmyy(liq_raw)
        if dt is None:
            return None
        amount = _to_decimal(valor_raw, 2)
        if amount is None or amount == 0:
            return None

        return CnabTransaction(
            date=dt,
            amount=-amount,  # pagamento = saída de caixa
            description=f"Título {nosso_num}" if nosso_num else "Título CNAB",
            document_ref=nosso_num,
        )

    if segmento == "T":
        # Linha T traz o nome do pagador; sem valor financeiro próprio
        return None

    # Outros segmentos (Q, R, U, Y...) — ignorar
    return None


def parse_cnab240(content: bytes) -> list[CnabTransaction]:
    text = content.decode("latin-1", errors="replace")
    transactions: list[CnabTransaction] = []
    for raw_line in text.splitlines():
        line = raw_line.ljust(240)
        tx = _parse_cnab240_line(line)
        if tx:
            transactions.append(tx)
    return transactions


# ────────────────────────────────────────────────────────────────────────────
# CNAB 400
# ────────────────────────────────────────────────────────────────────────────

def _parse_cnab400_line(line: str) -> Optional[CnabTransaction]:
    """Extrai transação de uma linha de detalhe CNAB400.

    Layout Febraban padrão (cobrança — remessa/retorno):
      [0]     tipo = '1' (detalhe)
      [62:70] nosso número (8 ou mais, varia)
      [110:120] data de vencimento DDMMAAAA (8)
      [152:165] valor do título (13, 2 decimais implícitos)
      [295:301] data de crédito DDMMAA (6, retorno)
    """
    if len(line) < 400:
        return None
    tipo = line[0]
    if tipo != "1":
        return None

    nosso_num = line[62:70].strip()
    venc_raw = line[110:118]
    valor_raw = line[152:165]
    cred_raw = line[295:301]

    dt = _to_date_ddmmaaaa(venc_raw) or _to_date_ddmmyy(cred_raw)
    if dt is None:
        return None
    amount = _to_decimal(valor_raw, 2)
    if amount is None or amount == 0:
        return None

    return CnabTransaction(
        date=dt,
        amount=-amount,  # pagamento = saída de caixa
        description=f"Título {nosso_num}" if nosso_num else "Título CNAB",
        document_ref=nosso_num,
    )


def parse_cnab400(content: bytes) -> list[CnabTransaction]:
    text = content.decode("latin-1", errors="replace")
    transactions: list[CnabTransaction] = []
    for raw_line in text.splitlines():
        line = raw_line.ljust(400)
        tx = _parse_cnab400_line(line)
        if tx:
            transactions.append(tx)
    return transactions


# ────────────────────────────────────────────────────────────────────────────
# Ponto de entrada unificado
# ────────────────────────────────────────────────────────────────────────────

def parse_cnab(content: bytes) -> list[CnabTransaction]:
    """Detecta automaticamente CNAB240 ou CNAB400 e faz o parse."""
    line_length = _detect_line_length(content)
    if line_length == 240:
        return parse_cnab240(content)
    return parse_cnab400(content)
