# Cobranças

**Cobranças** (faturas) ficam nos **workspaces de negócio**. Servem para acompanhar **o que os clientes te devem e o
que já entrou** e, se você quiser, para **emitir o documento** que o cliente recebe. Também aceitam **contas a pagar**
(fornecedores).

> O módulo só aparece em workspaces do tipo **Negócios**. Um workspace pessoal não tem Cobranças.

## Dois modos de trabalhar

Em **Configurações de cobrança**, escolha o **Modo**:

| Modo | Para quem |
|------|-----------|
| **Acompanhar recebimentos** | Você emite a fatura em **outro lugar** (seu sistema fiscal, por exemplo). Aqui só acompanha quem deve e se pagou. Basta o valor e o vencimento. |
| **Emitir documentos** | O SyncroFin **escreve** a fatura que o cliente recebe, com itens, impostos, PDF e link. Exige os itens da cobrança. |

Outras configurações: **prefixo da numeração**, **prazo de pagamento** (dias), **nome do seu negócio**,
**razão social**, **endereço**, **dados para pagamento** (chave Pix, IBAN, conta), **logo**, **cor de destaque**,
**rodapé** e os **rótulos** do documento.

## A lista

O topo resume: **A receber**, **Vencido**, **Recebido no mês**, **A vencer** e a distribuição **Por idade** (a vencer,
1–30, 31–60, 61–90, 90+ dias). Filtre por **Todas**, **Em aberto**, **Vencidas**, **Recebidas** e **Rascunhos**, e por
exercício (ano).

## Situação de uma cobrança

| Situação | Significa |
|----------|-----------|
| **Rascunho** | Em edição. Pode ser alterado e excluído. Ainda sem número. |
| **Em aberto** | Emitida, aguardando pagamento. |
| **Parcial** | Recebeu parte do valor. |
| **Recebida** | Totalmente quitada. |
| **Vencida** | Passou do vencimento sem quitar. |
| **Cancelada** | Anulada. Mantém o número e vale zero. |
| **Incobrável** | Você desistiu de cobrar (dar baixa como perda). |

A situação **paga / parcial / vencida** é **calculada** a partir dos pagamentos e do vencimento: você só *decide*
emitir, cancelar ou dar baixa.

## Criar uma cobrança

**Nova cobrança**: escolha o **Cliente** ([Pessoas](help:pessoas)), o **Valor** (ou os **Itens**: descrição, quantidade,
unidade, valor unitário e alíquota), a **emissão**, o **Vencimento**, a **moeda** e as **Observações**. Salve como
**rascunho** ou **Emitir**.

Regras importantes:

- **Emitida não muda.** Se errou, **cancele** e emita outra.
- Só **rascunho** pode ser **excluído**.
- O vencimento não pode ser anterior à emissão e o total não pode ser zero.
- A **data de competência** (quando o serviço foi prestado) pode diferir da emissão e é usada na contabilidade.

## Receber: vincular pagamentos

Quando o dinheiro entra, **Vincular pagamento**: escolha a transação de entrada (na mesma moeda). Deixe o valor em
branco para abater o quanto ela cobrir. Uma cobrança pode ter vários recebimentos (**Parcial**). Você também pode
**Desvincular**. Vincular a transação também **marca a cobrança como recebida** quando quita o total. O sistema
tenta fazer isso **sozinho**: veja [Conciliação](help:conciliacao).

## Outras ações

**Baixar PDF**, **Compartilhar** (gera um **link público** que mostra a cobrança a quem tiver o endereço; **Revogar
link** desativa), **Reabrir** (uma incobrável), **Cancelar**, **Dar baixa como perda**, anexar **documentos** (aba
*Documentos*: o arquivo do documento fiscal, comprovantes, contratos).

Contas a **pagar** (fornecedores) usam a mesma tela com o sentido invertido: **A pagar** e **Pago no mês**. **Não**
podem ser compartilhadas por link.

## Visão consolidada AR/AP

Para ver o resumo de todas as contas a receber e a pagar com o aging completo, acesse
[Títulos](help:titulos).

## Cobranças no painel e nos avisos

- Vencendo em até 3 dias ou vencidas geram **avisos** no sino ([Notificações](help:notificacoes)).
- Entram na **previsão de caixa** ([Saúde financeira](help:saude-financeira)).
- Aparecem no **pacote do contador** ([Exportar para o contador](help:contador)).

## Documentos fiscais

O sistema **valida e formata** documentos fiscais por país (CPF/CNPJ etc.), conforme a **jurisdição fiscal** do
workspace ([Workspace](help:workspace)). Para emitir NF-e diretamente a partir de uma fatura, configure um provedor
externo — veja [Emissão de NF-e](help:emissao-nfe). Para cobrar com boleto ou PIX, veja [Boleto e PIX](help:boleto-pix).

## Retenções

Em faturas a receber, registre os impostos retidos pelo cliente; veja [Obrigações fiscais e retenções](help:obrigacoes-fiscais).
