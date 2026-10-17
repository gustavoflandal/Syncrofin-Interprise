# Períodos

## Fechamento de período

**Administração → Períodos** permite fechar meses contábeis. Um mês fechado bloqueia a criação,
edição e exclusão de lançamentos naquele período.

Apenas membros com a permissão **Gerenciar períodos** podem fechar ou reabrir meses.

## Fechar um período

1. Clique em **Fechar período** ao lado do mês desejado.
2. Informe um motivo (opcional) e confirme.

Após o fechamento, qualquer tentativa de lançar ou editar uma transação no período fechado
retorna erro com indicação do mês bloqueado.

## Reabrir um período

1. Localize o mês fechado na lista.
2. Clique em **Reabrir** e informe o motivo.

A reabertura é registrada na auditoria com o nome de quem reabriu e o horário.

## Sincronização bancária em período fechado

O comportamento do sync quando o período está fechado é configurável em
**Configurações → Fechamento & Aprovações**:

| Modo | Comportamento |
|------|--------------|
| **Rejeitar** (padrão) | Transações sincronizadas no período fechado são descartadas |
| **Revisão pendente** | Criadas com status "revisão pendente" para análise manual |
| **Permitir** | Sync ignora o fechamento |

Veja também: [Aprovações](help:approvals).
