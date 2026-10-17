# Importar

**Importar** traz transações (e ordens de investimento) de arquivos, sem digitar. É o caminho para bancos que não
têm sincronização.

## Formatos aceitos

**OFX**, **QIF**, **CAMT** (extrato bancário europeu), **CSV** e **CNAB** (240/400). A tela tem três abas:
**Transações**, **Investimentos** e **NF-e XML**.

## Importar transações

1. Arraste o arquivo para a área **Arraste um arquivo ou clique para selecionar** (ou clique e escolha).
2. O sistema lê o arquivo e mostra a **Pré-visualização**, com o número de receitas e despesas encontradas.
3. Escolha a conta em **Importar para:** (obrigatório).
4. Revise a lista. Você pode **buscar**, filtrar por **categoria** ou **status**, e **excluir linhas** que não quer
   (uma linha excluída aparece como *Excluída*). Categorias podem ser ajustadas na própria pré-visualização;
   quando uma regra sugere uma, aparece **Sugerida**.
5. Confira o **Impacto no saldo** e clique em **Importar N transações**.

Ao terminar, o sistema informa quantas foram importadas, quantas eram **duplicadas** (e foram ignoradas) e quantas
você excluiu.

### Opções (principalmente para CSV)

| Opção | O que faz |
|-------|-----------|
| **Formato da data** | *Automático (detectar)* ou um formato fixo. |
| **Inverter valores** | Troca entrada e saída (alguns bancos exportam o sinal ao contrário). |
| **Ignorar transações duplicadas** | Não importa de novo o que já existe. Ligado por padrão. |
| **Separar colunas entrada/saída** | Para arquivos com uma coluna de crédito e outra de débito: aponte a **Coluna de entrada** e a **Coluna de saída**. |

### Mapeamento de colunas

Se o sistema **não reconhece as colunas** do CSV, aparece **Mapeamento de colunas**: associe cada coluna do seu arquivo
aos campos do SyncroFin (**data**, **descrição**, **valor**, **tipo**, **categoria**, **moeda**, **câmbio**,
**pessoa**, **ID da transação**, **notas**). Deixe em *Detectar automaticamente* para manter a detecção. Data, descrição
e valor são o mínimo.

Se algumas linhas **não puderam ser lidas** (data ou valor inválidos), o sistema avisa e **Ver detalhes** mostra a linha,
o valor e o motivo. Elas são ignoradas.

**Baixar modelo CSV** entrega um arquivo de exemplo com as colunas esperadas.

## Histórico de Importações

Abaixo, o **Histórico de Importações** lista cada importação: data, arquivo, formato, conta, quantidade e totais de
crédito e débito. Em cada uma você pode **Desfazer importação**, que **exclui as transações daquele arquivo**. Não
dá para desfazer o desfazer.

## Importar investimentos

Na aba **Investimentos** (ou pelo botão **Importar ordens** em [Patrimônio](help:patrimonio)):

- Use um CSV com **Ativo** (código), **Data**, **Quantidade** e **Preço** (obrigatórios); **Taxas**, **Compra/Venda**,
  **Moeda** e **Observações** são opcionais. **Quantidade negativa** é lida como **venda**.
- Escolha a **Carteira** de destino. Se o ativo já existe em outra carteira, o sistema **avisa** antes de criar uma
  segunda posição.
- A pré-visualização mostra ordens prontas, ativos criados/encontrados e ordens **já importadas** (que são
  puladas). Linhas com problema mostram o motivo: *sem ativo*, *data ilegível*, *quantidade ilegível*, *preço
  ilegível*, *ativo não encontrado no provedor de cotações* ou *venda maior do que a posição*.
- **Baixar modelo** entrega o CSV de exemplo.

## Importar NF-e XML (nota fiscal de fornecedor)

Na aba **NF-e XML** você importa o arquivo XML emitido pelo seu fornecedor. O sistema lê a nota
e cria um **título a pagar** (contas a pagar) automaticamente.

1. Arraste o arquivo `.xml` da NF-e (envelope `nfeProc` ou `NFe`) para a área de importação.
2. O sistema mostra a **Prévia**: emitente, CNPJ, número, valor total, tributos e itens.
3. Informe a **Data de vencimento** do pagamento.
4. Clique em **Criar título a pagar**.

A nota é identificada pela **chave de acesso** (44 dígitos): reimportar o mesmo arquivo é
**idempotente** e retorna o título já existente sem duplicar.

> Somente NF-e modelo 55. NFS-e municipal não é suportada aqui.

## Extrato CNAB

Os arquivos **CNAB 240** e **CNAB 400** (extensão `.cnab`, `.rem` ou `.ret`) são detectados
automaticamente na aba **Transações**, junto com OFX e CSV. Arraste o arquivo normalmente —
o sistema detecta o formato pelo comprimento de linha.

## Dicas

- Sempre escolha a conta certa antes de importar; para desfazer, use o histórico.
- Importações e regras trabalham juntas: transações importadas passam pelas suas [regras](help:regras) e já saem
  categorizadas quando há correspondência.
- Para ver os títulos a pagar criados via NF-e, acesse [Contas a Pagar/Receber](help:titulos).
