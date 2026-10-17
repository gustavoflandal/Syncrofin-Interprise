"""The accountant package: spreadsheet-ready CSVs for a period."""
import csv
import io
import uuid
import zipfile
from datetime import date, datetime, timezone
from decimal import Decimal

import pyzipper
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.transaction import Transaction
from app.models.user import User
from app.services.accountant_export_service import fmt_date, fmt_money, validate_period, ExportPeriodError


def _period() -> dict:
    today = date.today()
    return {"start": today.replace(day=1).isoformat(), "end": today.isoformat()}


def _rows(zf: zipfile.ZipFile, name: str) -> list[list[str]]:
    text = zf.read(name).decode("utf-8-sig")
    return list(csv.reader(io.StringIO(text), delimiter=";"))


def test_money_uses_decimal_comma_and_no_thousands_separator():
    assert fmt_money(Decimal("1234.5")) == "1234,50"
    assert fmt_money(Decimal("-0.1")) == "-0,10"
    assert fmt_money(None) == ""


def test_dates_are_day_first():
    assert fmt_date(date(2026, 3, 9)) == "09/03/2026"
    assert fmt_date(None) == ""


def test_period_validation():
    validate_period(date(2026, 1, 1), date(2026, 1, 1))
    with pytest.raises(ExportPeriodError):
        validate_period(date(2026, 2, 1), date(2026, 1, 1))
    with pytest.raises(ExportPeriodError):
        validate_period(date(2000, 1, 1), date(2026, 1, 1))


@pytest.mark.asyncio
async def test_requires_authentication(client: AsyncClient):
    response = await client.get("/api/export/accountant", params=_period())
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_rejects_inverted_period(client: AsyncClient, auth_headers):
    response = await client.get(
        "/api/export/accountant",
        params={"start": "2026-02-01", "end": "2026-01-01"},
        headers=auth_headers,
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_package_has_every_file_and_a_bom(
    client: AsyncClient, auth_headers, test_transactions
):
    response = await client.get("/api/export/accountant", params=_period(), headers=auth_headers)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "syncrofin-contador-" in response.headers["content-disposition"]

    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        assert set(zf.namelist()) == {
            "lancamentos.csv",
            "resumo_por_categoria.csv",
            "resumo_mensal.csv",
            "plano_de_contas.csv",
            "contas.csv",
            "titulos.csv",
            "LEIA-ME.txt",
        }
        # Excel needs the BOM to read UTF-8 as UTF-8.
        assert zf.read("lancamentos.csv").startswith(b"\xef\xbb\xbf")


@pytest.mark.asyncio
async def test_ledger_is_signed_and_formatted_for_brazilian_spreadsheets(
    client: AsyncClient, auth_headers, test_transactions
):
    response = await client.get("/api/export/accountant", params=_period(), headers=auth_headers)
    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        rows = _rows(zf, "lancamentos.csv")

    header, body = rows[0], rows[1:]
    assert header[0] == "Data" and header[8] == "Valor"
    by_desc = {r[3]: r for r in body}
    assert len(body) == len(test_transactions)
    assert by_desc["UBER TRIP"][8] == "-25,50"
    assert by_desc["UBER TRIP"][7] == "Despesa"
    assert by_desc["SALARIO FEV"][8] == "8000,00"
    assert by_desc["SALARIO FEV"][7] == "Receita"
    assert by_desc["IFOOD RESTAURANTE"][5] == "Alimentação"
    assert by_desc["PIX RECEBIDO"][5] == "Sem categoria"


@pytest.mark.asyncio
async def test_summaries_add_up_and_leave_transfers_out(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers,
    test_user: User,
    test_account: Account,
    test_transactions,
):
    # The fixture rows default to USD; the workspace is BRL. Summaries only
    # count what can be expressed in the workspace currency.
    for tx in test_transactions:
        tx.currency = "BRL"
    # A transfer pair: neither leg is income or spending.
    pair = uuid.uuid4()
    for typ in ("debit", "credit"):
        session.add(
            Transaction(
                id=uuid.uuid4(),
                user_id=test_user.id,
                account_id=test_account.id,
                description="TRANSF ENTRE CONTAS",
                amount=Decimal("500.00"),
                date=date.today(),
                type=typ,
                source="manual",
                transfer_pair_id=pair,
                created_at=datetime.now(timezone.utc),
            )
        )
    await session.commit()

    response = await client.get("/api/export/accountant", params=_period(), headers=auth_headers)
    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        ledger = _rows(zf, "lancamentos.csv")[1:]
        monthly = _rows(zf, "resumo_mensal.csv")[1:]
        by_cat = _rows(zf, "resumo_por_categoria.csv")[1:]

    assert sum(1 for r in ledger if r[7] == "Transferência") == 2
    # income 8000 + 150, spending 25.50 + 45 + 39.90 = 110.40
    assert len(monthly) == 1
    assert monthly[0][1] == "8150,00"
    assert monthly[0][2] == "110,40"
    assert monthly[0][3] == "8039,60"
    # The category summary agrees with the monthly one.
    assert sum(Decimal(r[2].replace(",", ".")) for r in by_cat) == Decimal("8150.00")


@pytest.mark.asyncio
async def test_period_filters_the_ledger(
    client: AsyncClient, auth_headers, test_transactions
):
    response = await client.get(
        "/api/export/accountant",
        params={"start": "2001-01-01", "end": "2001-01-31"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        assert _rows(zf, "lancamentos.csv")[1:] == []
        assert _rows(zf, "resumo_mensal.csv")[1:] == []


@pytest.mark.asyncio
async def test_formula_injection_is_neutralised(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers,
    test_user: User,
    test_account: Account,
):
    session.add(
        Transaction(
            id=uuid.uuid4(),
            user_id=test_user.id,
            account_id=test_account.id,
            description='=HYPERLINK("http://evil.example","clique")',
            amount=Decimal("10.00"),
            date=date.today(),
            type="debit",
            source="manual",
            created_at=datetime.now(timezone.utc),
        )
    )
    await session.commit()

    response = await client.get("/api/export/accountant", params=_period(), headers=auth_headers)
    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        rows = _rows(zf, "lancamentos.csv")[1:]
    assert rows[0][3].startswith("'=")


@pytest.mark.asyncio
async def test_a_viewer_can_export(client: AsyncClient, viewer_auth_headers, test_transactions):
    """The accountant is invited as a viewer; the export is what they are for."""
    response = await client.get(
        "/api/export/accountant", params=_period(), headers=viewer_auth_headers
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_password_encrypts_the_package(
    client: AsyncClient, auth_headers, test_transactions
):
    response = await client.post(
        "/api/export/accountant",
        json={**_period(), "password": "senha-forte-123"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    with pyzipper.AESZipFile(io.BytesIO(response.content)) as zf:
        with pytest.raises(RuntimeError):
            zf.read("lancamentos.csv")
        zf.setpassword(b"senha-forte-123")
        assert zf.read("lancamentos.csv").startswith(b"\xef\xbb\xbf")


@pytest.mark.asyncio
async def test_short_password_is_refused(client: AsyncClient, auth_headers):
    response = await client.post(
        "/api/export/accountant", json={**_period(), "password": "curta"}, headers=auth_headers
    )
    assert response.status_code == 422
