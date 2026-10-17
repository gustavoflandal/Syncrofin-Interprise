# Administração

Área para **administradores da instalação**: quem cuida do servidor e das contas de usuário. Aparece no **menu da
conta → Administração** e só para quem tem o papel de **Admin**.

> Não confunda com o papel de **dono** de um workspace ([Workspace](help:workspace)): o administrador governa a
> instalação inteira; o dono governa um espaço financeiro.

## Usuários

**Gerenciamento de Usuários** lista todas as contas, com busca por e-mail.

| Ação | O que faz |
|------|-----------|
| **Adicionar usuário** | Cria uma conta com e-mail, senha e, se quiser, **privilégios de administrador**. |
| **Editar usuário** | Muda o **status** (Ativo/Inativo) e a **função** (Admin/Usuário). |
| **Redefinir senha** | Define uma nova senha. Em branco, mantém a atual. Útil quando o servidor **não tem e-mail** configurado. Encerra as sessões da pessoa. |
| **Redefinir 2FA** | Para quem **perdeu o celular**: remove o aplicativo autenticador e encerra as sessões. A pessoa entra só com a senha e configura outro. Pede uma confirmação. |
| **Desbloquear conta** | Aparece (com a marca **Bloqueada** na lista) quando a conta foi pausada por senhas erradas repetidas. Encerra a pausa na hora; ver [Segurança e conta](help:seguranca-conta). Definir uma nova senha para a pessoa também desbloqueia. |
| **Excluir** | Remove **permanentemente** o usuário **e todos os seus dados**. Não dá para desfazer. |

Um usuário **Inativo** não consegue entrar (e as sessões dele são encerradas na hora), mas seus dados ficam guardados. Você
aparece na lista marcado como **Você**. O escudo verde indica quem já tem **aplicativo autenticador**.

## Registro de novos usuários

**Permitir registro de usuários**: quando **desativado**, só administradores criam contas novas. Deixe desligado em
instalações fechadas (uma empresa, uma família).

## Verificação em duas etapas (2FA) obrigatória

Por padrão, cada pessoa decide se ativa o 2FA ([Segurança e conta](help:seguranca-conta)). Em **Verificação em duas etapas
(2FA)** você pode **exigir** o segundo fator de quem entra com a senha:

- **Quem precisa:** *todas as pessoas* ou *somente administradores*.
- **Prazo até valer (dias):** ao ligar a exigência, as pessoas têm esse prazo. Até lá, veem só um **aviso** com a data; depois
  dele, quem ainda não configurou vê **uma tela que só permite configurar** o 2FA (ou sair). `0` vale imediatamente.
- O quadro mostra **quantas contas ativas ainda não têm aplicativo autenticador**.

O que conta como segundo fator: um código do **aplicativo autenticador**, uma **chave de acesso (passkey)**, ou o **login
único da empresa (OIDC)**, que tem a verificação do próprio provedor. Quem entra com a senha e **termina de configurar** o
aplicativo (digita o primeiro código) ou registra uma passkey já segue em frente na mesma sessão.

> **Antes de ligar, configure o seu próprio 2FA.** O sistema recusa ligar a exigência se a sua sessão não tiver segundo
> fator, para você não ficar trancado para fora do painel que desliga.

**Se alguém ficar sem acesso** (perdeu o celular): abra o usuário e use **Redefinir 2FA**. Se o **único** administrador ficar
trancado, quem cuida do servidor desliga a regra direto no banco
(`UPDATE app_settings SET value='false' WHERE key='mfa_required';`) ou remove `REQUIRE_MFA` do `.env`, e reinicia.

**Para exigir já, na configuração do servidor:** `REQUIRE_MFA=true` no `.env`. Vale **imediatamente**, para todos, e **o painel
não desfaz**. `MFA_GRACE_DAYS` muda o prazo padrão (7 dias).

## Registros de acesso e prazo de guarda

**Registros de acesso** (em *Administração*) mostra quem entrou na instalação, quem tentou e não conseguiu, e de onde: logins,
falhas de senha ou de código de 2FA, contas bloqueadas e desbloqueadas, sessões encerradas e o uso de tokens de API. Dá para filtrar
por período, pessoa, IP e tipo de evento, e **exportar em CSV**. Ninguém consegue editar ou apagar esses registros.

O cartão **Prazo de guarda dos registros de acesso** define por quantos dias eles ficam guardados: de **183 dias** (o mínimo legal de
6 meses) a 3650. Passado o prazo, o registro é **anonimizado**: somem a pessoa, o IP e o navegador, e só ficam a data e o tipo do
evento. Reduzir o prazo anonimiza os registros mais antigos na próxima execução da tarefa diária, e isso não pode ser desfeito.

## Solicitações de titulares (LGPD)

**Administração → Solicitações de titulares** mostra a fila de pedidos de acesso, portabilidade,
correção e eliminação abertos pelos usuários, conforme o art. 18 da LGPD.

| Coluna | O que mostra |
|--------|-------------|
| **Quem pediu** | Nome e e-mail do usuário que abriu a solicitação |
| **Tipo** | Acesso, Portabilidade, Correção ou Eliminação |
| **Status** | Pendente, Resolvida ou Rejeitada |
| **Prazo** | Data-limite de atendimento (15 dias após a abertura); aparece em destaque quando vencido |

Solicitações de **acesso, portabilidade** e **correção autoatendida** são resolvidas automaticamente
no momento do pedido — elas aparecem aqui só como registro, com status já "Resolvida".

Solicitações de **correção manual** chegam com status **Pendente** e precisam de ação:

1. Leia o detalhe exibido abaixo do tipo na coluna **Ação** para entender o que a pessoa quer corrigir.
2. Corrija o dado no sistema (via Usuários ou no workspace afetado, conforme o caso).
3. Volte à fila, preencha a **nota de resolução** (opcional, mas recomendada) e clique em
   **Resolver** ou **Rejeitar** (se o pedido não for aplicável ou já estiver resolvido de
   outra forma).

Solicitações de **eliminação** são executadas automaticamente pelo próprio usuário — o sistema
cuida do cascade. Elas aparecem aqui como "Resolvida" para fins de registro de conformidade.

O cartão **Solicitações de titulares** no painel de administração mostra o número de pedidos
pendentes e um link direto para a fila.

## Contabilidade: caixa ou competência

Define **como as compras no cartão de crédito entram no painel, nos relatórios e nos orçamentos**, para todos:

- **Regime de caixa** (padrão): a compra conta **no dia em que aconteceu**.
- **Regime de competência**: a compra conta **na data de vencimento da fatura**, o que reflete o fluxo de caixa real.

Mude com consciência: os números históricos passam a ser contados de outro jeito.

## Categorias da integração

**Usar categorias da integração**: com ela **desligada**, as transações sincronizadas com o banco chegam **sem
categoria** e só as suas [Regras](help:regras) categorizam.

## Formato de números e de datas

Como valores e datas são **exibidos para todos**:

- **Número:** *Automático* (segue a convenção de cada moeda), `1,000.00`, `1.000,00` ou `1 000,00`;
- **Data:** *Automático*, **Dia/Mês/Ano**, **Mês/Dia/Ano** ou **Ano/Mês/Dia**. Os nomes dos meses seguem o idioma de
  cada usuário.

## Cores do tema

Em **Personalização**, escolha a **cor do tema** dos modos **claro** e **escuro**. Vale para toda a instalação.

## Atualizações do servidor

Quando há uma **nova versão**, aparece um aviso no menu lateral, com o **comando de atualização** para copiar e um
link para as **notas da versão**. Leia as notas antes de atualizar, para ver se há mudanças incompatíveis. Você pode
ligar ou desligar a **verificação automática de atualizações**, ou usar **Verificar atualizações** no menu.

O SyncroFin **não se atualiza sozinho**: quem executa o comando é você (veja `docs/DEPLOYMENT.md`).

## Acesso pela internet e pelo celular

Para usar o sistema fora de casa, instalar o aplicativo no celular e usar chaves de acesso, o endereço precisa de
**HTTPS**. O passo a passo, com certificado automático, está em [Publicar com HTTPS](help:publicar-https). Depois, as
pessoas instalam o aplicativo seguindo [Usar no celular](help:app-celular).

## Fechamento de períodos e aprovações

Controles de [Períodos](help:periods), [Aprovações](help:approvals) e [Webhooks](help:webhooks) ficam em subseções de
**Administração**. Períodos fechados bloqueiam lançamentos; aprovações por alçada mantêm transações
em fila até liberação por um aprovador autorizado; webhooks notificam sistemas externos em tempo real.

## O que não fica aqui

E-mail (SMTP), webhook de alertas, chaves de segurança, agentes de IA e o domínio das chaves de acesso são
configurados por **variáveis de ambiente** do servidor, não por esta tela. Veja `docs/CONFIGURATION.md`.
