# Provisões e diferimentos

## Para que serve

**Organizar → Provisões** distribui um valor ao longo de vários meses. Use **Provisão** para
reconhecer uma despesa aos poucos (férias, 13º, seguro anual) e **Diferimento** para reconhecer
uma receita recebida adiantada mês a mês.

## Criar um cronograma

1. Clique em **Novo cronograma**.
2. Escolha o tipo, informe descrição, valor total, data inicial e final, a conta e, se quiser,
   categoria e centro de custo.
3. O sistema gera uma parcela por mês. O valor é dividido igualmente e a diferença de
   arredondamento fica na última parcela.

Use uma **conta dedicada** às provisões: cada parcela lançada é uma transação real e altera o
saldo da conta escolhida.

## Lançamento das parcelas

- No dia 1 de cada mês o sistema lança automaticamente as parcelas vencidas.
- **Lançar agora** faz o mesmo na hora.
- Provisão gera um **débito** (despesa); diferimento gera um **crédito** (receita).
- Parcelas de um [período fechado](help:periods) ficam como **Ignorada** e são lançadas de
  novo se o período for reaberto.

## Cancelar

**Cancelar cronograma** encerra o que falta; o que já foi lançado permanece.

## Rateio entre centros de custo

Ao editar uma transação, a seção **Rateio** divide o valor entre vários [centros de custo](help:centros-de-custo)
por percentual ou por valor. A soma precisa fechar com o valor da transação (a última linha
completa os 100% sozinha). Os relatórios por centro de custo passam a usar a fatia de cada centro.
