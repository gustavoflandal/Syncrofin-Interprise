# Diagnóstico e backlog de melhorias

> Análise feita sobre o código herdado do Securo v0.16.0 já renomeado para SyncroFin.
> Cada item traz o **porquê**, o **onde** e um **critério de pronto** para poder virar uma
> tarefa/issue diretamente. Prioridades: **P0** bloqueia operar o projeto como seu · **P1** risco
> real de segurança/qualidade · **P2** melhorias de manutenção/produto · **P3** ideias.

## 1. Diagnóstico

### Pontos fortes

- **Cobertura ampla de funcionalidades** para finanças pessoais e de pequenos negócios, com
  foco real no Brasil (Pluggy/Open Finance, Tesouro Direto, faturas de cartão com convenção
  brasileira, CPF/CNPJ via *fiscal pack*, preço médio de investimentos).
- **Arquitetura limpa e previsível:** rotas finas → serviços → modelos; multi-tenancy por
  workspace com papéis; módulos ligáveis por tipo de workspace; agentes de IA totalmente
  opcionais e isolados.
- **Boa base de testes:** ~1.010 testes no backend (passam com o rename) e ~740 no frontend.
- **Código bem comentado**: comentários explicam decisões ("por quê"), o que reduz o custo de
  entrada.
- **Operação madura:** lockfile com hash, Helm chart completo, migrações com verificação de cadeia,
  rate limit, 2FA/passkey/OIDC, backup criptografado.

### Pontos de atenção

| Área | Observação |
|------|-----------|
| CI/CD | ~~Inexistente~~ **Implementado** (falta a primeira tag). Antes: inexistente no repositório (o `.github/` do upstream não veio). Imagens de produção, chart e `install.sh` dependem de publicação que não ocorre. |
| Tamanho de arquivos | Serviços/páginas gigantes: `connection_service.py` (108 KB), `transaction_service.py` (77 KB), `report_service.py` (68 KB), `assets.tsx` (125 KB), `transactions.tsx` (94 KB), `account-detail.tsx` (88 KB), `dashboard.tsx` (78 KB), `lib/api.ts` (72 KB). Dificulta revisão e teste. |
| Testes vs. produção | ~~Testes em SQLite~~ **Resolvido: testes em PostgreSQL real**. Antes: testes em SQLite; produção em PostgreSQL + pgvector. Diferenças de collation, índices e tipos não são cobertas. |
| Legado multi-tenant | `workspace_autostamp` deduz `workspace_id` de `user_id` em `before_insert` (risco de gravar no workspace errado quando o chamador esquece de informar). |
| Configuração | ~~Defaults inseguros~~ **Resolvido:** `install.sh` gera segredos, compose exige `${VAR:?}`. S3 implementado (`S3StorageProvider`). `registration_enabled` permanece em revisão. |
| Observabilidade | ~~Só `logging` básico~~ **Resolvido:** logs JSON estruturados, request-id, OpenTelemetry, métricas Prometheus, `/api/ready` (readiness DB+Redis). |
| Idioma/locale | ~~UI inicia em inglês, moeda padrão `USD`~~ **Resolvido na edição Enterprise** (Fase 0, G4): a UI inicia em `pt-BR` (ainda sem seguir o navegador) e a conta nova recebe BRL, DD/MM/YYYY e fuso de São Paulo. Ver [ENTERPRISE](ENTERPRISE.md). |
| Documentação herdada | `frontend/README.md` é o boilerplate do template Vite; `charts/syncrofin/README.md` descreve o frontend como "Next.js" (é Vite/React). |
| Testes frágeis | `relative-time.test.ts` depende do locale da máquina; `register.test.tsx` é instável sob carga. |
| Sessão no cliente | ~~Token JWT em `localStorage`~~ **Resolvido:** access token em memória (15 min), refresh token httpOnly cookie com rotação. |
| Dados de runtime no diretório | ~~`celerybeat-schedule*` em `backend/`~~ **Resolvido:** movido para `/tmp/celerybeat-schedule`. |

> **Atualização 2:** CI/CD (itens 1, 2, 3, 11, 13, 14 e 15 abaixo) foi implementado: `.github/workflows/`, testes em
> **PostgreSQL real**, teste das migrações, `ty`/`ruff` limpos e testes frágeis corrigidos. Falta só **criar a primeira
> tag** para publicar (ver [DEPLOYMENT](DEPLOYMENT.md)). O e-mail de recuperação de senha e convites (E9) também
> está pronto ([FEATURES §7](FEATURES.md)). O escopo de idiomas foi decidido: **`en`, `pt-BR`, `es`**.
>
> **Atualização:** os itens P3 **26–30** foram implementados (ver [FEATURES](FEATURES.md)); o 31 virou
> ferramenta (`npm run i18n:check`) e a decisão de reduzir idiomas segue em aberto. O projeto agora é
> **independente do upstream** (ver §4).

## 2. Backlog priorizado

### P0 — Colocar o projeto de pé como SyncroFin

1. ✅ **Pipeline de CI (GitHub Actions).**
   Rodar em PR/push: `ruff`, `ty`, `check_migration_chain.py`, `pytest -n auto`, `uv lock --check`,
   `npm ci && typecheck && lint && test && build`. Fixar o locale nos testes frágeis antes
   (para o CI ficar verde).
   *Pronto quando:* PR com checks obrigatórios na branch `main`.
2. ✅ **Publicar imagens e chart** (`ghcr.io/gustavoflandal/syncrofin-{backend,frontend}` e
   `charts/syncrofin`) em tag `v*`. Passar `VITE_APP_VERSION` no build do frontend.
   *Pronto quando:* `docker compose -f docker-compose.prod.yml up` e `install.sh` funcionam num host limpo.
3. ⏳ **Primeira release/tag** (crie `v0.17.0` para disparar a publicação) (`v0.16.0-fork.1` ou `v0.17.0`) — necessária para o aviso de
   atualização do frontend e para o `resolveAppVersion` mostrar uma versão útil.
4. **Identidade visual:** logo, favicons e `manifest.json` já trocados; falta refazer os
   screenshots (ainda mostram a UI do Securo).
5. **Corrigir docs herdadas:** `frontend/README.md`, `charts/syncrofin/README.md` (Next.js →
   Vite/React, links para docs inexistentes), `templates/NOTES.txt`, `CONTRIBUTING.md` (o
   upstream tinha; aqui não existe e o README antigo apontava para ele).

### P1 — Segurança e robustez

6. ✅ **Endurecer o compose de produção:** `install.sh` gera todos os segredos; compose de produção
   exige variáveis via `${VAR:?}`. Ver [DEPLOYMENT](DEPLOYMENT.md).
7. ✅ **Falhar na subida com segredos padrão fora de `DEBUG`:** `model_validator` em `core/config.py`
   rejeita `SECRET_KEY` padrão quando `DEBUG=false`.
8. ✅ **Sessão:** access token em memória (15 min), refresh token httpOnly cookie com rotação e
   detecção de replay; CSP e headers de segurança no nginx. Ver [FEATURES §10](FEATURES.md).
9. ✅ **Remover o `print()`** de `core/auth.py:44` (usar `logger`) — hoje loga o id do usuário em
   stdout sem nível.
10. ✅ **Rate limit além do login:** `RateLimiter` Redis sliding-window em import, export, backup e
    agents-chat; configurável por instância.
11. ✅ **Auditoria de dependências** no CI: `pip-audit` (Python), `npm audit` (frontend) e `bandit`
    (SAST Python) no job `audit`.
12. **Aposentar `workspace_autostamp`:** tornar `workspace_id` obrigatório nos serviços/rotas e
    remover o listener; cobrir com testes que falhem quando ausente.

### P1 — Qualidade

13. ✅ **Testes contra PostgreSQL real** no CI (serviço `pgvector/pgvector:pg16`) para um subconjunto
    (migrações `upgrade head`/`downgrade`, collation de payees, busca vetorial). Hoje só SQLite.
14. ✅ **Corrigir testes frágeis** do frontend (fixar `Intl`/locale e `vi.useFakeTimers` em
    `relative-time.test.ts`; aumentar timeout/awaits em `register.test.tsx`).
15. 🔧 **Teste de migração de dados legados** (dump do Securo → SyncroFin): restaurar um dump da
    versão anterior num banco novo e rodar `alembic upgrade head`. (Há um dump real da base antiga, com
    poucos dados, fora do repositório em `D:\Projeto Financeackups\`.)

### P2 — Localização Brasil

16. ✅ **Padrões pt-BR/BRL:** idioma inicial `pt-BR` com detector de navegador, `default_currency`
    `BRL`, DD/MM/YYYY, fuso de São Paulo; categorias e carteira iniciais em português.
17. ✅ **Revisar traduções pt-BR:** termos financeiros revisados; sem referências ao produto
    upstream nos locales; escopo de idiomas decidido: `en`, `pt-BR`, `es`.
18. **Recursos BR de alto valor** (ideias, validar demanda): apoio à declaração de IR a partir do
    livro de operações (ganho de capital, bens e direitos), proventos/dividendos B3, importação de
    NF-e/OFX de bancos BR, PIX/boleto como métodos de pagamento nas faturas, DARF/vencimentos
    tributários como recorrências, integração com CVM/B3 para cotações locais (hoje: yfinance +
    Tesouro Direto).

### P2 — Manutenibilidade

19. **Quebrar arquivos gigantes** (um por vez, com testes existentes como rede de segurança):
    `connection_service.py` → por provider/etapa (contas, transações, faturas, holdings);
    `transaction_service.py` → consulta, mutação, transferências, parcelamentos;
    `assets.tsx`/`transactions.tsx`/`account-detail.tsx`/`dashboard.tsx` → componentes + hooks;
    `lib/api.ts` → módulos por domínio (`api/transactions.ts`, …) com re-export.
20. **Type checking mais rígido:** ampliar o `ty`/`ruff` (regras além de `E4,E7,E9,F`, ex. `B`,
    `UP`, `I`) de forma incremental; `strict` gradual no `tsconfig` do frontend.
21. ✅ **Logging estruturado** (JSON) + correlação por request-id + OpenTelemetry opcional
    (`OTEL_EXPORTER_OTLP_ENDPOINT`); `/api/health` (liveness) e `/api/ready` (readiness DB+Redis);
    métricas Prometheus em `/api/metrics`.
22. ✅ **`celerybeat-schedule`**: movido para `/tmp/celerybeat-schedule` (funciona em containers
    efêmeros).
23. ✅ **S3:** `S3StorageProvider` implementado (`providers/s3_storage.py`, boto3 async, SSE-S3,
    presigned URLs). `registration_enabled` permanece em revisão.
24. **Migração do identificador legado `securo-*`** (formatos de export, `securo-chart`, salt) com
    leitura dupla — só se/quando quiser cortar o vínculo total (ver `docs/ARCHITECTURE.md` §8).
25. **Pre-commit** habilitado por padrão (`prek`/`pre-commit`) + `.editorconfig` +
    `.gitattributes` (adicionado; garante LF em scripts shell).

### P3 — Produto (ideias)

26. ✅ Notificações (e-mail/webhook/push) para orçamentos estourados, faturas a vencer e falhas de sync.
27. ✅ App/PWA instalável (o `manifest.json` é genérico hoje) e modo offline de leitura.
28. ✅ Painel de "saúde financeira" e projeções de fluxo de caixa a partir de recorrências + faturas.
29. ✅ Conciliação bancária mais automática (auto-aplicar sugestões acima de certo score, com
    auditoria em `ReconciliationEvent`).
30. ✅ Compartilhamento com contador (papel `viewer` + exportações prontas para o contador).
31. ✅ Multi-idioma — decidido: `en`, `pt-BR`, `es`: revisar a qualidade das 13 traduções além de `pt-BR` e `en`, ou reduzir o
    escopo mantendo só as que serão mantidas (a cada chave nova, todas precisam de tradução).

## 3. Ordem sugerida das primeiras semanas

1. Itens 1 → 2 → 3 (CI, imagens, primeira tag) — destravam tudo.
2. Itens 6, 7, 9 (segurança barata e de alto retorno).
3. Item 16 (padrões BR) + 4 (identidade visual) — o produto "parece" seu.
4. Itens 13–15 (confiança para mexer no núcleo), depois 19 (refatorações incrementais).

## 4. Independência do upstream

**Decisão (2026-09):** o SyncroFin segue como projeto independente. 
Correções de segurança do upstream **não chegam automaticamente** e precisam ser acompanhadas manualmente quando relevantes (`git remote add upstream …` + `cherry-pick` pontual continua possível).
Consequências: (1) refatorar os arquivos gigantes deixou de ter o custo de merge; (2) a numeração de migrações é só nossa (`093+`); (3) a responsabilidade por vulnerabilidades em código herdado passa a ser nossa — vale ligar `pip-audit`/`npm audit`/Renovate (item 11 e P0).

## 5. Riscos ao evoluir o fork

- **Sem acompanhamento do upstream:** ver §4 — vulnerabilidades do código herdado são nossas.
- **Numeração de migrações:** upstream e fork podem criar `091_*` diferentes; use prefixo/rebase
  cuidadoso e mantenha o `check_migration_chain.py` no CI.
- **Licença AGPL:** qualquer instância pública com modificações precisa oferecer o código-fonte
  (link visível na UI/rodapé é uma forma comum de cumprir).
