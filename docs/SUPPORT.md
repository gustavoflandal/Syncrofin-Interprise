# Modelo de suporte, licenciamento e versionamento — SyncroFin Enterprise

## 1. Licenciamento

### Código herdado (Community)

O núcleo do SyncroFin Enterprise foi derivado do **Securo v0.16.0**, publicado sob
[AGPL-3.0](../LICENSE). Esse código permanece AGPL-3.0 de seus autores originais.
Nenhuma parte do aviso de licença foi removida.

### Código novo (Enterprise)

As funcionalidades adicionadas neste repositório (módulos de NF-e, webhooks,
multiempresa consolidada, onboarding empresarial, canal do titular, etc.) são
**propriedade de Gustavo Flandal**. Uso restrito a licenciados.

### O que você pode fazer com a licença Enterprise

- Instalar e operar em quantos servidores a licença cobrir.
- Modificar o código para uso interno — sem redistribuição.
- Fazer backups do código para recuperação de desastres.

### O que a licença não permite

- Redistribuir o software (fonte ou binário) para terceiros sem autorização.
- Sublicenciar ou revender como serviço gerenciado sem acordo específico.
- Remover ou modificar avisos de autoria ou copyright.

---

## 2. Canais de suporte

| Canal | Uso | SLA de resposta |
|---|---|---|
| **Issues GitHub** (privado) | Bugs e feature requests | 5 dias úteis (P3/P4) |
| **E-mail** `suporte@syncrofin.app` | Dúvidas de uso, problemas de implantação | 3 dias úteis |
| **E-mail** `segurança@syncrofin.app` | Vulnerabilidades (use PGP; chave no README) | 24 horas (triagem) |

> Vulnerabilidades de segurança **nunca** devem ser abertas como issue público.
> Use o [aviso privado do GitHub](https://github.com/gustavoflandal/syncrofin-enterprise/security/advisories/new)
> ou envie e-mail criptografado para `segurança@syncrofin.app`.

---

## 3. Definições de severidade

| Nível | Descrição | Exemplo |
|---|---|---|
| **P0 — Crítico** | Dado corrompido, perda de dados, falha de segurança explorável em produção | Injeção SQL, falha de autenticação |
| **P1 — Alto** | Funcionalidade central indisponível, sem workaround | Importação bancária falha para todos |
| **P2 — Médio** | Funcionalidade degradada, workaround existe | Relatório lento com >50k transações |
| **P3 — Baixo** | Comportamento inesperado, cosméticos, pedidos de melhoria | Texto de UI fora de contexto |

---

## 4. SLA de resolução (instâncias de produção licenciadas)

| Severidade | Resposta inicial | Correção / mitigação |
|---|---|---|
| P0 | 4 h | 24 h (patch de emergência ou workaround documentado) |
| P1 | 24 h | 5 dias úteis |
| P2 | 5 dias úteis | Próxima versão minor |
| P3 | 15 dias úteis | Backlog priorizado |

> O SLA aplica-se apenas a instâncias de produção com contrato ativo. Implantações
> de desenvolvimento, homologação e avaliação não têm garantia de SLA.

---

## 5. Política de versionamento

O SyncroFin Enterprise segue **Semantic Versioning** (`MAJOR.MINOR.PATCH`):

- **PATCH** (`0.17.x`): correções de bug e segurança, sem migração de banco obrigatória.
  Sempre seguro de aplicar imediatamente.
- **MINOR** (`0.x.0`): funcionalidades novas com migrações Alembic compatíveis para frente.
  As migrações rodam automaticamente no startup do backend.
- **MAJOR** (`x.0.0`): mudanças incompatíveis (schema, API ou fluxo de dados). Publicado
  com guia de migração e janela de depreciação de no mínimo 90 dias.

### Branches e tags

| Branch / tag | Descrição |
|---|---|
| `main` | Versão estável mais recente |
| `feature/*` | Desenvolvimento ativo — não usar em produção |
| `vX.Y.Z` | Tag imutável que dispara o CI/CD de publicação de imagem |

### Ciclo de suporte (LTS)

- Versões **MINOR** ficam com suporte de segurança por **12 meses** após o lançamento
  da próxima versão MINOR estável.
- Correções de segurança P0/P1 são backportadas para a versão LTS corrente sem custo
  de atualização de licença.

---

## 6. Atualizações e migrações

### Caminho de atualização suportado

Atualizações incrementais (`N → N+1`) são o único caminho suportado. Nunca pule versões
intermediárias — cada release inclui apenas as migrações acumuladas desde a anterior.

### Rollback

Migrações de banco não têm downgrade automático. Antes de atualizar em produção:

1. Faça um dump (`pg_dump`) ou ative o perfil `backup`.
2. Atualize.
3. Se precisar reverter, restaure o dump e use a imagem anterior.

---

## 7. Privacidade e dados

O SyncroFin Enterprise é **self-hosted**: todos os dados ficam no servidor do cliente.
Nenhum dado financeiro é transmitido para Gustavo Flandal ou terceiros, exceto:

- Provedores bancários (Pluggy, Enable Banking, SimpleFIN) — ativados explicitamente.
- Provedor de NF-e (Focus NFe, eNotas, PlugNotas) — ativado explicitamente.
- LLM externo (OpenAI, Anthropic) — apenas se `AGENTS_ENABLED=true` e configurado.

Para obrigações LGPD, consulte `docs/ADMIN.md §8` (canal do titular).

---

## 8. Contato comercial

Novos contratos, renovações, downgrades ou perguntas sobre licenciamento:
`comercial@syncrofin.app`
