# Exportar para o contador

O SyncroFin **não é um sistema contábil**: quem escritura é o seu contador. O que ele faz é entregar a **matéria-prima
limpa**: os lançamentos e resumos do período, em arquivos que abrem direto no **Excel** ou no **LibreOffice**.

## Como exportar

1. Abra o **menu da conta** (rodapé do menu lateral) → **Exportar para o contador**.
2. Escolha o **Período**: **Mês passado**, **Este mês**, **Último trimestre**, **Este ano**, **Ano passado** ou
   **Personalizado** (informe **De** e **Até**). O intervalo escolhido aparece logo abaixo. O máximo é de 10 anos.
3. (Opcional) Defina uma **Senha** (pelo menos 8 caracteres) para proteger o arquivo. Ele fica **criptografado com
   AES-256** e abre em qualquer compactador. Envie a senha por **outro canal**, não junto do arquivo.
4. Clique em **Exportar**. Baixa um `.zip`.

## O que vem no pacote

| Arquivo | Conteúdo |
|---------|----------|
| `lancamentos.csv` | Cada movimento **efetivado** do período: data, **data efetiva (caixa)**, conta, descrição, favorecido, categoria, grupo, tipo, **valor com sinal** (receita positiva, despesa negativa), moeda, valor na moeda principal, observações e ID. |
| `resumo_por_categoria.csv` | Receitas e despesas por categoria. |
| `resumo_mensal.csv` | Receitas, despesas e resultado, mês a mês. |
| `plano_de_contas.csv` | Grupos e categorias. |
| `contas.csv` | Contas e o saldo **atual**. |
| `titulos.csv` | Cobranças emitidas no período (a receber e a pagar): número, **competência**, vencimento, valor quitado, saldo, situação e dias de atraso. |
| `LEIA-ME.txt` | Explica cada arquivo e os critérios. |

**Formato:** separador `;`, decimal com vírgula, datas `dd/mm/aaaa`, codificação UTF-8 com BOM (acentos corretos no
Excel).

## O que fica de fora e por quê

- **Transferências entre as suas contas** e **saldos iniciais** aparecem em `lancamentos.csv`, mas **não** entram nos
  resumos (não são receita nem despesa).
- Transações **ignoradas** e categorias marcadas como *ignorar* ficam de fora.
- Nos resumos, só entram valores que puderam ser expressos na **moeda principal** do workspace.
- Textos que começariam com `=`, `+`, `-` ou `@` recebem um apóstrofo, para o Excel **não** tratá-los como fórmula
  (segurança: descrições vindas do banco são texto de terceiros).

## Dando acesso ao contador

Em vez de mandar arquivos, você pode **convidar o contador** para o workspace com o papel **Leitor** (somente
leitura). Ele entra, vê os dados e pode fazer **esta mesma exportação** sozinho, sem poder alterar nada. Veja
[Workspace](help:workspace).
