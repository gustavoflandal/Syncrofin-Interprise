# Usar no celular

Há duas formas de usar o SyncroFin no celular:

| | **App Android** | **Site instalável (PWA)** |
|---|---|---|
| Para quem | Celulares Android | iPhone, iPad e computador (também funciona no Android) |
| O que é | Um aplicativo simples, só com o que se faz na rua | O sistema completo, aberto como um aplicativo |
| Fotografar o comprovante | **Sim**, e o app **lê valor, data e estabelecimento** para você | Sim, escolhendo a foto no aparelho, sem leitura |
| Instalação | Um arquivo `.apk` (não está na Google Play) | Direto pelo navegador |

Se você quer **lançar um gasto na hora e guardar o comprovante**, use o **app Android**. Para tudo o mais (orçamentos,
relatórios, contas, importação…), use o sistema completo, no navegador ou no site instalado.

> Nas duas formas o endereço do seu SyncroFin precisa ser **HTTPS**. Se você administra o servidor, veja
> [Publicar com HTTPS](help:publicar-https).

---

## App Android

### O que ele faz

O app tem **três telas**, de propósito, e nada além disso:

| Tela | Para quê |
|------|----------|
| **Entrar** | Conectar ao seu servidor com e-mail e senha (e código de dois fatores, se a conta tem). |
| **Lançar** | Registrar uma despesa ou receita, com a **foto do comprovante**. |
| **Lançamentos** | Ver o mês, abrir um lançamento e ver ou **adicionar comprovantes**. |

O app usa o **idioma do celular** (português, inglês ou espanhol).

### Antes de começar

- **Android 7 ou mais novo.** Foi testado no Android 16.
- O **arquivo do app** (`SyncroFin.apk`). Quem administra o seu servidor entrega; veja *Para o administrador*, no fim desta página.
- O **endereço do servidor**, começando com `https://` (por exemplo, `syncrofin.suaempresa.com`), o seu **e-mail** e a sua **senha**.

### Instalar o app

Como o app não está na Google Play, o Android pede uma autorização na primeira vez.

1. Coloque o `SyncroFin.apk` no celular (por cabo, e-mail, mensagem ou nuvem) e **toque no arquivo**.
2. O Android avisa que o aplicativo usado para abrir o arquivo (o gerenciador de arquivos, o navegador…) **não pode instalar apps
   desconhecidos**. Toque em **Configurações** e ligue **Permitir desta fonte**. Depois, volte.
3. Toque em **Instalar**. Se aparecer um aviso do **Google Play Protect** dizendo que o app não é conhecido, escolha
   **Instalar mesmo assim** (o app não passou pela loja, e o aviso é por isso).
4. Ao terminar, toque em **Abrir**. O ícone do SyncroFin fica na lista de aplicativos.

> Os nomes exatos dos menus mudam de marca para marca. O caminho costuma ser *Configurações → Aplicativos → Acesso especial →
> Instalar apps desconhecidos*. Depois de instalar, você pode desligar essa permissão de novo.

### Entrar

![Tela de entrada do app, com o endereço do servidor, o e-mail e a senha](/manual-img/app-celular/login.png)

1. Em **Endereço do servidor**, digite o endereço do seu SyncroFin. Pode digitar sem o `https://`: o app acrescenta.
2. Digite o **E-mail** e a **Senha** e toque em **Entrar**.
3. Se a sua conta usa **dois fatores**, o app pede o **código de 6 dígitos** do seu aplicativo autenticador.

O que você precisa saber:

- O app **recusa endereços `http://`** (sem o cadeado): a senha e os dados financeiros viajariam sem proteção.
- Depois que você entra, o app **guarda a sessão de forma segura no celular** e você não digita a senha a cada uso. A sessão se
  renova sozinha enquanto você usa e termina após **7 dias sem uso** (ou 30 dias no total, a critério do administrador);
  depois disso o app volta para a tela de entrada, avisando.
- O Android pode perguntar **"Salvar informações de acesso?"** (no Samsung, o Samsung Pass; em outros, o Google). É o gerenciador
  de senhas do celular: pode salvar ou tocar em **Cancelar**.
- **Contas que só entram por login único (SSO), ou só por chave de acesso (passkey) e sem senha, não entram no app.** Use o sistema
  no navegador.

### Lançar um movimento

![Tela Lançar, com valor, descrição, conta, categoria e data](/manual-img/app-celular/lancar.png)

Na aba **Lançar**:

1. Escolha **Despesa** ou **Receita**.
2. Digite o **Valor** (pode usar vírgula: `45,90`; ou ponto).
3. Digite a **Descrição**.
4. Escolha a **Conta** e, se quiser, a **Categoria**. A **Data** já vem preenchida com hoje.
5. (Opcional) **Fotografe o comprovante**, como está logo abaixo.
6. Toque em **Salvar lançamento**. Aparece *"Lançamento salvo."* e o formulário fica pronto para o próximo.

Se a conta tem mais de um **workspace** (por exemplo, pessoal e empresa), aparece um seletor no alto da tela: o lançamento vai para
o workspace escolhido. Se o seu papel no workspace é **leitor**, o app avisa que ele é somente leitura.

### Fotografar o comprovante e usar a leitura

Toque em **Fotografar**. Abre a **câmera do celular**: fotografe o comprovante e confirme com o **✓**. A foto volta para o app e
aparece na tela.

Em seguida o app **lê o comprovante no próprio celular** (leva cerca de um segundo, **sem internet**; a imagem não sai do aparelho
para isso) e mostra o cartão **Lido do comprovante**:

![O comprovante fotografado e, abaixo, o cartão "Lido do comprovante" com valor, data e descrição](/manual-img/app-celular/sugestoes.png)

- Cada item que o app conseguiu ler aparece com um botão **Usar**. Toque nele para colocar só aquele item no formulário.
- **Usar tudo** coloca valor, data e descrição de uma vez.
- **Ignorar** fecha o cartão.
- **O app nunca preenche sozinho.** A leitura de papel térmico às vezes erra, então **confira** o que entrou antes de salvar.

![O formulário depois de "Usar tudo": valor, descrição, data e categoria preenchidos](/manual-img/app-celular/preenchido.png)

Depois de usar, ajuste o que precisar (a **categoria**, por exemplo, o app não adivinha) e toque em **Salvar lançamento**.

**Para a leitura acertar mais:**

- Fotografe o papel **de frente**, sem inclinar o celular, e **inteiro**, com o valor total à vista.
- Use **boa luz** e evite sombra e reflexo. Alise o papel; cupom amassado ou desbotado é o pior caso.
- Se o app disser *"Não consegui ler valor nem data neste comprovante"*, **preencha à mão**: a foto continua indo como anexo.

O que o app costuma ler bem: o **valor total** (procura por "Total", "Débito", "Crédito", "Pix" e "R$", e ignora troco, desconto e
impostos), a **data** e o **nome do estabelecimento** (a linha acima do CNPJ). Comprovantes muito borrados ou de letra manuscrita
podem não sair.

**Sobre a foto:** ela é **reduzida** (cerca de 1600 pixels no lado maior, uns 300 KB) antes de ir ao servidor e fica como **anexo**
do lançamento. Se o lançamento salvar mas o envio da foto falhar (sem sinal, por exemplo), o app avisa: abra o lançamento em
**Lançamentos** e use **Adicionar comprovante**.

### Ver os lançamentos

![Lista dos lançamentos do mês, com o clipe indicando os que têm comprovante](/manual-img/app-celular/lancamentos.png)

Na aba **Lançamentos**:

- As setas **‹ ›** mudam o mês. Os valores em vermelho são despesas e os em verde, receitas.
- O **clipe 📎** mostra os lançamentos que têm comprovante.
- Se o mês tem mais de 30 lançamentos, toque em **Carregar mais**.
- Se não houver sinal, aparece *"Não foi possível falar com o servidor"* com **Tentar de novo**.

Toque em um lançamento para abrir o **detalhe**:

![Detalhe de um lançamento, com a miniatura do comprovante](/manual-img/app-celular/detalhe.png)

Lá você vê a data, a categoria e os **comprovantes** (toque na miniatura para ampliar) e pode **Adicionar comprovante** a qualquer
lançamento. Toque em **Fechar** para voltar.

### Sair

Toque em **Sair**, no alto da tela. A sessão guardada no celular é apagada e o servidor a cancela. Perdeu o celular? Em
outro dispositivo, abra **Sessões e dispositivos** ([Segurança e conta](help:seguranca-conta)) e encerre o **App SyncroFin**.

### Limites e privacidade

- **Precisa de internet.** Não há modo offline: sem sinal, não dá para salvar. (Os dados **não ficam guardados no celular**.)
- O app **não edita nem exclui** lançamentos, não mostra saldos e relatórios e não cria contas ou categorias: para isso, use o sistema completo.
- **A tela do app não aparece em capturas de tela nem na lista de aplicativos recentes**, para proteger os seus dados financeiros.
- O app **não faz backup do Android** e pede **só uma permissão**: acesso à internet. A câmera é aberta pelo aplicativo de câmera do
  celular, que faz a foto e a entrega ao SyncroFin.
- A leitura do comprovante é **feita no celular**: a imagem só vai ao servidor quando você **salva** o lançamento, como anexo.

### Problemas comuns

| Sintoma | O que fazer |
|---------|-------------|
| *"Endereço inválido"* | Confira se digitou o endereço do servidor certo, sem espaços. |
| *"O endereço precisa ser HTTPS"* | O endereço começa com `http://`. Peça ao administrador o endereço com `https://` ([Publicar com HTTPS](help:publicar-https)). |
| *"E-mail ou senha incorretos"* | Confira os dados. Se esqueceu a senha, use *Esqueceu a senha?* no site ([Segurança e conta](help:seguranca-conta)). |
| *"Não foi possível falar com o servidor"* | Sem internet, ou o endereço está errado, ou o servidor está fora do ar. Confira e toque em **Tentar de novo**. |
| *"Este servidor não aceita login por e-mail e senha"* | O servidor só permite login único (SSO). Use o sistema no navegador. |
| O app volta para a tela de entrada | A sessão expirou. Entre de novo. |
| *"Este servidor exige a verificação em duas etapas…"* | O administrador tornou o 2FA obrigatório e a sua conta ainda não tem. O app **não configura** o 2FA: abra o sistema no navegador, configure ([Segurança e conta](help:seguranca-conta)) e entre de novo no app. |
| *"Seu papel neste workspace é somente leitura"* | Peça a um dono do workspace para mudar seu papel para **Editor** ([Workspace](help:workspace)). |
| A leitura do comprovante não acha nada | Tente de novo com a foto de frente e boa luz, ou preencha à mão. |
| A câmera não abre | O app usa o aplicativo de câmera do celular: confira se ele está ativo e funcionando. |

### Para o administrador: gerar e entregar o app

O código do app fica na pasta `mobile/` do projeto (documentação técnica em `mobile/README.md`).

1. **Gerar o APK de release**, com a sua chave de assinatura (`npm run apk:release`, na pasta `mobile/`). O arquivo sai em
   `mobile/android/app/build/outputs/apk/release/`. Ele tem cerca de 25 MB.
2. **Guarde a chave (keystore) e as senhas, com cópia, e fora do repositório.** Sem a mesma chave o Android não deixa atualizar o
   app por cima: as pessoas teriam de desinstalar e instalar de novo.
3. **Entregue o `.apk`** por um canal seguro (a sua nuvem, um link interno, e-mail). Como o arquivo é o seu, avise que o Android vai
   pedir a autorização de "apps desconhecidos".
4. Confirme que o servidor tem **HTTPS** ([Publicar com HTTPS](help:publicar-https)): sem isso o app não conecta.

---

## Site instalável (PWA)

Para **iPhone, iPad ou computador** (e também no Android), o SyncroFin é um **aplicativo web instalável**: você abre o endereço do
sistema no navegador e o **instala na tela inicial**. Fica com ícone próprio, abre em tela cheia e se atualiza sozinho. É o
sistema **completo**, o mesmo do navegador.

### Android (Chrome)

1. Abra o endereço do SyncroFin no **Chrome** e entre com a sua conta.
2. Toque no menu **⋮** (canto superior direito) e em **Instalar aplicativo** (às vezes aparece como **Adicionar à tela inicial**).
3. Confirme em **Instalar**.

### iPhone e iPad (Safari)

1. Abra o endereço do SyncroFin no **Safari** e entre com a sua conta.
2. Toque no botão **Compartilhar** (o quadrado com uma seta para cima).
3. Role a lista e toque em **Adicionar à Tela de Início** e depois em **Adicionar**.

### Computador (Chrome ou Edge)

Na barra de endereço aparece um ícone de **instalação**. Clique nele e em **Instalar**. O SyncroFin passa a abrir numa janela própria.

### Limites do site instalável

- **Precisa de internet.** Sem conexão o aplicativo abre, mas **avisa que não alcança o servidor**. Por segurança, os dados
  financeiros **não ficam guardados no aparelho** para uso offline.
- **Sem notificações no celular.** Os avisos aparecem no **sino** dentro do sistema e, se o administrador configurou, por **e-mail**
  ([Notificações](help:notificacoes)).
- **Não aparece a opção de instalar?** O endereço precisa ser **HTTPS** (com cadeado): `http://` e número de IP não permitem
  instalar. Se você administra o servidor, veja [Publicar com HTTPS](help:publicar-https).

Mais respostas em [Perguntas frequentes](help:faq).
