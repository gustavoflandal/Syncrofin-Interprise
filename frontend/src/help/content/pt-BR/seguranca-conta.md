# Segurança e conta

Tudo aqui fica no **menu da conta**: o círculo com a sua inicial, no rodapé do menu lateral (ou no topo, no celular).

## Alterar a senha

**Menu da conta → Alterar senha.** Informe a senha atual, a nova (mínimo de caracteres exibido na tela) e a confirmação.
A opção só existe quando o acesso por senha (local) está ligado na instalação.

### O que o sistema pede de uma senha

O servidor confere toda senha nova (cadastro, redefinição, troca e as definidas por um administrador ou no convite):

- **Tamanho mínimo**: 10 caracteres por padrão (o administrador da instalação pode aumentar). O comprimento é o que mais
  protege.
- **Não pode ser uma senha “de todo mundo”**: `123456`, `senha123`, `qwerty`, nomes de time, `Brasil2026`… O sistema também
  reconhece essas senhas com número ou símbolo no fim (`Senha123!` conta como `senha`).
- **Não pode conter o seu e-mail**.
- **Não pode ser simples demais**: um caractere repetido (`aaaaaaaaaa`) ou uma sequência óbvia (`1234567890`, `abcdefghij`).

Não há regra de “uma maiúscula, um número e um símbolo”, de propósito: ela leva a senhas como `Senha@123`. Prefira **uma
frase**: quatro ou cinco palavras sem relação (`cavalo grampo bateria nuvem`) são fortes e fáceis de lembrar. Se a senha
for recusada, a mensagem diz o motivo.

## Esqueci a senha

Na tela de entrada, clique em **Esqueceu a senha?**, informe o e-mail e siga o link recebido para **escolher uma nova
senha**.

- A resposta é **sempre a mesma**, exista ou não uma conta com esse e-mail: assim ninguém descobre quem usa o sistema.
- O link é de **uso único** e expira. Se estiver inválido, peça outro.
- Depende de o **servidor ter e-mail (SMTP) configurado**. Sem ele, peça a um administrador para
  **redefinir a senha** em [Administração](help:administracao).

## Autenticação em dois fatores (2FA)

**Menu da conta → Autenticação 2FA.**

1. Clique em **Ativar 2FA** e leia o **QR Code** com um aplicativo autenticador (Google Authenticator, Authy, 1Password…).
2. Digite o **código de 6 dígitos** para confirmar.

Depois disso, todo login pede o código. Para desligar, use **Desativar 2FA** informando a **senha** e um código.

> **Atenção:** o sistema **não tem códigos de recuperação**. Se você perder o aplicativo autenticador e não tiver outro
> meio de entrada (como uma chave de acesso), peça a um administrador para **redefinir o seu 2FA** (
> [Administração](help:administracao)): você volta a entrar só com a senha e configura outro.

### Quando o administrador exige o 2FA

O administrador pode tornar o segundo fator **obrigatório** ([Administração](help:administracao)):

- **Durante o prazo de carência**, aparece uma faixa amarela no topo com a **data** em que passa a valer e o botão
  **Configurar agora**.
- **Depois do prazo**, quem entra só com a senha vê a tela **Configure a verificação em duas etapas**, em vez do sistema. Ela
  oferece **Configurar aplicativo autenticador** (mesmo passo a passo acima) ou **Usar uma chave de acesso (passkey)**. Ao
  terminar, você **continua de onde parou**, sem entrar de novo.
- Quem entra por **passkey** ou pelo **login único da empresa** já tem o segundo fator e não vê a tela.

## Chaves de acesso (passkeys)

**Menu da conta → Chaves de acesso.** Permitem entrar **sem digitar a senha** (Touch ID, Windows Hello, YubiKey…) e
também servem como **segundo fator**.

- **Adicionar chave de acesso**: dê um nome (ex.: *YubiKey*, *Touch ID do MacBook*) e siga a solicitação do navegador.
- A lista mostra quando cada chave foi **criada** e o **último uso**. Você pode **excluir** as que não usa mais.
- Cada dispositivo aceita **uma** chave por conta.

**Requisitos:** as chaves de acesso exigem **conexão segura**: abra o SyncroFin por **HTTPS** ou em
`http://localhost`. Elas **não funcionam em endereço IP** e precisam do domínio configurado no servidor
(`WEBAUTHN_RP_ID`). Veja [Perguntas frequentes](help:faq) se o navegador recusar.

## Tentativas erradas e bloqueio da conta

Para atrapalhar quem tenta **adivinhar** uma senha, a conta é **pausada** depois de **5 senhas (ou códigos de 2FA) errados
seguidos**:

- A pausa dura **15 minutos** e **dobra** a cada nova pausa (15, 30, 60 min), nunca passando de **1 hora**. Uma entrada
  correta zera tudo.
- Durante a pausa o sistema responde **exatamente como se a senha estivesse errada**, mesmo que você digite a certa. Ele não
  diz se a conta existe nem se está pausada, para não ajudar quem está tentando.
- Você recebe um **e-mail** avisando (se o servidor tem e-mail configurado). **Redefinir a senha** pelo link do e-mail
  encerra a pausa na hora.
- Um **administrador** também pode encerrar a pausa: em [Administração](help:administracao), a pessoa aparece com a marca
  **Bloqueada** e o botão **Desbloquear conta**. Se nenhum administrador conseguir entrar, quem opera o servidor usa
  `python -m app.cli unlock-user <e-mail>`.
- Erros de senha antigos (mais de 24 horas) deixam de contar.

Cada tentativa errada, bloqueio e desbloqueio fica na [Auditoria](help:auditoria) (com o IP), mas o **e-mail digitado errado
não é guardado**: muita gente digita a senha no campo do e-mail.

## Aviso de novo dispositivo

Quando a sua conta é acessada por um **navegador ou sistema que ela ainda não usou** (por exemplo, o primeiro acesso pelo
*Firefox em Linux*), você recebe um **e-mail** com o dispositivo, o endereço e a hora. Se foi você, não há nada a fazer. Se
não foi, **troque a senha** e encerre a sessão em *Sessões e dispositivos*. O primeiro acesso de uma conta nova não gera
aviso.

## Sessões e dispositivos

**Menu da conta → Sessões e dispositivos** mostra onde a sua conta está aberta: navegador e sistema (por exemplo
*Firefox em Windows*), o endereço IP e a **última atividade**. O dispositivo que você está usando aparece marcado como
**Este dispositivo**.

- **Encerrar** derruba aquele dispositivo **na hora**: a próxima ação dele já pede o login de novo.
- **Encerrar todas as outras sessões** deixa só o dispositivo atual conectado. Use se perdeu um celular ou entrou em um
  computador que não é seu.
- **Trocar a senha** encerra sozinha as sessões dos outros dispositivos. Uma redefinição por e-mail, ou um administrador
  definir uma senha nova ou desativar a conta, encerra **todas**.
- Uma sessão termina sozinha após **7 dias sem uso** e, de qualquer forma, **30 dias depois do login**
  (o administrador pode mudar esses prazos). Depois disso, basta entrar de novo.

Se aparecer um dispositivo que você não reconhece, encerre-o e **troque a senha**.

Por segurança, o navegador guarda a sua sessão em um *cookie* que o próprio site **não consegue ler**, e o acesso
propriamente dito dura apenas alguns minutos, renovado sozinho enquanto você usa o sistema.

## Últimos acessos

Na janela **Sessões e dispositivos**, abaixo da lista de dispositivos, a seção **Últimos acessos** mostra os 20 acessos mais recentes
à sua conta: quando entrou, quando alguém errou a senha ou o código de 2FA, quando uma sessão foi encerrada, e de qual endereço IP.
Se aparecer uma tentativa que você não reconhece, troque a senha e encerre as outras sessões. Você só vê os acessos da sua própria
conta, e eles são guardados pelo prazo que o administrador definiu, depois anonimizados.

## Backup dos seus dados

**Menu da conta → Backup** baixa um `.zip` com **todas as contas, transações e regras** do workspace atual, em JSON.

- Defina uma **senha (opcional)** para **criptografar com AES-256**. O arquivo abre em qualquer compactador.
- **O SyncroFin não guarda essa senha.** Se a perder, o backup criptografado não pode ser aberto.

Para entregar dados ao contador, use [Exportar para o contador](help:contador): é outro pacote, em CSV.

## Idioma

**Menu da conta → Idioma**: **English**, **Português (BR)** ou **Español**. A escolha vale para você. O idioma
padrão do workspace ([Workspace](help:workspace)) é independente. Os textos de ajuda existem em português: nos outros
idiomas o manual aparece em português, com um aviso.

## Tema e privacidade

- **Tema:** o botão de **sol/lua** no topo alterna entre o modo **claro** e o **escuro**. A **cor do tema** é definida
  pelo administrador ([Administração](help:administracao)).
- **Ocultar valores:** o ícone de **olho** no topo esconde todos os valores na tela (útil em reuniões e em público). É só
  visual e vale até você mostrar de novo.
- **Ctrl+K** abre a busca rápida (ver [Navegação](help:navegacao)).

## Sair

**Menu da conta → Sair** encerra a sessão neste navegador, e o servidor a cancela: copiar o acesso de antes não
adianta.

## Meus dados (LGPD)

**Menu da conta → Meus dados** abre o painel de direitos de titular, previsto no artigo 18 da LGPD.
Qualquer pessoa pode abri-lo a qualquer momento — não precisa de permissão especial.

### Acesso e portabilidade

O botão **Baixar meus dados** gera um arquivo `.zip` com:

- todos os workspaces dos quais você faz parte (contas, lançamentos, orçamentos, regras, categorias…),
- seu perfil (nome, e-mail, preferências),
- a lista de sessões ativas e revogadas,
- os tokens de API que você criou (metadados — escopos, datas — nunca o segredo), e
- o histórico de acesso da sua conta.

O download começa na hora, sem necessidade de aprovação.

### Correção

Clique em **Correção** e responda se já sabe onde corrigir sozinho.

- **Sim:** o sistema mostra os links diretos para editar perfil, lançamentos, contas e categorias.
  Um registro é criado automaticamente, já com status Resolvida, e aparece em "Minhas solicitações".
- **Não:** descreva o que precisa ser corrigido e envie. Um protocolo é gerado e a solicitação
  fica na fila do administrador.

### Eliminar minha conta

**Use com cuidado — a ação não pode ser desfeita.**

1. Clique em **Excluir minha conta** e confirme sua senha.
2. Se você for o único dono de um workspace com outras pessoas, a exclusão é **bloqueada**. Você receberá
   um protocolo de registro e a lista dos workspaces que precisam de resolução antes. Transfira a
   titularidade ou remova os outros membros e abra uma nova solicitação.
3. Caso contrário, sua conta e todos os dados que você possui são excluídos permanentemente.
   Um e-mail de confirmação é enviado antes da exclusão.

### Histórico de solicitações

A seção **Minhas solicitações** lista todos os pedidos que você abriu, com protocolo, tipo, status
e prazo de atendimento (15 dias). Use o protocolo para acompanhar com o administrador se necessário.
