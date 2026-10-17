# Publicar com HTTPS

Para quem **administra o servidor**. Para usar o SyncroFin no celular, com [chave de acesso](help:seguranca-conta) e com
segurança, o endereço precisa ser **HTTPS** (o cadeado no navegador). Este passo a passo coloca um **proxy com
certificado automático** (Caddy + Let's Encrypt) na frente do sistema. O certificado é emitido e **renovado sozinho**.

> Depois de pronto, quem usa o sistema instala o aplicativo seguindo [Usar no celular](help:app-celular).

## Para que serve

- **Instalar o aplicativo no celular**: o navegador só oferece a instalação em site seguro.
- **Chaves de acesso (passkeys)**: só funcionam em HTTPS (ou `localhost`), e **nunca por número de IP**.
- **Segurança**: sem HTTPS, senhas e dados financeiros viajam sem criptografia pela rede.

## O que você precisa

| Item | Detalhe |
|------|---------|
| **Servidor** | Uma máquina Linux (uma VPS, por exemplo) com **Docker** e **Docker Compose 2.24 ou mais novo** (`docker compose version`). |
| **Domínio** | Um nome como `syncrofin.suaempresa.com`. Serve um subdomínio de um domínio que você já tem. |
| **IP público** | O servidor precisa ser alcançável pela internet. Em casa, sem IP público (CGNAT), veja *Sem IP público* abaixo. |
| **Portas 80 e 443** | Liberadas para a internet. A 80 é usada pelo Let's Encrypt para provar que o domínio é seu. |
| **O SyncroFin instalado** | Os arquivos do projeto no servidor, e o sistema rodando com `docker-compose.prod.yml` (veja `docs/DEPLOYMENT.md`). |

## Passo a passo

### 1. Aponte o domínio para o servidor

No painel de DNS do seu domínio, crie um registro **A** com o nome escolhido (ex.: `syncrofin`) apontando para o
**IP público** do servidor. Se o servidor tem IPv6, crie também um registro **AAAA**.

Confira (pode levar de minutos a algumas horas para propagar):

```
nslookup syncrofin.suaempresa.com
```

O endereço devolvido tem de ser o IP do servidor.

### 2. Libere as portas 80 e 443

- **VPS:** no firewall do provedor (grupo de segurança) e no do sistema (`ufw allow 80,443/tcp`), e a **443/udp** se
  quiser HTTP/3.
- **Em casa:** no roteador, encaminhe as portas **80** e **443** para o computador que roda o SyncroFin.

### 3. Ajuste o arquivo `.env`

No servidor, na pasta do projeto, abra o `.env` (copie de `.env.example` se não existir) e confira:

```
DOMAIN=syncrofin.suaempresa.com
SECRET_KEY=<valor longo e aleatório>
```

- `DOMAIN` é o domínio do passo 1, **sem** `https://`.
- Gere a `SECRET_KEY` com `openssl rand -hex 32`. **Não deixe o valor padrão** e não a perca: trocá-la encerra as
  sessões e torna ilegíveis as chaves de IA salvas.
- Se usa [agentes de IA](help:agentes), defina também `AGENTS_MCP_JWT_SECRET` com outro valor aleatório.

### 4. Suba o sistema com HTTPS

```
docker compose -f docker-compose.prod.yml -f docker-compose.https.yml up -d
```

O segundo arquivo acrescenta o Caddy, **fecha as portas antigas** (o app e a API deixam de ser expostos direto; só o
Caddy responde) e já acerta a URL pública e a contagem de proxies (`TRUSTED_PROXY_HOPS=2`) que o limite de tentativas
de login usa.

> **Dica:** para não repetir os dois arquivos em todo comando, acrescente ao `.env` a linha
> `COMPOSE_FILE=docker-compose.prod.yml:docker-compose.https.yml`. Depois basta `docker compose up -d`.

### 5. Acompanhe o certificado

```
docker compose -f docker-compose.prod.yml -f docker-compose.https.yml logs -f caddy
```

Em cerca de um minuto aparece uma linha com **`certificate obtained successfully`**. Se aparecer erro, veja *Se algo
der errado* abaixo.

### 6. Teste

- Abra `https://syncrofin.suaempresa.com` no navegador: deve aparecer o **cadeado** e a tela do SyncroFin.
- Abra `http://syncrofin.suaempresa.com`: deve **redirecionar** para o HTTPS.

### 7. Crie o administrador logo em seguida

Na primeira visita o sistema pede para **criar o administrador** (veja [Primeiros passos](help:primeiros-passos)).
Como o endereço agora é público, faça isso **imediatamente**: até existir o primeiro usuário, qualquer pessoa que abrir
o endereço poderia criá-lo.

### 8. Se o uso é pessoal ou da empresa, feche o cadastro

Em **Administração**, desligue **Permitir registro de usuários** ([Administração](help:administracao)). Assim só o
administrador cria contas. Ative também o [2FA](help:seguranca-conta) na sua conta.

### 9. Instale no celular

Peça a cada pessoa para seguir [Usar no celular](help:app-celular).

## Se algo der errado

| Sintoma | Causa provável e o que fazer |
|---------|------------------------------|
| O log do Caddy mostra erro ao emitir o certificado | O **DNS** ainda não aponta para o servidor (passo 1) ou as **portas 80/443** estão bloqueadas (passo 2). Corrija e reinicie: `docker compose ... restart caddy`. |
| O navegador diz que o site **não é seguro** | O certificado ainda não foi emitido, ou você abriu por **IP**: use o domínio. |
| O site abre, mas o **login falha** | `DOMAIN` errado ou diferente do endereço que você abre. A URL do sistema (`FRONTEND_URL`) tem de ser exatamente `https://` + o domínio. |
| Muitas pessoas recebem **"muitas tentativas"** | A contagem de proxies não bate com a sua instalação: com este passo a passo o valor certo é `TRUSTED_PROXY_HOPS=2`. Se você acrescentou outro proxy na frente, some 1. |
| O Let's Encrypt recusa por **limite de pedidos** | Foram muitas tentativas falhas seguidas. Espere cerca de uma hora e tente de novo. Não apague o volume `caddy_data`: ele guarda os certificados. |
| Passkey diz que o endereço não é válido | Abra pelo **domínio** em HTTPS, nunca por IP. Veja [Perguntas frequentes](help:faq). |

## Sem IP público (só em casa)

Se a sua operadora usa **CGNAT** (não dá para abrir portas) ou você não quer expor o servidor, use um **túnel** que
entrega HTTPS por fora, como o **Tailscale** (acesso privado só entre seus aparelhos) ou o **Cloudflare Tunnel**. Nesse
caso **não use** o `docker-compose.https.yml`: rode só o `docker-compose.prod.yml`, aponte o túnel para a porta do
frontend (`3000`) e defina `FRONTEND_URL` no `.env` com o endereço `https://` que o túnel entregar.

> Este caminho **não foi testado** com o SyncroFin. Confirme o `TRUSTED_PROXY_HOPS`: ele é o número de proxies entre o
> usuário e o sistema (o nginx do frontend conta 1; o túnel, se acrescentar o IP do cliente, conta mais 1).

## Atualizar e manter

- **Atualizar:** `docker compose ... pull` e depois `docker compose ... up -d`. Faça **backup do banco antes**
  (veja `docs/DEPLOYMENT.md`).
- **Certificado:** nada a fazer. O Caddy renova sozinho, desde que as portas 80/443 continuem abertas e o volume
  `caddy_data` seja preservado.
- **Lista de segurança** completa em `docs/DEPLOYMENT.md`.
