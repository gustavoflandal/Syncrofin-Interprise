# Notificações

O **sino** (no topo da tela) reúne os avisos do que **precisa da sua atenção**: orçamento estourando, cobrança
vencendo, banco desconectado, caixa ficando negativo. O número no sino é a quantidade de avisos **não lidos**.

## Usando o sino

- Clique no sino para abrir a lista. Ao abrir, o sistema **verifica na hora** se surgiu algo novo.
- Cada aviso mostra o que aconteceu e **há quanto tempo**. Clique nele para ir à tela relacionada; ele é marcado como
  lido.
- **Marcar todas como lidas** limpa o contador.
- **Verificar agora** força uma nova checagem.
- Sem nada pendente, aparece *"Nada precisa da sua atenção."*

Além de quando você abre o sino, o sistema confere **a cada hora** em segundo plano.

## O que gera aviso

| Situação | Quando | Gravidade |
|----------|--------|-----------|
| **Orçamento estourado** | O gasto passou de 100 % do orçamento do mês | Crítica |
| **Orçamento perto do limite** | O gasto chegou a 80 % | Aviso |
| **Cobrança ou conta vencendo** | Vence em até 3 dias | Aviso |
| **Cobrança ou conta vencida** | Passou do vencimento (a receber é crítica; a pagar é aviso) | Crítica / Aviso |
| **Falha de sincronização bancária** | A conexão com o banco falhou ou expirou (só o dono da conexão é avisado) | Aviso |
| **Caixa projetado negativo** | A [previsão](help:saude-financeira) dos próximos 30 dias fica abaixo de zero | Crítica |

## Sem repetição

Cada aviso descreve uma **situação**, e a mesma situação **avisa uma vez só**. Um orçamento que continua estourado
não gera um aviso novo a cada hora. Quando a situação **muda** (novo mês, novo vencimento), você é avisado de novo.

## Quem recebe

**Donos e editores** do workspace. **Leitores** não recebem avisos (eles não agem sobre orçamentos nem bancos). Cada
pessoa tem a **sua própria** lista: marcar como lido o seu aviso não some com o de outra pessoa.

## Fora do sistema: e-mail e webhook

Os avisos também podem chegar por **e-mail** e por **webhook** (para integrar com outro sistema). São canais
**opcionais**, **desligados por padrão**, e configurados pelo **administrador do servidor** (não há tela para isso).
Se estiverem ligados:

- O envio é *best effort* e **nunca se repete**: mesmo que falhe, o aviso continua no sino.
- O webhook é **assinado** (cabeçalho `X-SyncroFin-Signature`) para o receptor conferir a origem.

O detalhe das variáveis está em `docs/CONFIGURATION.md`. O e-mail do servidor também envia os links de
[recuperação de senha](help:seguranca-conta) e de convite de [Workspace](help:workspace).
