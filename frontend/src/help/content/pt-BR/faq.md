# Perguntas frequentes e solução de problemas

## Acesso

**Esqueci a minha senha.** Na tela de entrada, use **Esqueceu a senha?**. Se o servidor não tem e-mail configurado, peça
a um administrador para **redefinir a senha** ([Administração](help:administracao)). Veja também
[Segurança e conta](help:seguranca-conta).

**Perdi o aplicativo do 2FA.** Não existem códigos de recuperação. Entre por uma **chave de acesso**, se tiver uma, ou
peça a um administrador para redefinir o seu acesso.

**A chave de acesso (passkey) não funciona.** Elas exigem **HTTPS** (veja [Publicar com HTTPS](help:publicar-https)) ou `http://localhost`, e **não funcionam por
endereço IP**. O endereço que você abre tem de ser o **domínio configurado** no servidor (`WEBAUTHN_RP_ID`). Se o
navegador ainda recusar, abra o sistema pelo domínio correto.

**Não consigo criar uma conta.** O administrador pode ter **desligado o registro**: peça a ele para criar o usuário
([Administração](help:administracao)).

**Não recebi o e-mail de redefinição ou de convite.** Confira o **spam**. O e-mail só existe se o servidor tem SMTP
configurado. A tela de **Redefinir senha** responde igual exista ou não a conta (de propósito), então a ausência de
e-mail não indica erro de digitação. Ao convidar alguém, o sistema informa se o e-mail foi enviado; se não foi, a pessoa
**foi adicionada** mesmo assim e você pode definir uma senha por conta própria ([Workspace](help:workspace)).

## Não aparece o que eu esperava

**Não aparece “Instalar aplicativo” no celular.** O endereço precisa ser **HTTPS** (com cadeado): `http://` e número de IP
não permitem instalar. Veja [Usar no celular](help:app-celular) e, se você administra o servidor,
[Publicar com HTTPS](help:publicar-https).

**Não vejo o módulo Cobranças.** Ele só existe em workspaces do tipo **Negócios**, e o tipo **não pode ser mudado**
depois de criado. Crie um novo workspace de negócios ([Workspace](help:workspace)).

**Não vejo os Agentes de IA.** São opcionais e dependem de o administrador ligar `AGENTS_ENABLED`
([Agentes de IA](help:agentes)). O chat lateral também exige permissão de **edição**.

**Não vejo a opção de Administração.** Só quem tem o papel **Admin** enxerga.

**Não consigo editar nada.** Seu papel no workspace pode ser **Leitor** (somente leitura). Peça a um dono para mudar
para **Editor** ([Workspace](help:workspace)).

**Sumiu uma transação da lista.** Confira os **filtros** ativos (conta, período, categoria, **coleção**). A coleção
selecionada no topo mostra só as **contas** que pertencem a ela ([Navegação](help:navegacao)). Transações **ignoradas** também
ficam fora dos totais.

**O botão de ajuda `?` não aparece.** Ele não é mostrado no link público de uma cobrança nem dentro do próprio
manual. Nas demais telas fica no canto inferior direito.

## Números que não batem

**O total do painel é diferente do que o banco mostra.** Saldos e totais seguem regras do SyncroFin: transferências entre
as suas contas **não são receita nem despesa**, e o painel usa o **regime** definido pelo administrador (**caixa** ou
**competência**, que muda o dia em que as compras no cartão contam). Veja [Painel](help:painel) e
[Administração](help:administracao).

**Uma despesa dividida aparece com valor menor.** Em despesas de [Grupos](help:grupos), só a **sua parte** conta.

**A previsão de caixa parece otimista.** Ela parte do **saldo líquido** das contas e considera só as
[recorrentes](help:recorrentes) cadastradas e as cobranças em aberto: **não estima gastos do dia a dia** nem faturas de
cartão ([Saúde financeira](help:saude-financeira)).

**Valores em outra moeda.** O sistema consolida na **moeda do workspace**. Nos resumos, só entram valores que puderam ser
convertidos para essa moeda.

## Importação e bancos

**A importação criou transações duplicadas.** Confira a **revisão** antes de confirmar e use o
**Histórico de importações** para ver o que entrou ([Importar](help:importar)).

**A conexão com o banco parou.** O sistema avisa pelo sino (**Falha de sincronização bancária**). Reconecte pela tela
de [Contas](help:contas).

## Segurança e dados

**Meus dados vão para fora?** Não, a menos que você use agentes com um provedor externo (OpenAI, Anthropic): nesse caso
os trechos consultados são enviados a ele. Com um modelo **local** (Ollama), nada sai da sua máquina.

**Como faço backup?** **Menu da conta → Backup** ([Segurança e conta](help:seguranca-conta)).

**Como entrego os dados ao contador?** **Menu da conta → Exportar para o contador** ([contador](help:contador)).

## Glossário

| Termo | Significado |
|-------|-------------|
| **Workspace** | Espaço financeiro independente, com suas contas, categorias e membros. |
| **Conta** | Onde o dinheiro está: corrente, poupança, cartão de crédito, investimento ou carteira. |
| **Transação** | Um movimento: receita, despesa ou transferência. |
| **Categoria** | Classificação de uma transação (ex.: Mercado, Salário). |
| **Coleção** | Grupo de contas com um nome, usado como filtro de visualização (ex.: *Empresa*, *Reserva*). |
| **Regra** | Ação automática: se a descrição bate, categoriza. |
| **Favorecido / Pessoa** | Quem paga ou recebe: fornecedor, cliente, familiar. |
| **Orçamento** | Limite mensal de gasto por categoria. |
| **Meta** | Objetivo de poupança com valor e prazo. |
| **Recorrente** | Conta fixa que se repete (aluguel, assinatura, salário). |
| **Cobrança** | Fatura a receber ou a pagar, em workspaces de negócios. |
| **Conciliação** | Casar automaticamente um pagamento real com o que se esperava. |
| **Caixa** | Regime em que o valor conta no dia em que o dinheiro se move. |
| **Competência** | Regime em que o valor conta no período a que se refere. |
| **Reserva de emergência** | Dinheiro líquido guardado, medido em meses de despesas. |
| **2FA** | Segundo passo de login, com código de um aplicativo. |
| **Passkey** | Chave de acesso do dispositivo (biometria ou chave física) para entrar sem senha. |
| **MCP** | Protocolo que permite a um agente de IA consultar seus dados. |

## Ainda com dúvida?

Volte ao [Guia de introdução](help:introducao) ou ao [índice do manual](/help). O código-fonte e o registro de
problemas estão em <https://github.com/gustavoflandal/SyncroFin>.
