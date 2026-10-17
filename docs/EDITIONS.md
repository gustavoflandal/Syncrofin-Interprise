# Edições: Community e Enterprise

Este repositório (**SyncroFin-Interprise**, "Enterprise") nasceu do
[SyncroFin](https://github.com/gustavoflandal/SyncroFin) ("Community") na versão **v0.17.0** e passa a ser onde
se desenvolve tudo o que o [plano empresarial](ENTERPRISE.md) pede.

| | **Community** (`SyncroFin`) | **Enterprise** (este repositório) |
|---|---|---|
| Público | Uso pessoal e pequenas empresas | Empresas: auditoria, permissões granulares, sessões seguras, LGPD, fiscal, integrações |
| Ritmo | Só **correções** de bugs e de segurança | Funcionalidades novas (Fases 0 a 6 do plano) |
| Licença | AGPL-3.0 | AGPL-3.0 (deriva de código AGPL; ver abaixo) |
| Ponto de partida | v0.17.0 é a última versão com funcionalidades novas | Este repositório, a partir da v0.17.0 |

## Regra de ouro: as correções andam num sentido só

**Community → Enterprise. Nunca o contrário.**

```bash
git remote add community https://github.com/gustavoflandal/SyncroFin.git   # uma vez
git fetch community
git merge community/main          # traz correções e resolve conflitos aqui
```

- Uma correção de bug ou de segurança é feita **primeiro na Community**, publicada lá (tag `v0.17.x`) e só então
  trazida para cá com `git merge`. Assim o histórico das duas continua compatível.
- Funcionalidade nova **não** volta para a Community. Se um dia uma peça do Enterprise fizer sentido para todos,
  decide-se caso a caso e ela é reescrita como um PR na Community.
- Se um conserto só se aplica ao Enterprise (código que só existe aqui), fica só aqui.
- Faça o merge com frequência (a cada correção publicada): conflitos pequenos e frequentes custam menos que um
  grande de vez em quando.

## Cadeia de migrações do banco

O Enterprise **continua a numeração da Community** (parte da migração `092`). Quem usa a Community consegue
**subir** para o Enterprise (as migrações novas são aplicadas por cima). O caminho de volta **não existe**: as
migrações do Enterprise podem criar tabelas e colunas que a Community não conhece.

Se a Community precisar de uma migração nova (correção que mexe no banco), ela usa o **próximo número** e o Enterprise
renumera as suas ao fazer o merge (`scripts/check_migration_chain.py`, que roda no CI, acusa cadeia quebrada).

## Onde colocar o código do Enterprise

Para o merge continuar limpo, prefira **arquivos e módulos novos** a editar arquivos herdados:

- Auditoria, RBAC, sessões, LGPD → módulos próprios (`services/audit_*`, `api/audit.py`, `services/rbac_*`…).
- Quando for preciso mexer num arquivo herdado (por exemplo, `core/auth.py`), faça a mudança **pequena e isolada**,
  para o conflito de merge ser fácil de resolver.
- Não reformate nem reorganize arquivos herdados "de passagem": isso vira conflito em todo merge.

## Identidade, imagens e publicação

- Os identificadores persistidos `securo-*` **não** são renomeados (ver [ARCHITECTURE §8](ARCHITECTURE.md)).
- ✅ **Nomes próprios (feito na Fase 0):** as imagens são `ghcr.io/<dono>/syncrofin-enterprise-backend` e `…-frontend`, e o chart
  Helm vai para `oci://ghcr.io/<dono>/charts-enterprise`. A Community publica em `syncrofin-backend`/`-frontend` e `charts`;
  como o mesmo dono publica as duas, um nome igual faria uma sobrescrever a outra. **Se você mudar estes nomes, mude nos dois
  lados.** Os pacotes são **privados** e devem continuar assim (repositório privado); o acesso é por `docker login ghcr.io` ou
  `imagePullSecrets`.
- Nome de exibição do produto ("SyncroFin Enterprise") ainda não foi trocado na interface: decisão pendente.

## Licença e o que ela permite

O código herdado do Securo é AGPL-3.0 de terceiros, e o Enterprise o contém: **continua AGPL-3.0**, com `LICENSE` e
créditos preservados.

- Uso **interno** (você ou sua organização, em servidor próprio): sem obrigação de publicar nada.
- Oferecer o sistema a **terceiros pela rede** (SaaS ou instalação para clientes que o usam): esses usuários têm
  direito ao **código-fonte da versão que usam**, incluindo as modificações. Não dá para vender uma versão fechada.
- O que se pode cobrar: implantação, suporte, customização, treinamento e hospedagem.
- Isto não é aconselhamento jurídico: confirme com um advogado antes de comercializar.

## Infraestrutura separada

Community e Enterprise não compartilham **nada** no Docker: projeto do Compose, banco, volumes, portas e imagens têm
nomes próprios (tabela em [DEPLOYMENT](DEPLOYMENT.md#infraestrutura-docker-própria-e-como-mudar-de-uma-instalação-antiga)).
Consequência prática: as duas rodam lado a lado na mesma máquina, cada uma com os seus dados.

Por isso estes arquivos **divergem de propósito** entre os repositórios, e num `git merge community/main` vale a versão
do Enterprise: `docker-compose*.yml`, `install.sh`, `.env.example`, `backend/tests/conftest.py` (porta do banco de
testes), `frontend/vite.config.ts` (porta padrão da API), `scripts/migrate-docker-project.sh` e as portas citadas em
`README.md`, `CLAUDE.md`, `CONTRIBUTING.md` e `docs/`.

## Nome do produto

O projeto se chamava *FinanceBR* até 2026-09-20. Como esse nome já tem proprietário, tudo passou a se chamar
**SyncroFin**: repositórios `SyncroFin` (Community) e `SyncroFin-Interprise` (Enterprise), imagens
`syncrofin-*`/`syncrofin-enterprise-*`, chart `charts/syncrofin`, banco `syncrofin`, aplicativo Android
`br.com.syncrofin.mobile`. Quem já tinha uma instalação de desenvolvimento precisa migrar o banco (ver DEPLOYMENT).

## Decisões em aberto (ver [ENTERPRISE §5](ENTERPRISE.md))

- Nome de exibição da edição Enterprise (o repositório se chama `SyncroFin-Interprise`, mantendo a grafia original).
