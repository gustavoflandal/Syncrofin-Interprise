"""Testes unitários para o parser de NF-e XML (services/nfe_parser.py).

Usa XMLs sintéticos, sem dependência de banco de dados.
"""
import pytest
from datetime import date
from decimal import Decimal

from app.services.nfe_parser import NFeParseError, parse_nfe_xml

_NS = "http://www.portalfiscal.inf.br/nfe"
_CHAVE = "35200607677851000107550010000037021988210001"


def _make_nfe(
    chave: str = _CHAVE,
    nf_number: str = "3702",
    serie: str = "1",
    dh_emi: str = "2020-06-12T10:30:00-03:00",
    cnpj: str = "07677851000107",
    name: str = "EMPRESA EMITENTE LTDA",
    v_prod: str = "500.00",
    v_desc: str = "0.00",
    v_nf: str = "500.00",
    d_venc: str | None = "2020-07-12",
    wrap_proc: bool = False,
) -> bytes:
    """Gera um XML de NF-e mínimo para os testes."""
    dup = ""
    if d_venc:
        dup = f"""
      <cobr>
        <dup>
          <nDup>001</nDup>
          <dVenc>{d_venc}</dVenc>
          <vDup>{v_nf}</vDup>
        </dup>
      </cobr>"""

    nfe_body = f"""<NFe xmlns="{_NS}">
    <infNFe Id="NFe{chave}" versao="4.00">
      <ide>
        <nNF>{nf_number}</nNF>
        <serie>{serie}</serie>
        <dhEmi>{dh_emi}</dhEmi>
      </ide>
      <emit>
        <CNPJ>{cnpj}</CNPJ>
        <xNome>{name}</xNome>
      </emit>
      <total>
        <ICMSTot>
          <vProd>{v_prod}</vProd>
          <vDesc>{v_desc}</vDesc>
          <vNF>{v_nf}</vNF>
        </ICMSTot>
      </total>
      {dup}
    </infNFe>
  </NFe>"""

    if wrap_proc:
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="{_NS}" versao="4.00">
  {nfe_body}
  <protNFe versao="4.00">
    <infProt>
      <chNFe>{chave}</chNFe>
    </infProt>
  </protNFe>
</nfeProc>"""
    else:
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
{nfe_body}"""

    return xml.encode("utf-8")


def test_parse_minimal_nfe():
    """Parser extrai os campos básicos de um NF-e simples."""
    nfe = parse_nfe_xml(_make_nfe())
    assert nfe.chave == _CHAVE
    assert nfe.number == "3702"
    assert nfe.series == "1"
    assert nfe.issue_date == date(2020, 6, 12)
    assert nfe.due_date == date(2020, 7, 12)
    assert nfe.supplier_cnpj == "07677851000107"
    assert nfe.supplier_name == "EMPRESA EMITENTE LTDA"
    assert nfe.total == Decimal("500.00")


def test_parse_nfeproc_wrapper():
    """NFe envolvida em nfeProc (resultado de autorização) é aceita."""
    nfe = parse_nfe_xml(_make_nfe(wrap_proc=True))
    assert nfe.chave == _CHAVE
    assert nfe.total == Decimal("500.00")


def test_parse_due_date_fallback():
    """Sem <cobr>, o vencimento é emissão + 30 dias."""
    nfe = parse_nfe_xml(_make_nfe(d_venc=None))
    assert nfe.due_date == date(2020, 7, 12)  # 12/06 + 30


def test_parse_discount():
    """vDesc é carregado corretamente."""
    nfe = parse_nfe_xml(_make_nfe(v_prod="600.00", v_desc="100.00", v_nf="500.00"))
    assert nfe.discount == Decimal("100.00")
    assert nfe.total == Decimal("500.00")


def test_invalid_xml_raises():
    """XML malformado deve levantar NFeParseError."""
    with pytest.raises(NFeParseError):
        parse_nfe_xml(b"not xml at all")


def test_missing_infnfe_raises():
    """XML válido mas sem <infNFe> deve levantar NFeParseError."""
    with pytest.raises(NFeParseError, match="infNFe"):
        parse_nfe_xml(b"<root></root>")


def test_invalid_total_raises():
    """Valor total zero deve levantar NFeParseError."""
    with pytest.raises(NFeParseError, match="total"):
        parse_nfe_xml(_make_nfe(v_nf="0.00"))


def test_invalid_chave_raises():
    """Chave de acesso com comprimento errado deve levantar NFeParseError."""
    with pytest.raises(NFeParseError, match="Chave"):
        parse_nfe_xml(_make_nfe(chave="1234"))
