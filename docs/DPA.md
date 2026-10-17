# Acordo de Processamento de Dados (DPA) — SyncroFin Enterprise

**Versão 1.0 — 2026-10-06**

Este documento descreve como o SyncroFin Enterprise processa dados pessoais de clientes
e identifica os suboperadores (subprocessadores) utilizados, conforme exigido pela
LGPD (Lei 13.709/2018) e pelo GDPR (Regulamento (UE) 2016/679).

---

## 1. Identificação das partes

| Papel | Descrição |
|-------|-----------|
| **Controlador** | Organização que contrata e administra a instância do SyncroFin Enterprise |
| **Operador** | Gustavo Flandal — detentor do código SyncroFin Enterprise (AGPL-3.0 + licença Enterprise) |
| **Suboperadores** | Ver Seção 3 |

---

## 2. Dados pessoais tratados

O SyncroFin Enterprise processa as seguintes categorias de dados pessoais:

| Categoria | Exemplos | Base legal típica |
|-----------|----------|-------------------|
| Dados de identificação | Nome, e-mail, CPF/CNPJ | Execução de contrato |
| Dados financeiros | Saldo, transações, extratos | Execução de contrato |
| Dados de acesso | IP, user-agent, logs de auditoria | Interesse legítimo (segurança) |
| Dados fiscais | Chave de acesso NF-e, CNPJ emitente | Obrigação legal |

---

## 3. Suboperadores

### 3.1 Conectores bancários (opcional)

| Suboperador | Serviço | País | Dados transmitidos | DPA do fornecedor |
|-------------|---------|------|--------------------|-------------------|
| **Pluggy** | Aggregação Open Finance/Open Banking | 🇧🇷 Brasil | `item_id` criptografado, transações brutas | [pluggy.ai/privacy](https://www.pluggy.ai/privacy) |
| **Enable Banking** | Aggregação bancária europeia | 🇪🇺 UE | `item_id` criptografado, transações brutas | [enablebanking.com/legal](https://enablebanking.com/legal) |

> O `item_id` do Pluggy é armazenado **criptografado** (`item_id_enc`) na coluna `bank_connections.item_id_enc`. A chave Fernet deriva de `SECRET_KEY` via PBKDF2; o plaintext nunca é persistido.

### 3.2 Emissão de notas fiscais (opcional, B1)

| Suboperador | Serviço | País | Dados transmitidos | DPA do fornecedor |
|-------------|---------|------|--------------------|-------------------|
| **Focus NFe** | Emissão NFS-e/NF-e | 🇧🇷 Brasil | CNPJ, dados da fatura, valor | [focusnfe.com.br/privacidade](https://focusnfe.com.br/privacidade) |
| **eNotas** | Emissão NFS-e/NF-e | 🇧🇷 Brasil | CNPJ, dados da fatura, valor | [enotas.com.br/politica-privacidade](https://www.enotas.com.br/politica-privacidade) |
| **PlugNotas** | Emissão NFS-e/NF-e | 🇧🇷 Brasil | CNPJ, dados da fatura, valor | [plugnotas.com.br/politica-privacidade](https://plugnotas.com.br/politica-privacidade) |

### 3.3 Cobranças por boleto e PIX (opcional, B2)

| Suboperador | Serviço | País | Dados transmitidos | DPA do fornecedor |
|-------------|---------|------|--------------------|-------------------|
| **Asaas** | Boleto bancário e PIX dinâmico | 🇧🇷 Brasil | CPF/CNPJ do pagador, endereço, valor | [asaas.com/politica-de-privacidade](https://www.asaas.com/politica-de-privacidade) |

### 3.4 Modelos de linguagem / Agentes de IA (opcional, módulo Agents)

| Suboperador | Serviço | País | Dados transmitidos |
|-------------|---------|------|--------------------|
| **Anthropic** | Claude API | 🇺🇸 EUA | Fragmentos de dados financeiros no prompt (escopo configurável por workspace) |

> O envio de dados para LLMs é **desabilitado por padrão** (`AGENTS_ENABLED=false`).
> Quando habilitado, o administrador do workspace pode restringir quais dados podem sair
> (configuração D6). Os dados enviados nunca incluem credenciais ou senhas.

### 3.5 Câmbio e cotações (opcional)

| Suboperador | Serviço | Dados transmitidos |
|-------------|---------|------------------|
| **Open Exchange Rates** | Taxas de câmbio | Somente moedas solicitadas (sem dados pessoais) |
| **Tesouro Direto** | Preços de títulos públicos BR | Sem dados pessoais |

---

## 4. Transferências internacionais

Os suboperadores que processam dados fora do Brasil (Anthropic, Enable Banking) estão
sujeitos a mecanismos adequados de transferência internacional:

- **Enable Banking**: Opera na UE sob GDPR; aplica-se a adequação por reciprocidade LGPD-GDPR.
- **Anthropic**: Aplica cláusulas contratuais padrão (SCCs) conforme [anthropic.com/privacy](https://www.anthropic.com/privacy).

---

## 5. Retenção de dados

| Tipo de dado | Retenção padrão | Observação |
|-------------|----------------|------------|
| Transações financeiras | Enquanto o workspace existir | Exportável pelo titular |
| Logs de auditoria | Configurável pelo admin (padrão: 12 meses) | Ver `AccessRetention` |
| Logs de acesso | Configurável (padrão: 90 dias) | Ver `AccessRetention` |
| Solicitações do titular | 5 anos | Exigência LGPD |
| Dados de sessão | 30 dias após inatividade | |

---

## 6. Direitos do titular

Os titulares podem exercer os seguintes direitos via **Configurações → Privacidade dos dados**
(ou pelo canal do titular em `/admin/data-requests`):

- Acesso e portabilidade (exportação JSON/ZIP)
- Retificação
- Exclusão / anonimização
- Revogação de consentimento
- Informação sobre compartilhamento

---

## 7. Contato do encarregado (DPO)

Para questões relacionadas a este DPA, entre em contato em: **gustavoflandal@gmail.com**

---

## 8. Atualizações

Este DPA pode ser atualizado quando novos suboperadores forem adicionados ou quando
obrigações legais mudarem. A versão vigente é sempre a que consta neste arquivo no
repositório.
