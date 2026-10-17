# Retenção Documental Fiscal

## O que é

A legislação tributária brasileira exige que documentos fiscais sejam guardados por no mínimo 5 anos. O SyncroFin permite travar anexos fiscais para que não possam ser alterados nem excluídos durante esse prazo.

## Como travar um documento

1. Abra o detalhe da fatura e vá até a seção de **Documentos**.
2. Localize o anexo do tipo **Documento fiscal** que deseja proteger.
3. Clique no botão de **escudo** que aparece ao passar o cursor sobre o anexo.
4. O documento será travado imediatamente com prazo de retenção de 5 anos.

## O que acontece após travar

- O anexo exibe um **ícone de cadeado** no lugar do ícone de arquivo.
- Um **badge** mostra a data até a qual o documento deve ser retido.
- Os botões de **excluir** e **editar** ficam ocultos — o arquivo não pode ser removido.
- Qualquer tentativa de modificar ou excluir via API retorna erro 403.

## Quem pode travar

Qualquer usuário com permissão de escrita na fatura pode travar um anexo fiscal. Uma vez travado, nem mesmo administradores podem destravar antes do fim do prazo.

## Prazo de retenção

O prazo padrão é de **5 anos** a partir do momento do travamento, conforme as obrigações fiscais brasileiras. A data de expiração é registrada no campo `retention_until` do anexo.
