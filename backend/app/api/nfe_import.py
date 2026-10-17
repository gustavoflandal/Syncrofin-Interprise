"""Endpoints de importação de NF-e (Nota Fiscal Eletrônica).

Fluxo de dois passos:
  1. POST /preview  — parse do XML, devolve prévia sem persistir nada
  2. POST /import   — cria o título a pagar (Invoice payable) com base na prévia

Rota GET não existe: este módulo só grava. O permissionamento reusa o gate
`imports.write` já definido para o importador de transações.
"""
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.upload_guard import validate_upload
from app.core.database import get_async_session
from app.core.workspace_context import WorkspaceContext, require_permission
from app.schemas.nfe_import import NfeImportResult, NfePreview, NfeItemPreview
from app.services import invoice_service
from app.services.nfe_parser import NFeParseError as NfeParseError, parse_nfe_xml

_write_gate = require_permission("imports.write")

router = APIRouter(
    prefix="/api/workspaces/{workspace_id}/nfe",
    tags=["nfe-import"],
)


@router.post("/preview", response_model=NfePreview)
async def nfe_preview(
    workspace_id: uuid.UUID,
    file: UploadFile = File(...),
    # Preview não muta; read gate suficiente (mesmo padrão do import/preview)
    ctx: WorkspaceContext = Depends(require_permission("imports.write")),
    session: AsyncSession = Depends(get_async_session),
):
    """Parse o XML de NF-e e devolve prévia para confirmação pelo usuário."""
    content, _ = await validate_upload(file, category="import")
    try:
        nfe = parse_nfe_xml(content)
    except NfeParseError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    already_imported = False
    existing = await invoice_service.find_by_external_id(
        session, workspace_id, "nfe", nfe.chave_acesso
    )
    if existing:
        already_imported = True

    return NfePreview(
        chave_acesso=nfe.chave_acesso,
        numero=nfe.numero,
        serie=nfe.serie,
        issue_date=nfe.issue_date,
        emitente_cnpj=nfe.emitente_cnpj,
        emitente_nome=nfe.emitente_nome,
        valor_total=nfe.valor_total,
        valor_produtos=nfe.valor_produtos,
        valor_impostos=nfe.valor_impostos,
        currency=nfe.currency,
        items=[
            NfeItemPreview(
                description=item.description,
                quantity=item.quantity,
                unit_price=item.unit_price,
                total=item.total,
            )
            for item in nfe.items
        ],
        notes=nfe.notes,
        already_imported=already_imported,
    )


@router.post("/import", response_model=NfeImportResult, status_code=201)
async def nfe_import(
    workspace_id: uuid.UUID,
    file: UploadFile = File(...),
    due_date: str = Form(...),          # ISO date string YYYY-MM-DD
    payee_id: str = Form(None),
    ctx: WorkspaceContext = Depends(_write_gate),
    session: AsyncSession = Depends(get_async_session),
):
    """Cria um título a pagar a partir do XML de NF-e.

    O arquivo é enviado novamente para que o servidor seja stateless.
    Se a chave de acesso já existir, devolve o Invoice existente (idempotente).
    """
    content, _ = await validate_upload(file, category="import")
    try:
        nfe = parse_nfe_xml(content)
    except NfeParseError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    from datetime import date as _date
    try:
        parsed_due = _date.fromisoformat(due_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="due_date inválido (use YYYY-MM-DD)")

    parsed_payee_id: uuid.UUID | None = None
    if payee_id:
        try:
            parsed_payee_id = uuid.UUID(payee_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="payee_id inválido")

    # Idempotência: chave já importada → retorna invoice existente
    existing = await invoice_service.find_by_external_id(
        session, workspace_id, "nfe", nfe.chave_acesso
    )
    if existing:
        return NfeImportResult(
            invoice_id=existing.id,
            chave_acesso=nfe.chave_acesso,
            emitente_nome=nfe.emitente_nome,
            valor_total=nfe.valor_total,
            already_existed=True,
        )

    # Constrói os dados do invoice
    lines_data = [
        {
            "description": item.description,
            "quantity": str(item.quantity),
            "unit_price": str(item.unit_price),
            "amount": str(item.total),
            "position": idx,
        }
        for idx, item in enumerate(nfe.items, start=1)
    ] or [
        {
            "description": f"NF-e {nfe.numero} — {nfe.emitente_nome}",
            "quantity": "1",
            "unit_price": str(nfe.valor_total),
            "amount": str(nfe.valor_total),
            "position": 1,
        }
    ]

    invoice_data: dict = {
        "direction": "payable",
        "origin": "imported",
        "external_source": "nfe",
        "external_id": nfe.chave_acesso,
        "external_number": nfe.numero,
        "issue_date": nfe.issue_date,
        "due_date": parsed_due,
        "currency": nfe.currency,
        "subtotal": nfe.valor_produtos,
        "tax_total": nfe.valor_impostos,
        "total": nfe.valor_total,
        "notes": nfe.notes,
        "status": "draft",
        "payee_id": parsed_payee_id,
        "lines": lines_data,
    }

    try:
        invoice = await invoice_service.create_invoice(
            session, workspace_id, ctx.user_id, invoice_data
        )
        # Muda para open — para NF-e importada o documento já foi emitido
        await invoice_service.issue_invoice(session, invoice)
        await session.commit()
    except invoice_service.InvoiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)

    return NfeImportResult(
        invoice_id=invoice.id,
        chave_acesso=nfe.chave_acesso,
        emitente_nome=nfe.emitente_nome,
        valor_total=nfe.valor_total,
        already_existed=False,
    )
