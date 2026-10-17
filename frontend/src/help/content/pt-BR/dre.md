# DRE e Fluxo de Caixa

## Demonstrativo de Resultado (DRE)

O DRE resume as receitas e despesas do período escolhido. Use o seletor de mês/trimestre/ano
no canto superior direito para navegar entre períodos.

A coluna comparativa mostra o mês anterior para facilitar a análise de tendências.

## Regime de apuração

Use o toggle **Competência / Caixa** para alternar o regime de apuração:

| Regime | O que usa |
|--------|-----------|
| **Competência** | Data do lançamento (quando a receita/despesa ocorreu) |
| **Caixa** | Data efetiva (para cartão de crédito: data do pagamento da fatura) |

## Coluna Orçado

Ative o botão **Orçado** para exibir uma coluna adicional com o valor orçado de cada categoria.
A variação aparece ao lado — em verde se realizado ≥ orçado (receita) e vermelho se realizado > orçado (despesa).
Essa coluna requer que o **Orçamento** esteja configurado para o período selecionado.

## Estrutura hierárquica

O DRE exibe as transações agrupadas por **natureza** (Receitas, Custos, Despesas operacionais, Neutro)
e, dentro de cada natureza, pelos **grupos de categoria** configurados no Plano de Contas.
Clique em qualquer seção ou grupo para expandir ou recolher as linhas de detalhe.

## Filtrar por centro de custo

Use o seletor **Centro de custo** no topo da página para ver o DRE apenas das transações
de um centro de custo específico. "Todos" exibe o consolidado.

## Períodos

| Modo | O que mostra |
|------|-------------|
| **Mês** | DRE do mês selecionado com comparativo do mês anterior |
| **Trimestre** | Acumulado dos 3 meses do trimestre. Expanda "Detalhe por mês" para ver cada mês individualmente |
| **Ano** | Acumulado do ano com tabela de sazonalidade (12 colunas) |

## Exportar DRE

Clique em **Exportar XLSX** (modo Mês) para baixar o DRE em planilha compatível com Excel
e LibreOffice, pronta para enviar ao contador. A exportação respeita o regime e o filtro de orçado ativos.

## Fluxo de Caixa (DFC)

O gráfico abaixo do DRE mostra entradas e saídas reais:

- **Modo Mês**: semana a semana dentro do mês.
- **Modo Trimestre / Ano**: um bucket por mês, mostrando a evolução do período completo.

Clique em **Exportar DFC** (modo Mês) para baixar o fluxo de caixa semanal como XLSX.
