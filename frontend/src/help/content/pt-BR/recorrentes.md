# Recorrentes

**Transações Recorrentes** são contas e receitas que se repetem: aluguel, salário, assinaturas, mensalidades.
Cadastrá-las alimenta as **previsões** (saldo projetado, entradas e saídas previstas, previsão de caixa) e pode
lançar as transações automaticamente.

## Criar

Clique em **Adicionar Recorrente**:

| Campo | Observação |
|-------|------------|
| **Descrição**, **Valor**, **Moeda** | O que se repete. |
| **Tipo** | **Entrada** ou **Saída**. |
| **Frequência** | **Mensal**, **Trimestral**, **A cada 6 meses**, **Semanal**, **A cada 2 semanas** ou **Anual**. |
| **Dia do mês** | Para as frequências mensais ou maiores. |
| **Ajuste de fim de semana** | *Sem ajuste*, *Sexta-feira antes do fim de semana* ou *Segunda-feira depois do fim de semana*: útil para contas que vencem em dia útil. |
| **Data de início** e **Data de fim** (opcional) | Quando começa e, se houver, quando termina. |
| **Categoria** e **Conta** | Onde a transação será lançada. |
| **Gerar transações automaticamente** | Cria a transação sozinha a cada vencimento. Desligue para esperar o lançamento **real** (por exemplo, quando o débito virá do banco). |

Também dá para criar uma recorrente **a partir de uma transação**: em [Transações](help:transacoes), use
**Tornar recorrente**.

## A lista

Cada recorrente mostra a **Próxima** ocorrência, o **Status** (**Ativo** / **Inativo**) e ações de editar e excluir.
**Gerar Pendentes** cria agora as transações que já venceram e ainda não foram geradas.

## Como o sistema casa o lançamento real

Quando uma transação real (importada ou sincronizada) corresponde a uma recorrente (mesma conta, valor próximo,
descrição parecida), o sistema **vincula** as duas e avança a próxima ocorrência, para não contar duas vezes.
Você vê a etiqueta **Recorrente** na transação e pode **Desvincular**. As regras desse casamento estão em
[Conciliação](help:conciliacao).

## Moeda estrangeira

Para recorrentes em outra moeda, o valor mostrado é uma **estimativa** pela última taxa de câmbio; o valor final
pode mudar quando a transação real chega.

## Onde as recorrentes aparecem

- No **calendário** de [Transações](help:transacoes), como itens **previstos**;
- Nos cartões **previstos** do [Painel](help:painel);
- Na **previsão de caixa** ([Saúde financeira](help:saude-financeira)).

## Excluir

Excluir a **definição** recorrente **não apaga** as transações que ela já gerou.

## Impostos

Obrigações como DAS, DARF e ISS ficam na aba **Impostos** desta página. Veja [Obrigações fiscais e retenções](help:obrigacoes-fiscais).
