# Títulos

O painel **Títulos** mostra a posição consolidada de contas a receber e a pagar,
com três abas: **Visão geral**, **A Receber / A Pagar** e **Previsão**.

## Visão geral

Exibe o aging de cada lado do ledger (quanto está vencido há quanto tempo),
os próximos vencimentos e a **Posição Líquida** — diferença entre o total a receber
e o total a pagar.

## A Receber e A Pagar

Lista paginada de títulos filtráveis por situação:

| Situação | Significado |
|----------|-------------|
| **Em aberto** | Emitido e não quitado, dentro do prazo |
| **Vencido** | Prazo expirado e com saldo devedor |
| **Parcial** | Pagamento parcial registrado |
| **Pago** | Saldo zero — quitado |
| **Rascunho** | Ainda não emitido |

### Baixa rápida

Na coluna de ações, clique no ícone de moeda para registrar uma **baixa**: informe
o ID de uma transação já lançada (conta bancária ou caixa) e, opcionalmente, o
valor. Deixando o valor em branco, o sistema usa o saldo integral do título.

## Previsão de fluxo de caixa

Agrupa os títulos em aberto por vencimento futuro, em visão **mensal** (12 meses)
ou **semanal** (8 semanas). Mostra recebimentos esperados, pagamentos previstos e
o líquido por período — útil para planejar o caixa antes que os vencimentos cheguem.

> A previsão considera apenas títulos **em aberto com vencimento futuro**. Títulos
> vencidos aparecem no aging da visão geral, não aqui.

## Importação de NF-e XML

Na aba **A Pagar**, o botão **Importar NF-e XML** permite carregar um ou mais
arquivos XML de Nota Fiscal Eletrônica autorizados pela SEFAZ. Para cada arquivo:

- Um novo título a pagar é criado com emissor, valor total e data de vencimento
  extraídos da nota.
- Se o fornecedor (CNPJ) ainda não existir no workspace, ele é criado automaticamente.
- Arquivos com a mesma **chave de acesso** (44 dígitos) já importados anteriormente
  são sinalizados como **duplicados** e ignorados — seguro re-enviar o mesmo lote.
- XMLs inválidos ou sem `<infNFe>` geram uma linha de **erro** sem interromper
  os demais arquivos do mesmo envio.

> Limite de 50 arquivos por envio. O sistema aceita tanto o documento puro (`<NFe>`)
> quanto o resultado de autorização da SEFAZ (`<nfeProc>`).

## Criando títulos manualmente

Para lançar um título avulso, acesse o menu **Faturas** e crie uma nova fatura com a
direção **A Receber** (cliente deve à empresa) ou **A Pagar** (empresa deve ao
fornecedor).

Para pagar um título por PIX ou TED com dupla aprovação, veja [Pagamentos](help:pagamentos).
