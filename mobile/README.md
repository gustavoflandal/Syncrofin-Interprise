# SyncroFin Mobile (Android)

App Android simples para **lançar movimentos na rua e fotografar o comprovante**. Conversa com o servidor SyncroFin
pela API que já existe (Community v0.17 ou Enterprise): não precisa de nada novo no servidor.

## O que faz (versão 1)

| Tela | Para quê |
|------|----------|
| **Login** | Endereço do servidor, e-mail, senha e código 2FA (quando a conta tem). Guarda a sessão no Keystore do Android. |
| **Lançar** | Despesa ou receita: valor, descrição, conta, categoria, data e a **foto do comprovante**. |
| **Lançamentos** | Lista do mês (navega entre meses, "carregar mais"). Ao tocar: detalhe, **comprovantes** e **adicionar comprovante**. |

Se a conta tem mais de um workspace, aparece um seletor no topo. Idiomas: o do celular (português, inglês ou espanhol).

**Leitura do comprovante (OCR):** depois de fotografar, o app lê a foto **no próprio celular** (ML Kit, sem internet;
a imagem não sai do aparelho para isso) e mostra um cartão **"Lido do comprovante"** com o valor, a data e o
estabelecimento que encontrou. Nada é preenchido sozinho: você toca em **Usar** (campo a campo) ou **Usar tudo**, confere e
salva. Comprovante de maquininha térmico costuma sair borrado, então a leitura **erra às vezes** e, quando não acha valor nem
data, o app avisa e você preenche à mão. Só existe no app Android (no navegador não há leitor).

**Fora da versão 1** (de propósito): fila offline, login por SSO ou chave de acesso (passkey),
edição e exclusão de lançamentos, notificações. Veja "Próximos passos".

## Requisitos

- Node 22, JDK 21, Android SDK com `platforms;android-36` e `build-tools;36.0.0`
  (`ANDROID_HOME` apontando para o SDK, ou `android/local.properties` com `sdk.dir=...`).
- O servidor precisa ser **HTTPS** (o app recusa `http://`, exceto `localhost` e `10.0.2.2` para desenvolvimento).

## Comandos

```bash
cd mobile
npm install --legacy-peer-deps   # ver a nota abaixo
npm test                         # 77 testes (API, telas, dinheiro, datas, textos)
npm run typecheck
npm run dev                      # o app no navegador, em http://localhost:5174 (ver "Desenvolvimento")

npm run apk:debug                # gera android/app/build/outputs/apk/debug/app-debug.apk
npm run apk:release              # gera o APK de release (assinado se houver keystore.properties)
```

> `--legacy-peer-deps`: o npm 11 falha ao resolver as dependências opcionais do `vitest` ("Cannot read properties of
> null (reading 'edgesOut')"). O `package-lock.json` foi gerado assim; use o mesmo (`npm ci --legacy-peer-deps`).

## Instalar no celular

1. Copie o `app-debug.apk` para o celular (cabo, e-mail, nuvem).
2. Abra o arquivo. O Android pede para permitir **instalar apps desta fonte** (Configurações → Apps → Acesso especial →
   *Instalar apps desconhecidos*): autorize o aplicativo que você usou para abrir o arquivo.
3. Instale, abra o **SyncroFin**, informe o endereço do servidor, o e-mail e a senha.

O APK de *debug* é assinado com uma chave de teste do Android: serve para instalar e testar. Para uso no dia a dia e
para **receber atualizações por cima**, gere o de *release* com a sua chave (abaixo).

## APK de release (com a sua chave)

```bash
keytool -genkeypair -v -keystore syncrofin-release.keystore -alias syncrofin \
  -keyalg RSA -keysize 2048 -validity 10000
```

Crie `mobile/android/keystore.properties` (**não vai para o git**):

```
storeFile=C:/caminho/seguro/syncrofin-release.keystore
storePassword=...
keyAlias=syncrofin
keyPassword=...
```

Depois `npm run apk:release`. Confira com `apksigner verify --print-certs app-release.apk`.

> **Guarde a keystore e as senhas em local seguro, com cópia.** Sem a mesma chave o Android **não aceita** atualizar o
> app: seria preciso desinstalar e instalar de novo. E ela nunca deve ir para o repositório.

**Tamanho:** o APK de release tem ~25 MB (só `arm64-v8a` e `armeabi-v7a`). O de debug tem ~53 MB porque mantém as arquiteturas x86
do emulador: o leitor de texto traz uma biblioteca nativa por arquitetura.

O identificador do app (`br.com.syncrofin.mobile`, em `capacitor.config.ts` e `android/app/build.gradle`) também é parte da
identidade: trocá-lo depois faz o Android tratar como outro aplicativo.

## Como funciona (para quem for mexer)

- **Capacitor 8 + React 19 + Vite.** A interface é uma página web dentro de uma WebView; a câmera, o armazenamento seguro
  e a rede vêm de plugins nativos.
- **Rede:** `CapacitorHttp` está ligado (`capacitor.config.ts`). O CORS do servidor só aceita o próprio endereço, e a
  WebView roda em `https://localhost`; as chamadas nativas não passam por CORS. Não é preciso mexer no servidor.
- **Sessão:** os dois tokens ficam no **Keystore** (`@aparajita/capacitor-secure-storage`), nunca em `localStorage`. O
  token de acesso dura minutos; o app envia `X-Refresh-Mode: body` no login e guarda o **token de renovação** (o app não
  tem cookie), renova sozinho ao receber 401 (uma renovação por vez, porque o token é de uso único) e repete a chamada.
  A sessão vale o que o servidor definir (7 dias sem uso, 30 no máximo); ao terminar, o app volta para o login com um
  aviso. **Sair** também cancela a sessão no servidor, e ela aparece em *Sessões e dispositivos* como "App SyncroFin". Se o servidor **exige o segundo fator** e a conta ainda não tem, o app avisa no login (o app não configura 2FA; isso é feito no site) e trata um bloqueio no meio do uso como sessão encerrada.
- **Foto:** `@capacitor/camera` (Base64, sem salvar na galeria). Antes de enviar, reduz para 1600 px e recomprime em JPEG
  (cerca de 300 KB). Vai como anexo do lançamento (`POST /api/transactions/{id}/attachments`). Se o lançamento é salvo e a
  foto falha, o app avisa e a foto pode ser reenviada pelo detalhe.
- **Segurança do app:** sem backup do Android (`allowBackup=false`), sem tráfego HTTP (`usesCleartextTraffic=false`),
  captura de tela bloqueada e a tela some no seletor de apps (`FLAG_SECURE`, **só no release**: o build de debug permite capturar,
  para documentação e relatos de problema). A única permissão é `INTERNET`.
- **Valores** trafegam como texto decimal ("45.90"), sem passar por `float`.

Estrutura: `src/lib` (API, sessão, armazenamento, câmera, imagem, dinheiro, datas, textos), `src/screens` (Login,
NewTransaction, Transactions, TransactionDetail), `android/` (projeto nativo gerado pelo Capacitor, com ajustes).
Ao mudar o código web: `npm run cap:sync` (o `apk:*` já faz isso).

### Desenvolvimento no navegador

`npm run dev` abre o app em `http://localhost:5174`. Como o navegador **aplica CORS** (o celular não), o servidor de
desenvolvimento precisa aceitar essa origem, ou o navegador precisa estar sem segurança web
(`msedge --disable-web-security --user-data-dir=...`). Foi assim que o app foi exercitado contra o backend real.

## Testar num celular pelo cabo (sem HTTPS)

O APK de **debug** (e só ele) aceita HTTP para `localhost`, `127.0.0.1` e `10.0.2.2`
(`android/app/src/debug/res/xml/network_security_config.xml`). Com o celular em modo desenvolvedor e a depuração USB ligada:

```bash
adb reverse tcp:8100 tcp:8100     # o "localhost:8100" do celular passa a ser o do computador
adb install -r android/app/build/outputs/apk/debug/app-debug.apk
```

No app, use o servidor `http://localhost:8100`. Para inspecionar ou automatizar a WebView do app rodando no celular:
`adb forward tcp:9333 localabstract:webview_devtools_remote_<pid do app>` e abra `chrome://inspect` (ou conecte o puppeteer em
`http://localhost:9333`). O APK de **release** continua só HTTPS.

Em Samsung, se a instalação por cabo falhar, desligue o **Auto Blocker** (Configurações → Segurança e privacidade).

## Como o OCR funciona

- **Leitor:** `android/.../ReceiptOcrPlugin.java`, um plugin do Capacitor escrito para este app sobre o ML Kit *Text Recognition*
  (modelo latino embutido, `com.google.mlkit:text-recognition`; funciona offline). Devolve o texto e a posição vertical de cada linha.
- **Interpretação:** `src/lib/receipt-parser.ts`, em TypeScript e testada sem celular. Tolera os erros típicos de papel térmico:
  `RS`/`R5` no lugar de `R$`, ponto no lugar de vírgula, letra `O` no lugar de zero, datas com separadores trocados.
  - *Valor:* pontua as linhas por palavra-chave (TOTAL, DÉBITO, CRÉDITO, PIX, VALOR) e pelo `R$`, e desconta SUBTOTAL, TROCO,
    DESCONTO, TRIBUTOS, PARCELA. Sem `R$` nem palavra-chave, não sugere nada.
  - *Data:* a primeira data válida que não seja futura.
  - *Estabelecimento:* a linha logo acima do CNPJ; senão, a primeira linha do topo que pareça um nome. Ignora a marca da maquininha
    (Stone, Cielo, Rede...), endereços e linhas de pagamento.
- **Foto original:** o OCR lê a foto como a câmera entregou; só depois ela é reduzida para o envio.
- Para afinar contra comprovantes reais: no console do app, `localStorage.setItem('syncrofin_debug_ocr','1')` faz o app escrever o
  texto lido no `logcat` (`adb logcat -s Capacitor/Console`). Desligado por padrão.

## O que foi verificado e o que não foi

**Automatizado:** 77 testes; o app no navegador contra o backend real; APK debug e release assinado compilam
(`apksigner verify`); `aapt2` confirma só `INTERNET`, backup e HTTP em claro desligados.

**Num celular real** (Samsung Galaxy A55, Android 16, APK de debug, servidor local pelo `adb reverse`):

| Verificado | Resultado |
|---|---|
| Instalação e abertura do app | Ok |
| Login por e-mail e senha pela rede **nativa** (`CapacitorHttp`, sem CORS) | Ok; senha errada mostra a mensagem |
| Login com **2FA** | Ok; código errado é recusado, código certo entra |
| Sessão no **Keystore** | Ok: nada em `localStorage`; continua logado depois de fechar e reabrir o app |
| **Câmera** nativa | Ok: a foto volta para o app e aparece na pré-visualização |
| **Upload da foto pela camada HTTP nativa** (o ponto de maior risco) | Ok: o `FormData` chegou como multipart e o servidor guardou o anexo (JPEG 1200×1600, 112 KB, legível) |
| Lançamento com valor e categoria | Ok (`12,34` gravado como `12.34`) |
| Lista do mês e detalhe com **miniatura** do comprovante (download nativo em base64) | Ok |
| Servidor inacessível | Mensagem de rede e "Tentar de novo"; volta a funcionar quando o servidor volta |
| Captura de tela (`FLAG_SECURE`) | O conteúdo do app sai preto |
| Nenhum *crash* no `logcat` durante os testes | Ok |

**OCR, no aparelho** (Galaxy A55, comprovantes reais):

| Comprovante | Resultado no app |
|---|---|
| Maquininha Stone (débito), foto já reduzida | Plugin leu em 430 ms, offline, com ruído (`DÉBIT0e RS 100.00`). O parser extraiu valor `100.00`, data `2026-06-06` e "Posto Trevao": os três certos (verificado sobre o texto real, nos testes) |
| Cupom fiscal de supermercado (NFC-e), foto em resolução original, inclinada | **Cartão dentro do app**: Valor R$ 59,39, Data 1 de ago. de 2026 (a "Emissão 01/08/26" do rodapé), Descrição "Pjk Franco e Cia Ltda": os três certos. "Usar tudo" e "Salvar" gravaram no servidor `2026-08-01`, `59.39`, despesa, com o comprovante anexado |

O que a medição mostrou (e virou correção): na 1ª foto do cupom o **valor não era sugerido**, porque o leitor devolve o rótulo
("Valor Total R$") e o número ("59,39") em linhas separadas e, com a foto inclinada, o número fica ~0,01 mais baixo que o
rótulo. Agora cada número solto é ligado ao rótulo vizinho. Os textos reais dessas duas fotos (com CNPJ, telefone, endereço e
chave de acesso mascarados) são fixtures dos testes.

**Só dois comprovantes reais foram medidos**, de dois tipos. A taxa de acerto em Pix, cupons de outros mercados, notas
manuscritas ou fotos ruins é desconhecida; os casos desses tipos nos testes são escritos à mão.

**Ainda não verificado:** cancelar a câmera no meio (coberto por teste automatizado, não no aparelho); sessão expirada de
verdade (7 dias sem uso) e a renovação silenciosa em aparelho real (coberta por teste automatizado); servidor HTTPS com certificado real (o teste foi por `localhost`); outros aparelhos e versões do Android;
a atualização do app por cima (exige a chave de release); o job de APK no CI.

Aviso inofensivo no `logcat`: `Error injecting safe area CSS: ... (reading 'style')`, do Capacitor ao iniciar, antes de a
página existir. Não afeta o app.

## Próximos passos

1. **Testar num celular real** (login, foto, upload, sessão).
2. **Medir o OCR com mais comprovantes reais** (cupom fiscal, Pix, outras maquininhas) e ajustar o parser.
3. Sessões renováveis no servidor (plano Enterprise C4), para não pedir a senha todo dia.
4. Fila offline com proteção contra lançamento duplicado.
