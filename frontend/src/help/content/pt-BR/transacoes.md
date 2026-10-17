# Transações

Em **Transações** ficam todos os lançamentos do workspace. Você navega mês a mês, busca, filtra, edita e faz ações em
lote.

## Duas visões

No topo, alterne entre **Lista** e **Calendário**.

- **Lista:** uma linha por transação, com data, descrição, categoria, conta, valor e status.
- **Calendário:** os dias do mês com a atividade de cada um. Escolha ver o **Saldo** ou a **Atividade**; o modo
  **Compacto** ou **Detalhado**; e o número de contas. Clique em um dia para ver as transações e para
  **Adicionar receita** ou **Adicionar despesa** naquela data. Transações **previstas** (de [Recorrentes](help:recorrentes))
  aparecem identificadas.

## Criar uma transação

Clique em **Adicionar Transação** e preencha:

| Campo | Observação |
|-------|------------|
| **Tipo** | **Despesa** (saída) ou **Receita** (entrada). |
| **Descrição** | Texto livre. |
| **Valor** e **Moeda** | Se a moeda for diferente da conta, veja *Moedas diferentes* abaixo. |
| **Data** | Quando aconteceu. |
| **Conta** | Onde o dinheiro entrou ou saiu. |
| **Categoria** | Opcional, mas importante para orçamentos e relatórios. |
| **Pessoa** | Quem pagou ou recebeu ([Pessoas](help:pessoas)). |
| **Notas** | Texto livre. Use **#tags** (por exemplo `#trabalho #reembolsável`) para marcar. |
| **Anexos** | Arraste arquivos ou clique. Aceita jpg, jpeg, png, webp, gif, heic e pdf, **até 10 MB** cada, com um limite de anexos por transação. |

O botão de salvar tem variações em **Mais opções de salvar**: **Salvar e novo** (limpa e abre outra) e **Salvar e
duplicar** (mantém os dados para você ajustar). Em qualquer linha, **Duplicar** cria uma cópia.

### Repetir em parcelas

Marque **Repetir em parcelas** para lançar uma compra parcelada: informe o **número de parcelas** e a
**frequência**. O sistema cria a série. Ao **editar ou excluir** uma parcela, ele pergunta **até onde aplicar**:
**Apenas esta**, **Esta e as futuras** ou **Todas as parcelas**.

### Tornar recorrente

**Tornar recorrente** cria uma [conta recorrente](help:recorrentes) a partir da transação, para que ela se repita
automaticamente.

### Moedas diferentes

Se a moeda da transação difere da moeda do workspace, o valor é **convertido automaticamente** pela taxa do dia. Você
pode preencher **Convertido** e **Taxa de câmbio** à mão. Se aparecer *"Taxa de câmbio indisponível — usando fallback
1:1"*, o sistema não conseguiu uma taxa: defina manualmente ou peça ao administrador para configurar o provedor de
câmbio.

## Status: Pendente e Lançada

Transações **Pendentes** ainda não foram compensadas pelo banco. As **Lançadas** já foram. Você pode ocultar ou
mostrar pendentes nos filtros.

## Transações sincronizadas

Transações que vieram de uma **conexão bancária** são "sincronizadas": nelas só é possível editar **categoria e
notas**. O restante vem do banco e é mantido por ele.

## Busca, filtros e colunas

- **Buscar transações…** procura na descrição.
- **Filtros:** por **Data** (Hoje, Últimos 7/30/90 dias, Este mês, Este ano ou **Período personalizado**), **Valor**
  (mínimo e máximo; o mesmo valor nos dois busca o valor exato), **Categoria**, **Conta**, **Pessoa**, **Tipo** e
  **Status**. **Limpar filtros** volta ao padrão.
- **Colunas:** escolha quais colunas mostrar (Data, Descrição, Categoria, Conta, Valor, Pessoa, Notas, Tags,
  Arquivos, Tipo, Status). **Restaurar padrão** desfaz.
- **Ocultar ignoradas:** esconde as transações ignoradas (veja adiante).
- **Exportar CSV:** baixa as transações filtradas (ou só as selecionadas: **Exportar Selecionadas**).

## Ações em lote

Marque transações pela caixa da esquerda. Aparece uma barra com:

- **Aplicar** uma **categoria** a todas;
- **Adicionar tags** / **Remover tags**;
- **Adicionar ao grupo** (dividir despesas: [Grupos](help:grupos));
- **Vincular como transferência** (com exatamente **2** selecionadas);
- **Excluir selecionadas** (**definitivo**, inclusive contrapartes de transferência e anexos).

## Categorizar e criar regras

Ao categorizar uma transação, o menu oferece **Criar Regra**: cria uma [regra](help:regras) para que transações
parecidas sejam categorizadas sozinhas no futuro. Também há **Adicionar a regra existente**, que soma a descrição a
uma regra que você já tem.

## Transferências entre contas

Uma transferência é dinheiro que sai de uma conta sua e entra em outra.

- **Criar:** use **Transferência** (conta de origem, de destino, valor, descrição). Se as moedas forem diferentes,
  informe o valor de destino ou deixe em branco para converter.
- **Vincular duas transações já existentes:** selecione as duas (um débito e um crédito, de contas diferentes) e use
  **Vincular como transferência**; ou, a partir de uma delas, o assistente sugere a **Melhor correspondência** pela
  data e valor. Se a contraparte for uma conta manual e ainda não existir, ele pode **criá-la**.
- **Efeito:** transferências **não entram** em receitas e despesas de relatórios e do painel. Editar ou excluir um
  lado afeta o outro. **Desvincular transferência** devolve as duas ao normal.

## Ignorar e excluir dos relatórios

| Opção | Efeito |
|-------|--------|
| **Ignorar** | A transação **some dos totais** e do saldo da conta. Fica guardada e pode ser reativada (**Não ignorar**). |
| **Excluir dos relatórios** | Continua **afetando o saldo** da conta, mas **não conta** como receita ou despesa. Útil para ajustes de saldo. |

## Faturas de cartão de crédito

Em contas de cartão, uma compra pode ser movida para outra fatura definindo a **Data efetiva da fatura**
(manual, sobrescreve o ciclo automático). Veja [Contas](help:contas).

## Ligação com Cobranças

Em workspaces de negócio, uma transação que quita uma cobrança mostra uma etiqueta **Cobrança nº…**. Uma etiqueta
**Pergunta** indica que um pagamento pode quitar uma cobrança e espera sua resposta ([Conciliação](help:conciliacao)).

## Excluir uma transação

Pelo menu da linha ou dentro da transação. O sistema pede confirmação. Se ela é uma parcela, pergunta o escopo.
