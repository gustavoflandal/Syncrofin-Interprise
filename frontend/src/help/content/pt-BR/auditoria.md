# Auditoria

A auditoria responde a uma pergunta: **quem fez isso, quando e de onde?** Cada vez que alguém (ou uma tarefa
automática) **cria, altera ou exclui** um dado financeiro ou de configuração, o sistema guarda um registro do fato,
com o **valor de antes e o de depois**.

Ela fica em **Workspace → Configurações → Auditoria** e é visível para quem tem a permissão de **ver a auditoria**: por
padrão o **proprietário** e o **gestor** do workspace, e qualquer papel que o proprietário crie com essa permissão, como o
**Auditor** ([Workspace](help:workspace)). Editores e leitores não a veem.

## O que é registrado

- **Dados financeiros:** contas, transações (e divisões), categorias, orçamentos, metas, regras, recorrências,
  cobranças e seus itens, pessoas e empresas, patrimônio, conexões bancárias, anexos.
- **Configuração e acesso:** dados do workspace, **membros e papéis**, usuários, chaves de acesso, configurações do
  sistema e conexões com provedores de IA.
- **Quem:** o usuário que fez a ação. Tarefas automáticas (sincronização bancária, recorrências) aparecem como
  **Sistema**.
- **De onde:** o **endereço IP** e o **navegador** da requisição, e um **código da requisição** que liga vários registros
  feitos no mesmo clique.

Segredos **nunca** são gravados: senha, segredo do 2FA, credenciais de banco e chaves de API aparecem como `***`
(fica registrado que mudaram, não o valor).

Não entram: histórico de conversa dos agentes, notificações, taxas de câmbio e outros dados gerados pelo próprio
sistema. O saldo de uma conta que se atualiza sozinho a cada lançamento também não gera evento por si só; o
lançamento que o causou, sim.

## Consultar

Use os filtros de **período**, **registro** (conta, transação, membro…) e **ação** (criou, alterou, excluiu) e clique
em **Filtrar**. Clique em uma linha para ver os **campos que mudaram** (antes → depois), o IP, o navegador e o
**selo** do evento.

## Exportar

**Exportar CSV** baixa os eventos do filtro atual (até 100 mil linhas) em uma planilha que abre no Excel. Cada linha
leva o selo (hash), o que permite provar depois que o arquivo é fiel ao registro.

## Por que não dá para apagar nem editar

- O sistema **não tem nenhuma tela ou rota** que altere ou apague eventos.
- O **banco de dados** também recusa: um bloqueio interno rejeita qualquer alteração, exclusão ou esvaziamento da
  tabela, **mesmo com a senha do banco**.
- Cada evento é **encadeado** ao anterior por um selo criptográfico (SHA-256), como um livro-razão. Alterar ou
  remover um evento por fora do sistema quebra a cadeia, e a **verificação de integridade** aponta onde.

> **Para o administrador:** o botão **Verificar integridade** (visível só para administradores) sela os eventos
> pendentes e confere a cadeia inteira. Anote o **selo mais recente** que ele informa em um lugar fora do servidor:
> assim, mesmo a remoção dos eventos mais novos (que a cadeia sozinha não denuncia) pode ser descoberta depois.

Os eventos novos entram na cadeia em **até 1 minuto**. Quem consulta ou exporta já os vê selados.

## Perguntas comuns

- **"Alguém mudou o valor de uma transação. Como descubro quem?"** Filtre por **Transação → Alterou**, ache a linha e
  abra: o antes/depois e o usuário estão lá.
- **"Dá para desligar?"** Não. A auditoria é parte do sistema e não tem chave de desligar.
- **"O usuário foi excluído. Os registros dele somem?"** Não. Continuam, com o aviso *Usuário removido*.
