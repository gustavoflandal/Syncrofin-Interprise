# Workspace

Um **workspace** é um espaço financeiro independente: suas próprias contas, categorias, orçamentos, metas, regras e
**membros**. Use um para a vida pessoal e outro para a empresa, por exemplo, sem misturar nada.

## Trocar e criar workspaces

No rodapé do menu lateral, clique no nome do workspace para **trocar** ou criar um **Novo workspace**:

- **Nome**, **ícone** e cor;
- **Tipo**: **Pessoal** ou **Negócios**. Escolha com cuidado: **não dá para mudar depois**. Negócios ganha o módulo
  [Cobranças](help:cobrancas) e o [assistente de configuração da empresa](help:onboarding-empresa). Um tipo errado exige criar outro workspace.

## Configurações do workspace

Abra **Configurações do workspace** (menu da conta). Só **donos** alteram.

### Detalhes

| Campo | Para quê |
|-------|----------|
| **Nome**, **ícone**, **cor** | Identificação. |
| **Moeda padrão** | Moeda em que tudo é consolidado. Trocar a moeda também muda a exibição para o dono que a alterou. |
| **Idioma** | Idioma padrão do workspace. |
| **Jurisdição fiscal** | Define quais **documentos fiscais** o workspace oferece (CPF/CNPJ no Brasil, por exemplo). É independente do idioma: um brasileiro que lê o sistema em inglês continua fiscalmente no Brasil. |

Também aparecem estatísticas: número de **contas**, **transações** e a data de criação.

### Membros e papéis

**Adicionar membro**: informe o **e-mail** e o **papel**.

| Papel | O que pode |
|-------|------------|
| **Dono** | Tudo: membros, configurações e todos os dados. |
| **Editor** | Ler e escrever todos os dados financeiros. |
| **Leitor** | Somente leitura. Pode exportar para o contador. |
| **Gerente** | Administrador externo, com direitos efetivos de dono, sem ser membro da lista. |
| **Papéis seus** | Papéis que o dono cria para o workspace, com exatamente as permissões que quiser (ver abaixo). |

**Todo membro vê os dados do workspace.** O que os papéis controlam é quem pode **alterar**, **exportar**, **ver a auditoria**
e **administrar**.

**Convidar alguém novo:**

- Se o servidor **tem e-mail configurado**, deixe a senha **em branco**: a pessoa recebe um **link de convite** (válido
  por 7 dias) para **escolher a própria senha**. Você não precisa inventar e repassar uma senha.
- Se preferir (ou se o servidor **não** tem e-mail), **defina uma senha** e passe você mesmo.
- Se a pessoa **já tem conta**, ela é apenas adicionada (e avisada por e-mail, se possível).
- Depois do convite, o sistema informa se o e-mail **foi enviado**. Se falhar, o membro **foi adicionado** mesmo assim:
  avise por conta própria.

Você pode **alterar o papel** ou **Remover membro** (a pessoa perde o acesso a todos os dados do workspace).

Em instalações **somente SSO**, novos usuários entram primeiro pelo provedor de identidade.

### Papéis e permissões

Além de Dono, Editor e Leitor, o **dono** cria **papéis próprios** em **Papéis e permissões** (uma seção abaixo da lista de
membros). Cada papel é um conjunto de permissões, e a lista de papéis aparece ao adicionar um membro e ao mudar o papel de
alguém.

**Novo papel:** dê um **nome** (e, se quiser, uma **descrição**), escolha um **modelo** para começar e ajuste as caixas de
marcação. Os modelos são pontos de partida:

| Modelo | Para quem | O que marca |
|--------|-----------|-------------|
| **Contador** | Quem escritura, de fora | Só **exportar** (pacote do contador, backup, CSV). Não altera nada. |
| **Auditor** | Quem confere | **Exportar** e **ver a auditoria**. |
| **Lançador** | Quem digita o dia a dia | Lançar transações e anexos, contas, importar, pessoas e conciliar. Sem configurar nem administrar. |
| **Cobrança** | Quem cobra | Cobranças, pessoas e exportar. |

**As permissões**, em três grupos:

- **Alterar dados** (uma por área): transações e anexos, contas, categorias, regras, orçamentos/metas/recorrências, pessoas e
  empresas, patrimônio, importação, coleções, grupos de despesas, conexões bancárias, cobranças, conciliação e agentes de IA.
- **Exportar e auditar:** exportar dados (backup, pacote do contador, CSV) e ver a auditoria.
- **Administrar:** configurações e arquivamento do workspace, gerenciar membros, gerenciar papéis e gerenciar **tokens de API**
  ([Tokens de API](help:tokens-api)).

Uma mudança no papel **vale na hora** para quem o tem. Um papel **em uso** não pode ser excluído: mude o papel dos membros antes.
Quem não tem a permissão de exportar, por exemplo, não vê o backup funcionar e o sistema avisa que falta a permissão.

> Dono, Editor e Leitor **não mudam**: continuam com o que sempre tiveram. Só o **dono** pode criar papéis, a menos que ele
> dê a outro membro a permissão de gerenciar papéis.

### Conciliação automática

Em workspaces com o módulo Cobranças, defina a **Confiança necessária** (**Muito rigorosa 99%**, **Rigorosa 95%**,
**Equilibrada 90%**, **Permissiva 80%** ou **Desligada**) e use **Aplicar à fila agora** para processar o que está
esperando. Só são automáticos vínculos de **valor exato**, até **7 dias** do vencimento e de **uma** cobrança. Veja
[Conciliação](help:conciliacao).

### Auditoria

Quem tem a permissão de **ver a auditoria** (por padrão, o dono e o gerente; o papel Auditor também) vê **quem alterou o quê**
neste workspace em **Auditoria** (logo abaixo do cabeçalho desta tela). Veja [Auditoria](help:auditoria).

### Webhooks

Em **Webhooks** você configura destinos para notificações automáticas: quando um evento ocorre (nova transação, cobrança
criada, pagamento, etc.), o SyncroFin faz um **HTTP POST** para a URL configurada com o payload em JSON.

**Campos:**

| Campo | Para quê |
|-------|----------|
| **URL** | Endpoint HTTPS que receberá os eventos. |
| **Segredo** | Se informado, cada entrega inclui o cabeçalho `X-SyncroFin-Signature: sha256=<hex>` para você verificar a autenticidade. |
| **Eventos** | Filtre quais eventos devem ser entregues. Deixe todos desmarcados para receber tudo. |
| **Ativo** | Desmarque para pausar as entregas sem excluir o webhook. |

**Eventos disponíveis:** `transaction.created`, `transaction.updated`, `transaction.deleted`, `invoice.created`,
`invoice.paid`, `invoice.void`, `reconciliation.applied`.

O botão **Enviar evento de teste** (ícone de avião) agenda uma entrega de teste imediata; o código de resposta aparece
na linha do webhook após alguns segundos.

As entregas são **fire-and-forget**: uma falha não afeta a operação do SyncroFin. Requer permissão
**Configurações e arquivamento do workspace** (dono por padrão).

### Zona de perigo

**Arquivar workspace**: ele some da lista e do seletor, mas os **dados ficam preservados**.

## Quem vê o quê

Cada membro vê **somente** os workspaces em que foi incluído, e o que pode fazer depende do papel. Os dados de um
workspace **nunca** aparecem em outro.

Para integrar com sistemas ERP externos, veja [Conectores ERP](help:conectores-erp). Para a política de retenção e anonimização de dados pessoais, veja [Retenção de dados](help:retencao-dados).
