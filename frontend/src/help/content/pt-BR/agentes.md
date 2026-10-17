# Agentes de IA

**Agentes** são assistentes que **conversam sobre os seus dados** do SyncroFin: *"qual minha maior categoria de gasto
este mês?"*, *"mostre meus gastos por categoria num gráfico de pizza"*. Cada agente tem o seu **prompt**, o seu
**modelo** e, se você quiser, a sua **base de conhecimento**.

> **Recurso opcional.** Só aparece se o administrador do servidor **ligou os agentes** (`AGENTS_ENABLED`). Sem isso, não
> há menu, atalho nem telas de agentes. Veja `docs/CONFIGURATION.md`.

## Antes de começar: conexão com um modelo

Um agente precisa de uma **conexão LLM**: o provedor do modelo de linguagem. Abra **Menu da conta → Agentes →
Conexões** (**Gerenciar conexões**) e **Adicionar conexão**:

| Campo | Para quê |
|-------|----------|
| **Nome** | Como você reconhece a conexão. |
| **Tipo de provedor** | **OpenAI**, **Anthropic**, **Ollama** (modelo local) ou um endpoint **compatível com OpenAI**. |
| **URL do endpoint** | Obrigatória nos endpoints **compatíveis** (cole só `host:porta`: o `/v1` é acrescentado). Para um Ollama na sua máquina, use `http://host.docker.internal:11434` (Mac/Windows). OpenAI e Anthropic usam o endereço do provedor. |
| **Chave de API** | Guardada **criptografada**; a API **nunca a devolve**. Em branco para provedores locais. |
| **Modelo padrão** | Usado pelos agentes que não escolherem outro. |
| **Usar como padrão para novos agentes** | Marca a conexão principal. |

Use **Testar** para conferir que a conexão responde.

> Ao usar OpenAI ou Anthropic, os **trechos de dados que o agente consulta são enviados a esse provedor**. Para manter
> tudo na sua máquina, use **Ollama** ou outro modelo local.

## Criar um agente

**Agentes → Novo agente**:

- **Nome** e **Descrição**;
- **Prompt do sistema**: as instruções fixas ("Você é um assistente financeiro. Cite sempre as fontes…");
- **Conexão** e **Modelo** (em branco, usa o padrão da conexão);
- **Temperatura**: baixa = respostas mais previsíveis; alta = mais criativas;
- **Injetar contexto da conta automaticamente**: acrescenta ao início da conversa um resumo com seu nome, moeda, data de
  hoje e lista de contas;
- **Agente padrão**: o usado pelo chat lateral (só um por vez).

## Conversar

Abra o agente e use a aba **Conversa**. Cada conversa fica no histórico do lado esquerdo: dá para **renomear** e
**excluir** (excluir apaga as mensagens).

O **chat lateral** abre em qualquer tela com **Ctrl+J** (⌘J no Mac), ou pelo botão do menu. Escolha o agente e
converse sem sair do que estava fazendo. Só está disponível para quem **pode editar** dados.

### Gráficos e propostas

Os agentes podem responder com **gráficos** e também **propor ações**: recategorizar transações, criar categorias,
orçamentos, regras, transações, recorrentes e metas. Uma proposta aparece como um cartão **PROPOSTA** e **nada muda até
você clicar em Aplicar**. Confira o resumo antes. Depois de aplicada, o cartão passa a *aplicada*.

## Conhecimento (RAG)

Na aba **Conhecimento**, **Enviar** documentos **PDF, MD ou TXT** (regulamentos, contratos, políticas internas). Eles
são processados em segundo plano (*pronto* ou *falhou*) e o agente passa a consultá-los.

- **Fixar** um documento faz com que ele **entre sempre no contexto**.
- Excluir o agente **apaga também** o conhecimento enviado.

## Ferramentas

Na aba **Ferramentas**, escolha **quais ferramentas** o agente pode chamar (consultar contas, transações, orçamentos…),
descobertas a partir do servidor **MCP**. As que **alteram dados** ficam marcadas como *proposta*: sempre exigem a sua
confirmação. Se a lista vier vazia, o servidor MCP não está rodando (com Docker, suba com o perfil `agents`).

## Acesso MCP externo

Em **Conexões**, o painel **Acesso MCP externo** conecta um agente de fora (**Claude Desktop/Code**, **Cursor**,
**OpenAI**, n8n ou outro cliente MCP) aos **seus dados**. Clique em **Gerar token**, **copie na hora** (o token **não é
guardado e não pode ser mostrado de novo**) e use os exemplos de configuração exibidos. Tokens expiram após um período
e, para invalidar todos de uma vez, o administrador troca o segredo do MCP.

> Trate o token como uma **senha**: quem o tiver lê os seus dados financeiros.
