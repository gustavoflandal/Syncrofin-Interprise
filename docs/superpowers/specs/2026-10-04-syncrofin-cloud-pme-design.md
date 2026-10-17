# SyncroFin Cloud para PMEs — Design

**Data:** 2026-10-04  
**Status:** aprovado pelo product owner  
**Escopo:** posicionamento, modelo de negócio e as quatro frentes de desenvolvimento da versão Cloud para pequenas e médias empresas brasileiras.

---

## 1. Contexto e posicionamento

O SyncroFin Enterprise passa a ser oferecido como **SyncroFin Cloud**: sistema financeiro gerenciado para PMEs brasileiras, com instância dedicada por cliente incluída na mensalidade.

**Diferenciais principais:**

| Diferencial | Proposta |
|---|---|
| Privacidade real | Dados financeiros do cliente ficam numa instância própria dele, não num banco multi-tenant compartilhado |
| IA integrada | Assistente que guia o onboarding e responde perguntas sobre o negócio em linguagem natural |
| Open Finance BR | Sincronização bancária automática via Pluggy; conciliação automática sem digitar extrato |

**Público-alvo:** pequenas e médias empresas brasileiras sem TI interna, que hoje usam planilha, Conta Azul ou Omie, e sentem falta de privacidade ou de uma ferramenta que realmente entenda o contexto financeiro do negócio.

**O que o produto não é:** sistema contábil de partidas dobradas. O SyncroFin entrega a matéria-prima limpa para o contador; a escrituração é responsabilidade do sistema contábil do contador (decisão D-1a já registrada em `ENTERPRISE.md`).

**Modelo de implantação:** um VPS dedicado por cliente, provisionado automaticamente. O cliente contrata um plano mensal e acessa `cliente.syncrofin.com.br` sem saber que por trás há um servidor dedicado.

---

## 2. Abordagem escolhida

Das três abordagens avaliadas, foi escolhida a **Abordagem 3 — Plataforma + iteração**:

- Construir a infraestrutura de cloud gerenciada em paralelo com o assistente de onboarding por IA e os gaps críticos de funcionalidade.
- Lançar com 3–5 clientes piloto pagando para validar o modelo antes de escalar.
- Priorizar feedback real sobre roadmap teórico.

---

## 3. Frente 1 — Infraestrutura de cloud gerenciada

### Objetivo

Permitir provisionar, monitorar e faturar instâncias de clientes sem intervenção manual.

### Componentes

**Painel do operador** (aplicação separada, acesso restrito ao time):

- Formulário de criação de cliente: nome da empresa, e-mail do admin, plano contratado.
- Provisionamento automatizado: cria VPS, banco Postgres, Redis, roda `install.sh`, configura domínio e emite certificado TLS. Meta: instância pronta em < 5 minutos.
- Dashboard de saúde: uptime, uso de disco, status da última sincronização bancária por instância.
- Gestão de plano: ativar, suspender (inadimplência), cancelar e reativar instâncias.
- Atualização em lote: `docker pull` + restart em todas as instâncias ao publicar nova versão.

**Billing:**

- Integração com gateway BR (Asaas ou Stripe com PIX) para cobrança recorrente mensal.
- Webhooks de pagamento controlam o status da instância (ativa / suspensa).

**O que não está no escopo desta frente:**

- Multi-tenancy no mesmo banco (o isolamento por instância é o diferencial).
- Kubernetes ou auto-scaling (VPS simples cobre PME por bastante tempo).

### Base existente reutilizada

`docker-compose.prod.yml`, `install.sh`, Helm chart, imagens publicadas em `ghcr.io/gustavoflandal/syncrofin-enterprise-*`. Ajustes mínimos para parametrização por cliente (domínio, segredos gerados automaticamente).

---

## 4. Frente 2 — Assistente de onboarding por IA

### Objetivo

Eliminar a barreira de configuração inicial sem consultor, guiando o novo cliente numa conversa de 10–15 minutos que termina com o sistema pronto para uso.

### Fluxo

O sistema detecta workspace vazio no primeiro login e abre um chat em tela cheia. O assistente faz perguntas simples e age com base nas respostas:

1. Nome da empresa e regime tributário (Simples Nacional / Lucro Presumido / Lucro Real)
2. Setor de atividade principal
3. Número aproximado de funcionários
4. Bancos utilizados (oferta de conexão via Open Finance)
5. Tem contador externo? (oferece convite imediato com papel "Contador")
6. Quer configurar categorias agora ou usar o modelo padrão do setor?

Ao final, executa automaticamente:

- Configura workspace `business`, moeda BRL, jurisdição BR, fuso de São Paulo
- Cria categorias e grupos em PT-BR adequados ao setor e regime tributário
- Convida o contador como `viewer` com papel "Contador" (somente leitura + exportação)
- Conecta bancos via Open Finance se o cliente autorizou

O cliente pode dizer "pular" a qualquer momento. O assistente continua disponível pelo botão **?** para retomar qualquer configuração depois.

### Arquitetura

Aproveita o módulo de agentes existente (`app/agents/`):

- **Novas ferramentas MCP de setup** (seguindo o padrão de "proposta + confirmação" do executor atual):
  - `setup_workspace` — configura nome, tipo, moeda, jurisdição, fuso
  - `create_category_set` — cria grupos e categorias a partir de um template por setor/regime
  - `invite_member` — convida e-mail com papel específico
  - `connect_bank` — inicia fluxo de Open Finance para o banco escolhido
- **Perfil de agente `onboarding`** com acesso apenas a essas ferramentas e prompt de sistema focado em guiar o setup
- **UI:** variação em tela cheia do componente de chat existente (`components/chat`), mostrada apenas quando `workspace.setup_completed = false`
- **Flag `setup_completed`** em `Workspace`: após o onboarding (manual ou via assistente), marcada como `true` e a tela cheia não aparece mais

### Limites declarados ao usuário

O assistente deixa claro que está configurando o sistema, não prestando consultoria tributária. Perguntas sobre regime tributário são respondidas com "verifique com seu contador".

---

## 5. Frente 3 — Agente de inteligência financeira

### Objetivo

Transformar os dados do sistema em respostas e insights úteis para a tomada de decisão, sem o gestor precisar navegar por múltiplas telas.

### Modo reativo — chat financeiro

O gestor pergunta em linguagem natural e o agente responde com dados reais do workspace:

- "Qual minha margem líquida em setembro?" → DRE do período com comparativo
- "Quando meu caixa vai apertar?" → previsão de caixa com a data e o valor do saldo mínimo
- "Quem são os fornecedores que mais cresceram este trimestre?" → ranking por categoria/favorecido

### Modo proativo — insights semanais no dashboard

Uma tarefa Celery semanal (`generate_weekly_insights`) roda o agente em background e salva um resumo curto que aparece como card no dashboard. Exemplos de insights:

- Categoria que cresceu acima da média
- Fatura grande a vencer nos próximos 7 dias
- Meta de orçamento prestes a estourar (> 80%)
- Comparativo mês atual vs. mês anterior

### Arquitetura

Aproveita o módulo de agentes existente:

- **Novas ferramentas MCP de leitura financeira:**
  - `get_dre` — DRE por período (competência ou caixa)
  - `get_cash_flow_detail` — entradas/saídas por semana com saldo projetado
  - `get_budget_status` — orçamentos por categoria com % de uso
  - `get_top_categories` — ranking de despesas/receitas por período
  - `get_overdue_invoices` — faturas vencidas e a vencer por faixa de dias
- **Perfil de agente `cfo_assistant`** com acesso a essas ferramentas + RAG no manual (para responder dúvidas de uso junto com dados financeiros)
- **Tarefa Celery** `generate_weekly_insights` — roda o agente em background, salva resultado em nova tabela `workspace_insights`, exposta via `GET /api/insights/latest`
- **Somente leitura:** este agente nunca propõe escritas. Confirmação de lançamento continua sendo fluxo separado

### Limite declarado ao usuário

> *"Posso analisar os dados que estão no SyncroFin. Para previsões de longo prazo ou consultoria tributária, fale com seu contador."*

---

## 6. Frente 4 — Gaps críticos de funcionalidade para PME

### Prioridade 1 — Contas a pagar e a receber (AP/AR) unificadas

**Gap:** sem visão consolidada de títulos, vencimentos e aging, o gestor precisa de outra ferramenta para controlar o fluxo de caixa operacional.

**Entregáveis:**

- Tela **Títulos** com abas A Receber / A Pagar, filtros por período, favorecido, status e conta
- Aging em faixas: vencido 1–30 / 31–60 / 61–90 / +90 dias
- Baixa parcial e total via conciliação com extrato bancário (aproveita motor de conciliação existente)
- Agenda de vencimentos integrada à previsão de caixa existente (`health_service`)

**Base existente:** modelo `Invoice` com `direction receivable/payable`, motor de conciliação, `RecurringTransaction`, `health_service`. Esforço concentrado em UI + serviço de consulta consolidada.

---

### Prioridade 2 — DRE e fluxo de caixa gerencial

**Gap:** o `report_service` tem receitas × despesas mas sem competência × caixa, sem comparativo orçado × realizado, e sem exportação nos formatos que o gestor e o contador usam.

**Entregáveis:**

- **DRE mensal** (competência): receitas brutas, deduções, custos, despesas operacionais, resultado líquido
- **DFC direto** (caixa): entradas e saídas reais por período com saldo inicial e final
- **Comparativo:** mês atual vs. mês anterior vs. orçado por categoria
- **Exportação PDF e XLSX** com logo da empresa

**Base existente:** `report_service.py`, `dashboard_service.py`, `effective_date` para regime de caixa, `Budget` por categoria. Pacote para o contador já entrega CSV; os relatórios gerenciais são a camada acima disso.

---

### Prioridade 3 — Cobrança por PIX e boleto

**Gap:** o ciclo de cobrança fica fora do sistema. O cliente emite a fatura no SyncroFin mas precisa acessar o banco separadamente para gerar o boleto ou o QR Code PIX.

**Entregáveis (via provedor terceiro — Asaas ou Inter como primeira opção):**

- Botão **Gerar cobrança** na fatura: cria boleto ou QR Code PIX no provedor com os dados do título
- **Webhook de liquidação:** pagamento confirmado no provedor baixa a fatura automaticamente via conciliação
- PDF da cobrança anexado à fatura para envio ao cliente

**Decisão arquitetural:** provedor terceiro (conforme D-4 em `ENTERPRISE.md`). Abstração `BillingProvider` análoga ao `BankProvider` existente, permitindo trocar ou adicionar provedores sem mexer na lógica de negócio.

---

## 7. Ordem de implementação sugerida

```
Semana 1–3   Infraestrutura cloud (provisionamento + billing básico)
Semana 2–4   Onboarding por IA (ferramentas MCP de setup + UI tela cheia)
Semana 3–7   AP/AR unificado (modelo + serviço + tela)
Semana 5–8   DRE e DFC (serviço de relatórios + exportação PDF/XLSX)
Semana 6–9   Agente financeiro (ferramentas MCP de leitura + insights semanais)
Semana 8–11  PIX/boleto (abstração BillingProvider + integração Asaas)
Semana 10–12 Piloto com 3–5 clientes reais pagando
```

As frentes de infraestrutura e onboarding podem rodar em paralelo com AP/AR desde a semana 2 com dois desenvolvedores.

---

## 8. Riscos e mitigações

| Risco | Mitigação |
|---|---|
| Custo operacional de VPS por cliente pode tornar planos básicos inviáveis | Definir custo mínimo de plano baseado no custo real do VPS + margem; tier compartilhado como opção futura |
| LLM externo para IA processa dados financeiros sensíveis | Política de dados por workspace (item D6 do `ENTERPRISE.md`); suporte a Ollama local por padrão para quem não quer dados saindo |
| Provedor de boleto/PIX muda API ou encerra serviço | Abstração `BillingProvider` permite trocar sem reescrever lógica de negócio |
| Escopo de AP/AR crescer para ERP | Fixar D-1a: o sistema não faz escrituração; títulos são entradas/saídas, não débito/crédito contábil |
| Onboarding por IA configurar algo errado (categorias inadequadas) | Mostrar resumo do que será criado antes de executar; permitir desfazer via "recomeçar configuração" |

---

## 9. Critérios de saída do piloto

- [ ] Provisionamento de instância em < 5 minutos sem intervenção manual
- [ ] Onboarding por IA concluído por cliente sem suporte externo
- [ ] AP/AR com aging e baixa funcionando para cliente com > 50 títulos
- [ ] DRE e DFC exportados e validados pelo contador do cliente piloto
- [ ] Pelo menos 1 cliente pagando via PIX/boleto gerado pelo sistema
- [ ] Agente financeiro respondendo corretamente a 5 perguntas padrão do piloto
- [ ] Nenhum incidente de segurança ou vazamento de dados entre instâncias
