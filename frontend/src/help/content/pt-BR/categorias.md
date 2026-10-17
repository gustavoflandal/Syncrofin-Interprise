# Categorias

**Categorias** classificam receitas e despesas. É por elas que os orçamentos, os relatórios e o gráfico *Gastos por
Categoria* funcionam.

## Categorias e grupos

- Uma **categoria** tem nome, **ícone** e **cor**.
- Categorias podem ser organizadas em **grupos** (por exemplo, "Moradia" reunindo Aluguel, Condomínio e Luz).
  Uma categoria pode ficar **Sem grupo**. Use **Expandir tudo** / **Recolher tudo** para navegar.

Ao criar um workspace, ele já vem com **categorias e grupos padrão** (você pode ocultá-los ou editá-los).

## Criar, editar e excluir

- **Adicionar Categoria:** informe nome, grupo, ícone e cor.
- **Adicionar Grupo:** grupos têm nome, ícone, cor e **posição** (a ordem na lista).
- **Excluir:** uma categoria **em uso** por transações, regras ou orçamentos não pode ser excluída até que
  esses registros sejam ajustados (*"Esta categoria ainda está em uso"*). Excluir um **grupo** mantém as categorias
  dele, que passam a ficar sem grupo.

## Ocultar categorias padrão

Categorias e grupos **padrão** podem ser **ocultados** em vez de excluídos: deixam de aparecer nos seletores e não
são mais atribuídos automaticamente. Se regras ativas usam a categoria, o sistema avisa e pergunta se você quer
**Apenas ocultar** ou **Ocultar e desligar as regras**. Dá para **Mostrar** de novo depois.

## Tratamento especial

Duas opções mudam como as transações de uma categoria contam nos relatórios:

| Opção | Efeito |
|-------|--------|
| **Tratar como transferência** | As transações da categoria **não contam** como receita nem despesa. Serve para movimentos que trocam de lugar, como **aplicar em um investimento** (a contrapartida está em [Patrimônio](help:patrimonio), não em uma conta). |
| **Ignorar transações** | As transações da categoria são tratadas como se não existissem nos cálculos de receita e despesa. |

Categorias marcadas mostram uma etiqueta (*Transferência* ou *Ignorado*).

## Dicas

- Poucas categorias bem escolhidas rendem relatórios melhores que dezenas de categorias quase iguais.
- Crie [regras](help:regras) para categorizar automaticamente o que se repete.
- Categorizar em lote: em [Transações](help:transacoes), selecione várias e use **Aplicar**.
- Para classificar lançamentos por departamento ou projeto sem alterar o plano de contas, use [Centros de Custo](help:centros-de-custo).
