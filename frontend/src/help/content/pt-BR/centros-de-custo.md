# Centros de Custo

**Centros de Custo** permitem criar dimensões opcionais para classificar seus lançamentos por
departamento, projeto ou área (ex.: Marketing, Operações, Financeiro). Use-os quando precisar
analisar gastos ou receitas por unidade de negócio sem alterar o plano de contas.

## Criar um centro de custo

Clique em **Novo centro de custo** e preencha:

- **Nome** — obrigatório; ex.: "Marketing"
- **Código** — opcional; sigla curta para filtros e exportação (ex.: "MKT")
- **Descrição** — opcional; anotação interna sobre o propósito do centro

Após salvar, o centro aparece na lista e fica disponível para ser vinculado a lançamentos.

## Usar em lançamentos

No formulário de cadastro ou edição de um lançamento, o campo **Centro de custo** exibe os
centros ativos do workspace. Basta selecionar o desejado. Deixe em branco (ou selecione
"(nenhum)") quando o lançamento não pertencer a nenhum centro específico.

## Editar um centro de custo

Clique no ícone de lápis ao lado do centro. Você pode alterar o nome, o código e a descrição.
Centros desativados podem ser reativados marcando a opção **Ativo** no formulário de edição.

## Desativar e excluir

Clique no ícone de lixeira ao lado do centro. O comportamento depende do uso:

- **Excluir** — remove permanentemente se o centro não tiver lançamentos associados.
- **Desativar** — se houver lançamentos vinculados, o centro é desativado automaticamente.
  Ele fica invisível em novos lançamentos, mas continua preservado nos registros históricos
  para manter a integridade dos dados passados.

## Boas práticas

- Mantenha os códigos curtos e padronizados (ex.: "MKT", "OPS", "ADM") para facilitar filtros
  e exportações para o contador.
- Crie apenas os centros que fazem sentido para o seu negócio; muitos centros fragmentados
  dificultam a análise.
- Combine centros de custo com categorias para ter visões complementares: a categoria responde
  "o que foi gasto", o centro de custo responde "onde foi gasto".

Para dividir um único lançamento entre vários centros, veja o **Rateio** em [Provisões e diferimentos](help:provisoes).
