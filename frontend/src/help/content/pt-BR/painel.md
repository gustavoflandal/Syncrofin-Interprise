# Painel

O **Painel** é a tela inicial: um resumo do mês escolhido, com saldos, gastos, tendências e alertas. Você chega
nele ao clicar no nome **SyncroFin** do menu lateral.

## Escolher o período

No topo, o seletor de mês (**‹ Setembro de 2026 ›**) muda o mês exibido. Clique no nome do mês para abrir um
calendário de meses. Se você usa [Coleções](help:colecoes), o filtro de coleção limita tudo às contas dela.

## Cartões de resumo

| Cartão | Significado |
|--------|-------------|
| **Saldo disponível em contas** | Soma dos saldos das suas contas, com o detalhamento por conta (e por moeda, se houver mais de uma). |
| **Entradas do Mês** / **Saídas do Mês** | Receitas e despesas **efetivadas** no mês. Transferências entre suas contas **não** entram. |
| **Saídas previstas** / **Entradas previstas** | O que ainda deve acontecer no mês, vindo das [Recorrentes](help:recorrentes). |
| **Patrimônio líquido** | Contas + investimentos, descontadas as faturas de cartão em aberto. |
| **Taxa de Economia** | Quanto da renda do mês ficou guardada. Quando não há renda no mês, aparece `---`. |
| **Nesse ritmo, você gastará…** | Projeção do gasto até o fim do mês, pelo ritmo até agora. |

Se houver **grupos de divisão de despesas**, o patrimônio mostra também o líquido depois do que você deve ou tem a
receber ([Grupos](help:grupos)).

## Transações sem categoria

Quando existem transações sem categoria, uma faixa amarela avisa: *"N transações precisam ser categorizadas"*.
**Categorizar agora** leva à lista já filtrada. Quando tudo está categorizado, aparece **Tudo em dia!**

## Saúde financeira e previsão de caixa

Um cartão mostra a **nota de saúde financeira** (0 a 100) e a **previsão de caixa** dos próximos 90 dias. Explicação
completa em [Saúde financeira e previsão de caixa](help:saude-financeira).

## Gráficos

- **Gastos por Categoria:** barras com o quanto foi gasto em cada categoria no mês. Ordene por **Maior gasto** ou
  **Menor gasto**. Clique numa categoria para ver as transações dela (*drill-down*).
- **Tendência Mensal:** receitas e despesas dos últimos meses.
- **Orçamento vs Realizado:** cada categoria com orçamento, com o quanto do limite foi usado
  ([Orçamentos](help:orcamentos)).
- **Fluxo de Saldo:** a evolução do saldo dia a dia, comparada ao mês anterior. Passe o mouse para ver o saldo de
  cada dia.
- **Progresso das Metas:** as suas [Metas](help:metas) e o quanto falta.
- **Transações Recentes / do Período:** as últimas movimentações, com ordenação.

Clicar em um valor de entrada ou saída abre a lista de transações que o compõem, com o total (*Liquidado* e
*Pendente de liquidação*).

## Regime de caixa e de competência

Compras no **cartão de crédito** podem contar de duas formas, definidas pelo administrador
([Administração](help:administracao)):

- **Regime de caixa** (padrão): a compra conta no dia em que aconteceu;
- **Regime de competência:** a compra conta na **data de vencimento da fatura**. Nesse modo o painel mostra uma nota
  explicando.

## Atualizar as taxas de câmbio

Se você tem transações em outras moedas, o painel mostra o **detalhamento por moeda** e permite **atualizar as taxas
de câmbio**. Sem uma chave de câmbio configurada, o sistema usa **1:1** e avisa.

## Dicas

- **Ocultar valores** (ícone de olho) esconde todos os números da tela.
- O painel do workspace **Pessoal** e o do de **Negócios** são independentes.
