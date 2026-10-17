# Emissão de NF-e

O SyncroFin Enterprise pode emitir **NF-e (modelo 55)** diretamente a partir de faturas, usando um
provedor externo como o **Focus NFe**. O sistema **nunca é um emissor direto**: ele monta e transmite
o documento ao provedor, que se comunica com a SEFAZ.

> Disponível apenas em workspaces do tipo **Negócios** com o módulo de Cobranças ativo.

## Configurar o provedor

1. Abra **Configurações do workspace**.
2. Role até **Emissão de NF-e**.
3. Escolha o **Provedor** (Focus NFe, eNotas ou PlugNotas).
4. Escolha o **Ambiente** — use *Homologação* para testes antes de ir para produção.
5. Cole a **Chave de API** obtida no painel do provedor.
6. Preencha o **CNPJ do emitente** e a **Série padrão** (geralmente `1`).
7. Clique em **Salvar configuração**.

Apenas usuários com permissão **fiscal.admin** (Proprietário ou papel personalizado) podem salvar a configuração.

## Emitir uma NF-e a partir de uma fatura

1. Abra a fatura em **[Cobranças](help:cobrancas)**.
2. No painel **Emissão de NF-e**, clique em **Emitir NF-e**.
3. Confirme o envio na caixa de diálogo.
4. O status inicial é **Processando**. Clique em **Atualizar status** para consultar o retorno da SEFAZ.
5. Quando autorizada, o status muda para **Emitida** e aparecem os links de **XML** (NF-e) e **DANFE** (PDF).

> A **chave de acesso** de 44 dígitos fica visível no painel após a autorização.

## Status possíveis

| Status | Significado |
|--------|-------------|
| **Pendente** | Aguardando envio ao provedor |
| **Processando** | Enviado à SEFAZ; aguardando retorno |
| **Emitida** | Autorizada pela SEFAZ |
| **Cancelada** | Cancelada pela SEFAZ a pedido do emitente |
| **Erro** | Rejeitada ou falha de comunicação |

## Cancelar uma NF-e

1. Com o status **Emitida**, clique em **Cancelar NF-e**.
2. Informe o motivo (obrigatório para a SEFAZ).
3. Confirme. O cancelamento é **irreversível**.

> O prazo máximo de cancelamento varia por estado — consulte o provedor para saber a janela disponível.

## Dicas

- **Ambiente de homologação** — use para testar sem custo fiscal. As NF-e emitidas em homologação não têm validade jurídica.
- **NF-e importada** — ao importar um XML de NF-e de fornecedor via [Importar](help:importar), o sistema cria uma **conta a pagar**, não emite uma nota nova.
- **eNotas e PlugNotas** — as integrações estão previstas; enquanto não estiverem disponíveis, o sistema indicará o erro ao tentar emitir.
