# Primeiros passos: acesso e conta

Esta página cobre as telas de **entrada**: primeiro acesso, login, criação de conta e recuperação de senha.

## Primeiro acesso: criar o administrador

Numa instalação nova, ao abrir o endereço do sistema aparece **Bem-vindo ao SyncroFin**. Informe:

1. **Seu nome** (como devemos te chamar), **e-mail** e **senha** (mínimo de 8 caracteres) com **confirmação**.
2. **Idioma**, **Tema** e **Moeda** (a moeda do seu workspace Pessoal).
3. Clique em **Criar Conta Admin**.

Essa tela só funciona **uma vez**, enquanto não existe nenhum usuário. A conta criada é a **administradora** da
instalação ([Administração](help:administracao)).

## Entrar

Na tela **Entrar**, use:

- **E-mail e senha**, ou
- **Continuar com chave de acesso** (passkey): Touch ID, Face ID, Windows Hello ou chave de segurança, sem digitar
  senha. Veja [Segurança da conta](help:seguranca-conta) para cadastrar;
- **Login único (SSO)**, quando o administrador configurou um provedor (Authentik, Pocket ID etc.). Aparece um botão
  com o nome do provedor. Se a instalação for *somente SSO*, os campos de senha não aparecem.

Se você ativou a **autenticação em dois fatores**, depois da senha o sistema pede o **código de 6 dígitos** do
seu aplicativo autenticador (ou uma chave de segurança). Um código inválido é recusado; após várias tentativas
erradas o acesso é temporariamente limitado.

> **Chaves de acesso só funcionam** em `http://localhost` ou em um endereço com **HTTPS e domínio**. Não funcionam
> em endereço por IP (por exemplo `http://192.168.0.10`), por uma regra do próprio navegador.

## Criar conta

O link **Criar conta** aparece se o administrador permitiu o registro. Informe e-mail, senha, confirmação e a
**moeda**. Cada nova conta ganha um workspace Pessoal com categorias e regras padrão.

Se o link não aparece, o registro está desativado: peça a um administrador para criar seu usuário ou para
**convidar você** para um workspace.

## Esqueci a senha

1. Na tela **Entrar**, clique em **Esqueceu a senha?**.
2. Informe seu e-mail e clique em **Enviar link de redefinição**.
3. Abra o e-mail que chega e clique no link. Ele leva a **Escolha uma nova senha**.
4. Digite a nova senha duas vezes e clique em **Salvar senha**.

Detalhes importantes:

- O link vale **1 hora** e funciona **uma única vez**. Depois de usado (ou se você trocar a senha por outro meio),
  ele deixa de valer; peça outro.
- A resposta é a **mesma** para e-mails cadastrados ou não: por segurança, o sistema nunca revela quem tem conta.
  Se nada chegar, confira o spam e o endereço digitado.
- Se aparecer *"Esta instalação não consegue enviar e-mails"*, o servidor não tem e-mail configurado: peça ao
  administrador para redefinir sua senha em **Administração → Usuários**.

## Fui convidado para um workspace

Quando um dono convida você **sem definir uma senha**, chega um e-mail com um link (válido por **7 dias**, uso único).
Ele abre a tela **Bem-vindo ao SyncroFin**, onde você **escolhe sua própria senha**. Depois é só entrar.

Se você já tinha conta, o e-mail apenas avisa que foi adicionado; o workspace aparece no seletor de workspaces.

## Problemas para entrar?

Veja [Perguntas frequentes e solução de problemas](help:faq).
