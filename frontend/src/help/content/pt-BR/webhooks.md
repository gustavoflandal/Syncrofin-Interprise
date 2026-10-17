# Webhooks

Webhooks permitem que sistemas externos recebam notificações em tempo real quando eventos ocorrem no SyncroFin Enterprise. Útil para integrar com ERPs, sistemas de BI ou automatizar fluxos via plataformas como Zapier ou n8n.

## Configurar um endpoint

1. Acesse **Configurações › Webhooks**.
2. Clique em **Adicionar endpoint**.
3. Informe a URL HTTPS que receberá as notificações.
4. Selecione os eventos de interesse (ou deixe vazio para receber todos).
5. Opcionalmente, informe um **segredo HMAC** — o SyncroFin assina cada payload com `X-SyncroFin-Signature: sha256=<hmac>`.

## Eventos disponíveis

| Evento | Quando dispara |
|---|---|
| `transaction.created` | Nova transação lançada |
| `transaction.updated` | Transação editada |
| `transaction.deleted` | Transação removida |
| `invoice.paid` | Fatura totalmente quitada |
| `sync.completed` | Sincronização bancária concluída |
| `sync.failed` | Sincronização bancária com erro |
| `period.closed` | Período contábil fechado |
| `period.reopened` | Período contábil reaberto |

## Formato do payload

```json
{
  "id": "<uuid único por entrega>",
  "workspace_id": "<id do workspace>",
  "event": "transaction.created",
  "created_at": "2026-10-06T12:00:00Z",
  "data": { ... }
}
```

## Verificar a assinatura

```python
import hmac, hashlib

def verify(secret: str, body: bytes, signature: str) -> bool:
    expected = "sha256=" + hmac.new(
        secret.encode(), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)
```

## Histórico de entregas

Cada entrega é registrada em **Entregas** do endpoint. Em caso de falha, use o botão **Reenviar** para tentar novamente sem esperar o próximo evento.

## Permissões

Criar, editar e remover endpoints exige a permissão **webhooks.manage** (concedida a donos por padrão). Membros sem essa permissão podem consultar os endpoints e o histórico de entregas, mas não alterar configurações.
