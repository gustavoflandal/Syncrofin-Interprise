# Patrimônio

**Patrimônio** acompanha o que você tem além das contas: investimentos, imóveis, veículos e outros bens, com o
histórico de valor de cada um. Junto com o saldo das contas, forma o seu **patrimônio líquido**.

## Carteiras e ativos

- **Ativo:** um bem ou investimento (uma ação, um fundo, um imóvel…).
- **Carteira:** agrupador de ativos (por exemplo, *Ações EUA*, *Renda Fixa Longo Prazo*). Crie com **Nova Carteira**
  (nome e cor). Ativos sem carteira ficam em **Sem carteira**; dá para **Mover para carteira**. Excluir uma
  carteira mantém os ativos (ficam sem agrupamento).

A tela tem as abas **Carteira** (posições consolidadas) e **Transações** (cada compra e venda por trás delas), além
de gráficos **Por Carteira** e **Por Ativo** (empilhado ou em linhas).

## Tipos de ativo

**Ação**, **ETF**, **Cripto**, **Fundo**, **Investimento**, **Imóvel**, **Veículo**, **Bem de Valor** e **Outro**.

## Como o valor é atualizado (Método de Valuação)

| Método | Uso |
|--------|-----|
| **Manual** | Você informa o valor de tempos em tempos (**Adicionar Valor**). Bom para imóveis e veículos. |
| **Regra de Crescimento** | O sistema **gera valores** automaticamente por um crescimento **percentual** ou **absoluto**, **diário/semanal/mensal/anual**, a partir de uma data (útil para renda fixa). Se você altera os parâmetros, pode **Regenerar** os valores gerados. |
| **Preço de Mercado** | O valor vem de uma **cotação** automática pelo **código** do ativo (ex.: `AAPL`, `BTC-USD`, `PETR4.SA`) e pela **quantidade**. Atualizada diariamente; **Atualizar cotação** força agora. |

O histórico aparece em **Histórico de Valores**, com a **origem** de cada ponto (*Manual*, *Regra*, *Sincronizado*
ou *Compra*) e um gráfico de **Tendência de Valor**.

## Compras, vendas e preço médio

Para ativos de mercado, cada **compra** e **venda** é um lançamento (**Adicionar transação**): informe o ativo, o
tipo (**Compra**/**Venda**), a **quantidade**, o **preço unitário**, a **taxa** e a data. O sistema calcula a posição
consolidada com o **preço médio** (o custo médio ponderado, como se usa para o imposto de renda no Brasil), o
**resultado** e o **% da carteira**. Vender mais do que você possui é recusado (*posições vendidas não são
suportadas*). Excluir ou editar um lançamento **recalcula** o preço médio.

Um ativo adicionado **sem preço de compra** recebe o aviso *sem preço*: inclua suas compras para acompanhar o preço
médio e a rentabilidade.

## Tesouro Direto

Para títulos do **Tesouro Direto**, o sistema consulta os preços oficiais do Tesouro Transparente. Ao adicionar um
ativo, busque o título pelo nome; o **vencimento** aparece (*Vence em…*). O recurso pode ser desativado pelo
administrador.

## Ativos sincronizados

Ativos que vieram de uma conexão bancária aparecem como **Sincronizado**. São gerenciados pela conexão (não dá para
editar valor/quantidade), mas você pode renomear e mover de carteira.

## Importar ordens

**Importar ordens** carrega um CSV de compras e vendas de uma corretora. Veja [Importar](help:importar).

## Vendidos e arquivados

Ativos **Vendidos** e **Arquivados** ficam em abas próprias, fora do total.

## Metas e relatórios

Um ativo ou uma carteira podem ser o alvo de uma [meta](help:metas); e o patrimônio aparece no
[relatório de Patrimônio Líquido](help:relatorios).
