# Retenção de dados

O SyncroFin permite configurar por quanto tempo cada tipo de dado é mantido antes
de ser anonimizado ou excluído automaticamente. Essa configuração atende às
exigências de retenção fiscal brasileiras e à LGPD.

## Prazos padrão

| Tipo de dado | Padrão | Mínimo |
|---|---|---|
| Transações | 2555 dias (~7 anos) | 365 dias |
| Anexos | 1825 dias (~5 anos) | 365 dias |
| Auditoria | 3650 dias (~10 anos) | 365 dias |

## Anonimização vs exclusão

Quando **Anonimizar ao expirar** está ativado (padrão), os dados expirados são
anonimizados em vez de excluídos:

- **Transações**: a descrição é substituída por "[anonimizado]", notas e favorecido
  são removidos, mas valor, data e categoria são preservados para integridade contábil
- **Anexos**: o arquivo é removido do armazenamento

Quando desativado, os dados expirados são excluídos permanentemente.

## Purga automática

O sistema executa a purga automaticamente uma vez por dia (às 02:00 UTC). Também é
possível executar manualmente pelo botão **Purgar agora** nas configurações do workspace.

## Onde configurar

**Configurações do workspace** > seção **Retenção de dados**.
