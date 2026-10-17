# Conectores ERP

Os conectores ligam o SyncroFin Enterprise ao ERP da empresa. Hoje há suporte ao **Omie**; o **Conta Azul** aparece na lista, mas a integração ainda está em desenvolvimento.

> Disponível para quem tem a permissão **Conectar ERP** (`erp.manage`) para configurar e sincronizar, ou **Ver ERP** (`erp.read`) para consultar o histórico.

## Conectar o Omie

1. Em **Configurações do workspace**, abra **Conexões ERP**.
2. Clique em **Adicionar conexão** e escolha **Omie**.
3. Informe a **App key** e o **App secret** (gerados no Omie, em Configurações › Desenvolvedores).
4. Opcionalmente, informe o **código da categoria padrão** e o **ID da conta corrente padrão**: o Omie exige uma categoria em todo título a pagar ou receber enviado.
5. Salve e use **Testar conexão**.

As credenciais são guardadas **cifradas** e nunca são exibidas de novo. Para trocá-las, remova a conexão e crie outra.

## O que sincroniza

| Ação | Sentido | O que faz |
|---|---|---|
| Importar plano de contas | ERP → SyncroFin | Cria ou atualiza categorias a partir das categorias do Omie. Uma categoria que você já tinha com o mesmo nome é reaproveitada, não duplicada. |
| Importar beneficiários | ERP → SyncroFin | Cria ou atualiza clientes e fornecedores, com CPF ou CNPJ quando válido. |
| Enviar faturas | SyncroFin → ERP | Envia faturas **emitidas** (abertas) como contas a receber ou a pagar, no período escolhido. |
| Enviar transações | SyncroFin → ERP | Ainda não suportado pelo Omie; use o envio de faturas. |

Para enviar uma fatura, o cliente ou fornecedor dela precisa ter sido importado antes. Importe os beneficiários primeiro.

## Idempotência

Cada item sincronizado fica registrado em um **mapeamento** entre o id no SyncroFin e o id no ERP. Repetir uma sincronização atualiza o que mudou em vez de duplicar, e uma fatura já enviada não é enviada de novo.

## Acompanhar

A sincronização roda em segundo plano. O botão **Executar sincronização** enfileira o trabalho; o estado da conexão e o **histórico** (quantos criados, atualizados e com erro) atualizam sozinhos. Passe o mouse sobre o número de erros para ler as mensagens.

Um erro em um item não interrompe os demais. Uma falha geral (credencial recusada, Omie fora do ar) marca a execução como **Erro** e mostra a mensagem na conexão.

## Limites do Omie

O Omie aceita cerca de 3 requisições por segundo. O conector espaça as chamadas, então importações grandes podem levar alguns minutos.
