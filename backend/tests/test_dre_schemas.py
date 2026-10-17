from decimal import Decimal
from app.schemas.dre import DreSection, DreGroupLine, DreLine, DreReport, DreQuarterlyReport, DreAnnualReport


def test_dre_section_subtotal_is_sum_of_groups():
    g1 = DreGroupLine(group_name="Serviços", lines=[DreLine(label="Consultoria", amount=Decimal("5000"))], subtotal=Decimal("5000"))
    g2 = DreGroupLine(group_name="Produtos", lines=[DreLine(label="Venda", amount=Decimal("3000"))], subtotal=Decimal("3000"))
    s = DreSection(key="receita", label="Receitas", groups=[g1, g2], subtotal=Decimal("8000"))
    assert s.subtotal == Decimal("8000")


def test_dre_report_has_sections_and_compat_fields():
    sec = DreSection(key="receita", label="Receitas", groups=[], subtotal=Decimal("0"))
    r = DreReport(
        year=2026, month=1, currency="BRL",
        sections=[sec],
        gross_revenue=Decimal("1000"), deductions=Decimal("0"),
        net_revenue=Decimal("1000"), operating_expenses=Decimal("500"),
        result=Decimal("500"), cost_center_id=None,
    )
    assert r.sections[0].key == "receita"
    assert r.gross_revenue == Decimal("1000")


def test_dre_quarterly_report_fields():
    r = DreQuarterlyReport(
        year=2026, quarter=1, currency="BRL",
        sections=[], months=[],
        gross_revenue=Decimal("0"), operating_expenses=Decimal("0"),
        result=Decimal("0"), cost_center_id=None,
    )
    assert r.quarter == 1


def test_dre_annual_report_fields():
    r = DreAnnualReport(
        year=2026, currency="BRL",
        sections=[], monthly=[],
        gross_revenue=Decimal("0"), operating_expenses=Decimal("0"),
        result=Decimal("0"), cost_center_id=None,
    )
    assert r.year == 2026
