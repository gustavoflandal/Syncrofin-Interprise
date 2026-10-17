# Pagamentos (PIX e TED)

**Pagamentos** emite ordens de pagamento PIX ou TED pela API do banco, sempre com **dupla aprovação**.
O módulo fica no menu junto de Títulos, em workspaces do tipo **Negócios**.

## O caminho de uma ordem

1. **Rascunho** — alguém com a permissão `payments.write` cria a ordem: método, valor, favorecido e a chave PIX
   (ou banco, agência e conta, no caso de TED).
2. **Aguardando aprovação** — o criador clica em **Enviar para aprovação**.
3. **Aprovada** — duas pessoas diferentes aprovam (permissão `payments.approve`).
4. **Enviada** — uma terceira pessoa, com a permissão `payments.send`, envia ao provedor.
5. **Confirmada**, **Falhou** ou **Cancelada** — o retorno do provedor chega por webhook ou pela consulta de status.

## Regras que não têm exceção

- Quem **criou** a ordem não a aprova nem a rejeita (para desistir, use **Cancelar ordem**).
- A segunda aprovação vem de alguém **diferente do primeiro aprovador**.
- Quem **envia** é diferente do criador e dos dois aprovadores.
- Não existe configuração para desligar a dupla aprovação.

**Rejeitar** devolve a ordem a rascunho e zera as aprovações já dadas: o criador ajusta e reenvia.

## Confirmação e lançamento

Quando o pagamento é confirmado, o sistema cria sozinho um **lançamento de débito** na conta de origem
(ou na primeira conta corrente, se nenhuma foi escolhida) e, se a ordem estiver ligada a uma fatura, a baixa.
A confirmação de um webhook é sempre conferida de novo no provedor antes de lançar.

Uma tarefa em segundo plano consulta a cada 5 minutos as ordens enviadas que ainda não têm retorno. Você também pode
usar **Consultar status** a qualquer momento.

## Provedor sandbox

O provedor **sandbox** não movimenta dinheiro: confirma a ordem alguns segundos depois do envio. Serve para
conhecer o fluxo e para testes. Adaptadores bancários reais entram como novos provedores, sem mudar o fluxo.

## Permissões

| Permissão | Para quê |
|---|---|
| `payments.read` | ver as ordens |
| `payments.write` | criar, editar rascunhos, enviar para aprovação e cancelar |
| `payments.approve` | aprovar e rejeitar |
| `payments.send` | enviar ao provedor |

O papel **Editor** padrão não aprova nem envia pagamentos; crie um papel próprio (**Configurações → Papéis**) para quem fará isso.

Veja também: [Aprovações](help:approvals) e [Títulos a pagar e a receber](help:titulos).
