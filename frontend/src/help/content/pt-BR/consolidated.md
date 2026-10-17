# Consolidado Multiempresa

A visão consolidada agrega o DRE de múltiplos workspaces empresariais em um único relatório, eliminando automaticamente as transferências intercompany.

## Como usar

1. Acesse **Relatórios › Consolidado**.
2. Selecione os workspaces que deseja consolidar (mínimo 2).
3. Escolha o mês/ano e o regime (competência ou caixa).
4. Clique em **Gerar consolidado**.

O resultado exibe:
- A DRE individual de cada empresa selecionada.
- A DRE consolidada com os valores somados.

## Eliminação de intercompany

Transferências entre workspaces usam `transfer_pair_id` para ligar as duas pontas. O filtro de P&L (`counts_as_pnl`) exclui automaticamente qualquer transação com `transfer_pair_id`, então:

- Uma transferência da Empresa A para a Empresa B aparece nas duas DREs individuais como uma movimentação interna, mas **não entra na DRE consolidada**.
- Não é necessário nenhum ajuste manual.

## Permissões

Cada workspace é consultado com a permissão de membro. Só aparecem na lista os workspaces dos quais você é membro.

## Notas

- Se os workspaces tiverem moedas diferentes, o campo `currency` do consolidado será `MIX` — os valores são somados numericamente sem conversão.
- Para uma visão trimestral ou anual, use o DRE individual de cada workspace (A4).

Veja também: [DRE/DFC](help:dre).
