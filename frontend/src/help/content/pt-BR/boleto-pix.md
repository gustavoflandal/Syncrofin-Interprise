# Cobrança por Boleto e PIX

O SyncroFin pode emitir **boletos bancários** e **cobranças PIX dinâmicas** vinculados às suas faturas,
e registrar automaticamente o pagamento quando o provedor confirmar a liquidação via webhook.

> O módulo só está disponível em workspaces do tipo **Negócios** com permissão `billing.manage`.

## Configurar o provedor

Em **Configurações do workspace → Cobranças (Boleto/PIX)**:

1. Selecione o **Provedor** (Asaas é o suportado atualmente).
2. Escolha o **Entorno**: *Sandbox* para testes, *Produção* para cobranças reais.
3. Cole a **API Key** obtida no painel do provedor.
4. Clique em **Salvar configuração**.

Após salvar, um **Token do webhook** é gerado automaticamente. Copie-o e registre no painel do provedor
como chave de autenticação do webhook, apontando para:

```
POST https://seu-dominio/api/billing/webhook/asaas/{workspace_id}
```

## Emitir uma cobrança

Na tela de detalhes de uma fatura, clique em **Emitir boleto** ou **Emitir PIX**:

| Campo | Notas |
|-------|-------|
| Método | Boleto bancário ou PIX |
| Valor | Pré-preenchido com o valor da fatura |
| Vencimento | Data limite de pagamento |
| Nome e CPF/CNPJ | Dados do pagador |
| Endereço | Obrigatório para boleto |

Clique em **Emitir**. O SyncroFin cria a cobrança no provedor e exibe o link do boleto ou o QR Code PIX.

## Situação da cobrança

| Situação | Significado |
|----------|-------------|
| Pendente | Criada, aguardando geração pelo provedor |
| Aguardando pagamento | Disponível para o pagador |
| Confirmado / Recebido | Pagamento confirmado pelo provedor |
| Vencido | Prazo ultrapassado sem pagamento |
| Cancelado | Cancelado manualmente ou pelo provedor |
| Erro | Falha na criação — veja a mensagem de erro |

## Liquidação automática

Quando o webhook do provedor chegar confirmando o pagamento, o SyncroFin:

1. Atualiza o status da cobrança para **Confirmado** ou **Recebido**.
2. Cria uma **Transação** de receita no workspace.
3. Vincula a transação à fatura via **Alocação**, encerrando o título automaticamente.

Não é necessária nenhuma ação manual.

## Atualizar ou cancelar

- **Atualizar status**: consulta o provedor e sincroniza o estado atual.
- **Cancelar cobrança**: cancela junto ao provedor. Cobranças já pagas não podem ser canceladas.
