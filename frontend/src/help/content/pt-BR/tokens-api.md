# Tokens de API

Um **token de API** é uma credencial para um **programa**, não para uma pessoa: uma integração com outro sistema, um
*script*, a ferramenta do contador. Em vez de dar a senha de alguém a um programa, você gera um token com **só o que ele
precisa fazer**, por **um tempo determinado**, e pode **cancelá-lo** a qualquer momento.

Fica em **Workspace → Configurações → Tokens de API**, e só aparece para quem tem a permissão de **gerenciar tokens** (por
padrão, o dono; veja [Workspace](help:workspace)).

## Como um token funciona

- **Vale para um workspace só.** Ele só enxerga os dados do workspace em que foi criado, e não consegue trocar para outro.
- **Só faz o que você marcou.** As permissões (as mesmas dos [papéis](help:workspace)) são escolhidas na criação. Um token de
  leitura e exportação não consegue lançar nada.
- **Nunca faz mais do que você faz.** Você só pode dar a um token o que você mesmo pode. E vale sempre o **menor** dos dois:
  se você perder uma permissão, os seus tokens **perdem junto, na hora**. Se você sair do workspace ou for desativado, eles
  **param de funcionar**.
- **Sem poderes de administração.** Um token **não** pode convidar ou remover membros, criar papéis, mudar as configurações do
  workspace nem criar outros tokens.
- **Não mexe na conta de ninguém.** Rotas da conta da pessoa (senha, sessões, 2FA, passkeys) e da administração da instalação
  recusam tokens.
- **Sempre expira:** 30, 90, 180 ou 365 dias, à sua escolha.
- **Aparece na auditoria.** O que um token faz fica registrado como **feito por token**, com o **prefixo** dele e a pessoa por
  trás ([Auditoria](help:auditoria)).

## Criar um token

1. **Novo token**.
2. Dê um **nome** que diga para que ele serve (por exemplo, *integração com o ERP*).
3. Escolha a **validade** e marque as **permissões** de que ele precisa (só aparecem as que você mesmo tem).
4. **Gerar token**. O **segredo aparece uma única vez**: copie e guarde como uma senha. O sistema guarda só uma impressão
   digital dele, então **nem o administrador consegue ver de novo**. Se perder, gere outro.

## Usar um token

Envie o token no cabeçalho de cada requisição à API:

```
Authorization: Bearer sfn_1a2b3c4d_...
```

Por exemplo, para baixar o pacote do contador de um período (o token precisa da permissão de **exportar**):

```
curl -X POST https://seu-servidor/api/export/accountant \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"start": "2026-01-01", "end": "2026-03-31"}' -o contador.zip
```

A documentação de todas as rotas está em `/api/docs` no seu servidor. Um token que tente algo que não pode recebe **403** e a
resposta diz qual permissão faltou.

## Girar e revogar

- **Girar** gera um **novo segredo** com o mesmo nome, permissões e duração, e o **antigo para de funcionar na hora**. Use
  periodicamente, ou quando suspeitar de um vazamento.
- **Revogar** cancela o token para sempre. Ele continua na lista, marcado como *Revogado*.
- A lista mostra o **prefixo** (para reconhecer qual é qual), quantas permissões, quando expira e quando foi usado pela
  última vez. Um token **nunca usado** por muito tempo é candidato a revogar.

## Boas práticas

- **Um token por integração**, com o nome dela: fica claro na auditoria e dá para revogar só o que vazou.
- **Dê o mínimo:** só o que a integração usa, e a menor validade que atenda.
- **Nunca** coloque um token em código versionado, em mensagem ou em planilha. Use o cofre de segredos do sistema que o usa.
- Se a pessoa que criou os tokens **deixa a empresa**, os tokens dela param junto: recrie-os com outra pessoa.
