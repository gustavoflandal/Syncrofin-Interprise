# Saúde financeira e previsão de caixa

No [Painel](help:painel), o cartão **Saúde financeira** responde a duas perguntas: **"Estou bem?"** e **"Vou ficar sem
dinheiro? Quando?"**

## A nota (0 a 100)

A nota é uma **média ponderada de três indicadores simples**, cada um com uma meta:

| Indicador | Como é calculado | Meta | Peso |
|-----------|------------------|------|------|
| **Taxa de poupança** | (receitas − despesas) ÷ receitas | 20 % | 40 |
| **Reserva de emergência** | saldo líquido ÷ despesa mensal média | 6 meses | 40 |
| **Orçamentos em dia** | % das categorias com orçamento dentro do limite | 100 % | 20 |

Cada linha do cartão mostra o **valor atual** e a **meta**.

**Faixas:** **75 ou mais** = *Em boa forma*; **50 a 74** = *Requer atenção*; **abaixo de 50** = *Em risco*.

### Regras que evitam números enganosos

- As médias usam os **3 últimos meses completos**. O mês corrente, incompleto, distorceria a razão.
- Um indicador **sem dados** (por exemplo, sem nenhuma receita, ou sem orçamentos) é **deixado de fora** e os
  pesos são redistribuídos: ele não vira "zero". Se não houver dado para nenhum indicador, aparece **Sem nota
  ainda** e um pedido para registrar receitas e despesas.
- O **saldo líquido** considera contas correntes, poupança e carteiras **abertas**. **Cartão de crédito não é
  dinheiro disponível**. Contas em outra moeda só entram se houver o saldo convertido.
- Se você tem **cobranças a receber vencidas**, o cartão mostra um aviso com a quantidade e o total.

## Previsão de caixa (próximos 90 dias)

O gráfico parte do **saldo líquido de hoje** e soma **apenas o que já está prometido**:

- suas [contas recorrentes](help:recorrentes) futuras;
- as **cobranças em aberto** ([Cobranças](help:cobrancas)): a receber somam, a pagar subtraem, no dia do vencimento
  (as **vencidas** entram como devidas hoje).

Ele agrupa **por semana** e mostra **Hoje**, **Ponto mais baixo** e **Em 90 dias**. Se o saldo ficar negativo, um
alerta vermelho informa **a partir de que semana**. A linha tracejada vermelha é o zero.

### O que a previsão **não** faz

Ela **não estima gastos do dia a dia** (mercado, lazer), **faturas de cartão** nem **cobranças em moeda
estrangeira**. Por isso é uma **projeção**, não uma previsão: lê-se como *"você estará aqui se nada mais
acontecer"*. O próprio cartão avisa disso.

## Avisos relacionados

Quando o caixa projetado fica negativo nos próximos 30 dias, o sistema envia um aviso ao sino e, se configurado, por
e-mail ([Notificações](help:notificacoes)).

## Como melhorar a nota

- **Poupança:** reduza despesas ou aumente receitas.
- **Reserva:** mantenha um saldo equivalente a 6 meses de despesas.
- **Orçamentos:** crie orçamentos ([Orçamentos](help:orcamentos)) e mantenha-os dentro do limite.
