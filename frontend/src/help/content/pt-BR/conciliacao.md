# Conciliação

**Conciliação** é o casamento automático entre **o dinheiro que se move** (transações importadas ou sincronizadas) e
**o que você esperava** que acontecesse: uma **cobrança** a receber ou a pagar, ou uma **conta recorrente**. Assim,
quando um cliente paga, a cobrança se quita sozinha, sem você procurar a transação.

Fica na tela [Regras](help:regras), nas abas **Regras**, **Esperando você** e **Histórico** (a conciliação de
cobranças exige um workspace de negócio).

## Dois momentos

A conciliação procura o casamento em dois momentos, e a evidência não é a mesma:

- **Quando o dinheiro entra ou sai** (uma transação chega): procura a cobrança ou a recorrente que ela quita;
- **Quando a cobrança é emitida**: procura um pagamento que já tenha acontecido.

## O que pode acontecer

Cada regra de conciliação tem um resultado quando o par casa:

| Resultado | O que faz |
|-----------|-----------|
| **Liga sozinho** | Faz o vínculo (quita a cobrança ou vincula a recorrente) sem perguntar. |
| **Sugere** | Não liga: manda o par para a fila **Esperando você**, para você confirmar. |

## As regras que já vêm prontas

O sistema traz regras padrão (que melhoram com o produto). Exemplos:

- **Pessoa conhecida, valor exato**: a pessoa é a mesma da cobrança e o valor bate;
- **Pessoa conhecida, pago com retenção**: o valor bate descontado o imposto retido (usa as alíquotas do seu país);
- **Valor exato, qualquer pessoa**;
- **Valor próximo e descrição parecida**;
- **Mesma conta, valor exato**;
- **Pessoa conhecida, parte do valor**: para quem paga parcelado (o restante continua em aberto);
- **Pessoa conhecida, várias faturas de uma vez**: um pagamento que cobre mais de uma cobrança.

Você pode **alterar** uma regra padrão (aparece *Alterada*; **Voltar ao padrão** restaura), **desativar/excluir** (ela
pode ser recuperada) ou criar a **sua própria** (**Nova regra de conciliação**, marcada como *Sua*).

### Montando uma regra

- **O que fazer quando casar:** ligar ou sugerir.
- **Quem pagou ou recebeu:** qualquer um, ou a pessoa da cobrança.
- **O quão perto o valor precisa estar:** exatamente o devido, dentro de uma **margem**, **descontado o imposto
  retido**, **parte do que se deve** ou **várias faturas somadas** (com um máximo de faturas e, opcionalmente, uma
  taxa admitida).
- **Distância entre as datas:** dias de **adiantamento** e de **atraso** permitidos.
- **Semelhança da descrição:** de 0 a 1 (vazio ignora a descrição).
- **Quando esta regra se aplica:** limite por **contas**, **pessoas**, **entrada ou saída**, **moedas**, **faixa de
  valor** e **texto do extrato** (deve conter / não pode conter).

Regras podem ser **exportadas e importadas** entre instalações.

## Esperando você

A aba **Esperando você** lista os casamentos duvidosos: *"Um pagamento pode quitar a cobrança X"*, com a **evidência**
(*valor bate exatamente*, ou *esperado R$ X, movimentado R$ Y*, dias de diferença, mesma pessoa).

- **Ligar** aceita e faz o vínculo;
- **Descartar** recusa: esse par **nunca é sugerido de novo**.

Sugestões antigas sem resposta expiram depois de cerca de 60 dias. Quando a fila está vazia: *"Nada para revisar. Tudo
casou sozinho."*

## Histórico

A aba **Histórico** é o registro do que a conciliação fez: vínculos automáticos e manuais, sugestões, aceites,
recusas e vínculos **desfeitos**. Cada linha diz **se foi uma pessoa ou o sistema**.

## Conciliação automática

Em **Configurações do workspace**, um dono pode definir quão confiante o sistema precisa estar para **aceitar sozinho**
as sugestões, em vez de deixá-las na fila. Só valem casamentos de **valor exato**, até **7 dias** do vencimento e de
**uma** cobrança (nunca um pagamento dividido entre várias). Tudo fica no histórico e pode ser desfeito
desvinculando. Veja [Workspace](help:workspace).

## Recorrentes

O mesmo mecanismo vincula uma transação real à [conta recorrente](help:recorrentes) que ela cumpre, para não contar
duas vezes e avançar a próxima ocorrência.
