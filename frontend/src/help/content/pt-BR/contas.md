# Contas

Em **Contas** você cadastra onde seu dinheiro está e conecta bancos para importar tudo automaticamente.

## Contas manuais e conexões bancárias

A tela tem duas áreas:

- **Contas Manuais:** contas que você mesmo alimenta (lançando transações ou [importando extratos](help:importar)).
- **Conexões Bancárias:** contas trazidas de um banco por **sincronização**. Cada conexão mostra a instituição, as
  contas dela e a **última sincronização**.

Contas **encerradas** ficam em uma área própria (**Contas Encerradas**) e saem dos totais.

## Tipos de conta

**Conta Corrente**, **Poupança**, **Cartão de Crédito**, **Investimento** e **Carteira** (dinheiro em espécie).

## Criar uma conta manual

Clique em **Adicionar Conta**:

| Campo | Observação |
|-------|------------|
| **Nome da conta** | Como aparece no sistema. |
| **Tipo** | Veja acima. |
| **Moeda** | Moeda da conta. |
| **Saldo** | Saldo inicial (o "saldo inicial" vira um lançamento de abertura). Em **cartão de crédito**, o campo é **Valor devido**: informe quanto você deve hoje, como número positivo. |
| **Data do saldo** | Data a que o saldo se refere. |

Para editar, use **Editar Conta**. O **Nome de exibição** substitui o nome que o banco informa, em todo o sistema.

## Cartão de crédito

Para cartões, preencha (são opcionais, mas ativam recursos):

- **Limite do cartão**, **Dia de fechamento** e **Dia de vencimento** (dia do mês, 1 a 31);
- **Mínimo** da fatura.

Com isso, a tela da conta mostra por **ciclo de fatura**: **Total da fatura**, **Compras**, **Pagamentos**,
**Limite disponível**, **Utilização**, o **Vencimento** e alertas (*Vence hoje*, *Vence em N dias*, *Atrasado*).
Navegue entre **Ciclo anterior** e **Próximo ciclo**. Sem os dias de fechamento e vencimento aparece
**Configurar ciclo**: eles ativam filtros por fatura, alertas de vencimento e o enquadramento correto das compras.

## Detalhe de uma conta

Clique em uma conta para ver: **Saldo atual**, **Entradas**, **Saídas**, **Saldo projetado** e as transações da
conta, com o **saldo corrente** linha a linha. **Ver transações** abre a lista filtrada por essa conta.

## Conectar um banco

Clique em **Conectar Banco** e escolha o **conector**. Só aparecem os que o administrador configurou.

| Conector | Para quê | Como conecta |
|----------|----------|--------------|
| **Pluggy** | Bancos brasileiros (Open Finance) | Abre o widget do Pluggy dentro do sistema: escolha o banco e autorize. |
| **Enable Banking** | Bancos europeus (PSD2) | Você escolhe o **país** e o **banco**; é redirecionado ao banco para autorizar e volta ao sistema. |
| **SimpleFIN** | Bancos dos EUA e internacionais | Gere um **token de configuração** no SimpleFIN Bridge e **cole** aqui (uso único). |

Antes de abrir o conector, **Opções de sincronização** permitem decidir o que importar (por exemplo,
**Importar transações pendentes** e **Importar ativos de investimento**). Depois da autorização, o sistema
importa contas, saldos e transações; pode levar um minuto. **Não feche a aba** enquanto isso.

> No **Enable Banking em modo restrito (plano gratuito)**, as contas precisam ser vinculadas no portal do
> provedor *antes*. Se nenhuma conta aparecer, o sistema mostra **Contas ainda não vinculadas** com um botão para
> abrir o portal e outro para tentar novamente.

### Configurações da conexão

Em **Configurações da conexão** você define o **Apelido**, a **Origem da pessoa** (de onde tirar o nome de quem
pagou/recebeu: comerciante, dados de pagamento, descrição, automático ou nenhuma) e se importa transações
pendentes ou ativos de investimento.

### Sincronizar, reconectar e desconectar

- **Sincronizar:** força uma atualização agora. O sistema também sincroniza sozinho, de hora em hora.
- **Reconectar:** aparece quando a conexão **expirou** ou deu erro (*"Conexão expirada — reconecte para corrigir"*).
  Você é levado a autorizar de novo, **sem perder** o histórico. Quando a autorização do banco expira, um aviso
  aparece no sino ([Notificações](help:notificacoes)).
- **Desconectar:** remove a conexão **e as contas e transações sincronizadas** dela. É irreversível.

## Encerrar e excluir

- **Encerrar conta:** esconde a conta dos totais e, se for conectada, interrompe a sincronização. Dá para
  **Reabrir conta**.
- **Excluir conta:** remove também **todas as transações e registros de importação**. **Irreversível.**

## Contas de crédito compartilhadas

Se várias contas compartilham a mesma linha de crédito, o saldo aparece como **Linha de crédito compartilhada**.

## Saldos e o que "saldo" significa

Numa conta **manual**, o saldo é a soma das transações (incluindo o lançamento de abertura). Numa conta
**conectada**, vale o valor informado pelo banco, para bater com o aplicativo dele.
