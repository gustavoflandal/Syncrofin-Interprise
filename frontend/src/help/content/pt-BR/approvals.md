# Aprovações

## Fluxo de aprovação por alçada

Quando uma transação supera o valor configurado em **Configurações → Regras de alçada**,
ela fica em fila de aprovação até ser analisada por um aprovador.

Transações pendentes **não aparecem** no DRE, DFC nem no saldo até serem aprovadas.

## Aprovar ou rejeitar

**Administração → Aprovações** mostra todas as transações aguardando análise.

1. Clique em **Aprovar** para liberar o lançamento — ele entra nos relatórios imediatamente.
2. Clique em **Rejeitar** para recusar, com nota opcional.

Quem criou a transação **não pode** aprovar a própria — o sistema impede para garantir
separação de funções.

## Cancelar uma transação pendente

O criador da transação pode cancelá-la enquanto ela ainda estiver pendente, usando o botão
**Cancelar** na lista de transações (badge "Pendente").

## Configurar regras de alçada

Em **Configurações → Fechamento & Aprovações → Regras de alçada**:

- **Regra global:** todas as transações acima do valor informado precisam de aprovação.
- **Regra por grupo de categoria:** substitui a regra global para transações daquele grupo.

Exemplo: regra global de R$ 5.000 e regra de "Despesas operacionais" de R$ 2.000 faz com que
transações de despesas operacionais acima de R$ 2.000 precisem de aprovação, enquanto outros
grupos precisam apenas acima de R$ 5.000.

## Segregação de funções (C3)

Quando habilitada em **Configurações → Segregação de funções**, o sistema impõe que:

1. **Quem cria** a transação **não pode aprovar** (já existia).
2. **Quem cria** a transação **não pode rejeitar** a própria — deve usar **Cancelar**.
3. **Quem cria** ou **quem aprova** a transação **não pode liquidar** (confirmar pagamento).

Após a aprovação, um terceiro membro com permissão de aprovação pode clicar em **Liquidar** para
confirmar que o pagamento foi efetuado. O sistema registra quem liquidou e quando.

Veja também: [Períodos](help:periods).
