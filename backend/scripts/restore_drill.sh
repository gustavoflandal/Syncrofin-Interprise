#!/usr/bin/env bash
# Teste de restauração (E2) — prova que os backups realmente restauram.
#
# Sobe um Postgres TEMPORÁRIO (sem volume persistente, porta aleatória em 127.0.0.1),
# restaura o backup mais recente, roda verificações de sanidade, informa o tempo
# gasto (estimativa de RTO) e a data da última transação recuperada (estimativa de
# RPO) e remove tudo ao final. Nunca toca no banco de produção: os volumes de backup
# são montados somente-leitura.
#
# Uso:
#   backend/scripts/restore_drill.sh                         # backup mais recente
#   backend/scripts/restore_drill.sh --target-time "2026-10-14 09:30:00+00"   # PITR
#   backend/scripts/restore_drill.sh --mode dump             # força o pg_dump diário
#
# Opções:
#   --target-time TS   ponto no tempo (PITR); exige base backup + arquivo de WAL
#   --mode auto|base|dump   origem (padrão: auto = base backup se existir, senão dump)
#   --db NAME          nome do banco (padrão: syncrofin_enterprise)
#   --image IMG        imagem do Postgres (padrão: $DB_IMAGE ou pgvector/pgvector:pg16)
#   --dump-volume V / --base-volume V / --wal-volume V   volumes Docker (detectados se omitidos)
#   --dump-dir D / --base-dir D / --wal-dir D            usar diretórios do host em vez de volumes
#   --keep             não remove o contêiner ao final (depuração)
#   -h, --help
#
# Variáveis: RTO_LIMIT_S (padrão 7200 = 2 h; estourar vira falha).
# Saída: 0 = restaurou e passou nas verificações; != 0 = falhou.
set -euo pipefail

TARGET_TIME=""
MODE="auto"
DB_NAME="syncrofin_enterprise"
IMAGE="${DB_IMAGE:-docker.io/pgvector/pgvector:pg16}"
DUMP_SRC="" BASE_SRC="" WAL_SRC=""
KEEP=0
RTO_LIMIT_S="${RTO_LIMIT_S:-7200}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONTAINER="syncrofin-restore-drill-$$-$RANDOM"
START_TS=$SECONDS

log()  { printf '[restore-drill] %s\n' "$*"; }
fail() { printf '[restore-drill] ERRO: %s\n' "$*" >&2; exit 1; }
usage() { sed -n '2,/^set -euo/p' "${BASH_SOURCE[0]}" | sed '$d;s/^# \{0,1\}//'; }

while [ $# -gt 0 ]; do
  case "$1" in
    --target-time) TARGET_TIME="${2:?}"; shift 2 ;;
    --mode) MODE="${2:?}"; shift 2 ;;
    --db) DB_NAME="${2:?}"; shift 2 ;;
    --image) IMAGE="${2:?}"; shift 2 ;;
    --dump-volume|--dump-dir) DUMP_SRC="${2:?}"; [ "$1" = "--dump-dir" ] && DUMP_SRC="$(cd "$2" && pwd)"; shift 2 ;;
    --base-volume|--base-dir) BASE_SRC="${2:?}"; [ "$1" = "--base-dir" ] && BASE_SRC="$(cd "$2" && pwd)"; shift 2 ;;
    --wal-volume|--wal-dir)   WAL_SRC="${2:?}";  [ "$1" = "--wal-dir" ]  && WAL_SRC="$(cd "$2" && pwd)";  shift 2 ;;
    --keep) KEEP=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) fail "opção desconhecida: $1" ;;
  esac
done

case "$MODE" in auto|base|dump) ;; *) fail "--mode deve ser auto, base ou dump" ;; esac
command -v docker >/dev/null || fail "docker não encontrado"

cleanup() {
  local rc=$?
  if [ "$KEEP" = 1 ]; then
    log "--keep: contêiner $CONTAINER mantido (docker rm -f -v $CONTAINER para remover)"
  else
    docker rm -f -v "$CONTAINER" >/dev/null 2>&1 || true
  fi
  exit $rc
}
trap cleanup EXIT

# Detecta o volume pelo sufixo (o Compose prefixa com o nome do projeto).
find_volume() {
  docker volume ls -q | grep -E "(^|_)$1\$" | head -n1 || true
}
[ -n "$DUMP_SRC" ] || DUMP_SRC="$(find_volume pgbackups)"
[ -n "$BASE_SRC" ] || BASE_SRC="$(find_volume pgbasebackups)"
[ -n "$WAL_SRC" ]  || WAL_SRC="$(find_volume pgwal)"

# Executa um comando shell dentro de um contêiner descartável com as fontes montadas.
probe() {
  local args=()
  [ -n "$DUMP_SRC" ] && args+=(-v "$DUMP_SRC:/src/dumps:ro")
  [ -n "$BASE_SRC" ] && args+=(-v "$BASE_SRC:/src/base:ro")
  [ -n "$WAL_SRC" ]  && args+=(-v "$WAL_SRC:/src/wal:ro")
  docker run --rm --entrypoint bash "${args[@]}" "$IMAGE" -c "$1"
}

LATEST_BASE=""; LATEST_DUMP=""
if [ -n "$BASE_SRC" ]; then
  LATEST_BASE="$(probe 'for d in $(ls -1dt /src/base/base_* 2>/dev/null); do [ -f "$d/base.tar.gz" ] && { basename "$d"; break; }; done' || true)"
fi
if [ -n "$DUMP_SRC" ]; then
  LATEST_DUMP="$(probe 'ls -1t /src/dumps/*.sql.gz 2>/dev/null | head -n1 | xargs -r basename' || true)"
fi
HAS_WAL=0
if [ -n "$WAL_SRC" ] && [ -n "$(probe 'ls -A /src/wal 2>/dev/null | head -n1' || true)" ]; then HAS_WAL=1; fi

if [ "$MODE" = auto ]; then
  if [ -n "$LATEST_BASE" ]; then MODE=base
  elif [ -n "$LATEST_DUMP" ]; then MODE=dump
  else fail "nenhum backup encontrado (base_* em pgbasebackups, *.sql.gz em pgbackups). Ative o profile 'backup'."; fi
fi
if [ "$MODE" = base ]; then
  [ -n "$LATEST_BASE" ] || fail "nenhum base backup encontrado"
  [ "$HAS_WAL" = 1 ] || log "AVISO: arquivo de WAL vazio/ausente; só será possível recuperar até o fim do base backup"
else
  [ -n "$LATEST_DUMP" ] || fail "nenhum dump (*.sql.gz) encontrado"
  [ -z "$TARGET_TIME" ] || fail "--target-time (PITR) exige --mode base com WAL arquivado; dumps não permitem PITR"
fi
log "modo=$MODE base=${LATEST_BASE:-n/a} dump=${LATEST_DUMP:-n/a} wal=$HAS_WAL alvo=${TARGET_TIME:-fim do WAL}"

PSQL_OPTS=(-U postgres -d "$DB_NAME" -tA -v ON_ERROR_STOP=1)
q() { docker exec "$CONTAINER" psql "${PSQL_OPTS[@]}" -c "$1"; }

RPO_NOTE=""
if [ "$MODE" = dump ]; then
  log "subindo Postgres temporário ($IMAGE)"
  docker run -d --name "$CONTAINER" -p 127.0.0.1::5432 \
    -e POSTGRES_PASSWORD=drill -e POSTGRES_DB="$DB_NAME" \
    -v "$DUMP_SRC:/src/dumps:ro" "$IMAGE" >/dev/null
  for _ in $(seq 1 60); do
    # o entrypoint reinicia o servidor após o initdb: exige duas respostas seguidas
    docker exec "$CONTAINER" pg_isready -U postgres -d "$DB_NAME" >/dev/null 2>&1 && \
      sleep 3 && docker exec "$CONTAINER" pg_isready -U postgres -d "$DB_NAME" >/dev/null 2>&1 && break
    sleep 2
  done
  docker exec "$CONTAINER" pg_isready -U postgres -d "$DB_NAME" >/dev/null || fail "Postgres temporário não ficou pronto"
  log "restaurando $LATEST_DUMP"
  # pg_dump em texto puro (db-backup) ou formato custom (PGDMP), ambos comprimidos com gzip.
  docker exec "$CONTAINER" bash -c '
    set -euo pipefail
    f="/src/dumps/'"$LATEST_DUMP"'"
    if [ "$(zcat "$f" | head -c5)" = "PGDMP" ]; then
      zcat "$f" | pg_restore -U postgres -d '"$DB_NAME"' --no-owner --exit-on-error
    else
      zcat "$f" | psql -U postgres -d '"$DB_NAME"' -v ON_ERROR_STOP=1 -q >/dev/null
    fi'
  RPO_NOTE="aproximado: horário do arquivo de dump ($LATEST_DUMP)"
else
  RECOVERY_CONF="restore_command = 'cp /src/wal/%f %p'"$'\n'
  if [ -n "$TARGET_TIME" ]; then
    # 'pause' permite consultar o estado exato no ponto alvo antes de promover.
    RECOVERY_CONF+="recovery_target_time = '$TARGET_TIME'"$'\n'"recovery_target_action = 'pause'"$'\n'
  fi
  log "extraindo $LATEST_BASE e iniciando recuperação (PITR: ${TARGET_TIME:-não})"
  docker run -d --name "$CONTAINER" -p 127.0.0.1::5432 --entrypoint bash \
    -v "$BASE_SRC:/src/base:ro" ${WAL_SRC:+-v "$WAL_SRC:/src/wal:ro"} \
    -e RECOVERY_CONF="$RECOVERY_CONF" -e BASE_DIR="$LATEST_BASE" "$IMAGE" -c '
      set -euo pipefail
      D=/restore/data
      mkdir -p "$D" && cd "$D"
      tar -xzf "/src/base/$BASE_DIR/base.tar.gz"
      [ -f "/src/base/$BASE_DIR/pg_wal.tar.gz" ] && tar -xzf "/src/base/$BASE_DIR/pg_wal.tar.gz" -C "$D/pg_wal"
      printf "%s" "$RECOVERY_CONF" >> postgresql.auto.conf
      # o servidor temporário não deve arquivar WAL nem competir com produção
      printf "archive_mode = off\nlisten_addresses = '"'"'*'"'"'\nhot_standby = on\n" >> postgresql.auto.conf
      touch recovery.signal
      chown -R postgres:postgres /restore && chmod 700 "$D"
      exec gosu postgres postgres -D "$D"' >/dev/null

  log "aguardando a recuperação (replay de WAL)"
  deadline=$((SECONDS + RTO_LIMIT_S))
  while :; do
    [ "$(docker inspect -f '{{.State.Running}}' "$CONTAINER")" = true ] || {
      docker logs --tail 30 "$CONTAINER" >&2; fail "o servidor temporário encerrou durante a recuperação"; }
    st="$(docker exec "$CONTAINER" psql -U postgres -d "$DB_NAME" -tA -c \
      "select case when not pg_is_in_recovery() then 'done' else pg_get_wal_replay_pause_state() end" 2>/dev/null || true)"
    case "$st" in done|paused) break ;; esac
    [ $SECONDS -lt $deadline ] || fail "recuperação excedeu RTO_LIMIT_S=${RTO_LIMIT_S}s"
    sleep 3
  done
  ts="$(docker exec "$CONTAINER" psql -U postgres -d "$DB_NAME" -tA -c "select pg_last_xact_replay_timestamp()" 2>/dev/null || true)"
  [ -n "$ts" ] && RPO_NOTE="última transação reproduzida do WAL: $ts" || RPO_NOTE="sem commits reproduzidos do WAL; estado = fim do base backup"
fi

# ── Verificações de sanidade ────────────────────────────────────────────────
log "verificações de sanidade"
FAILED=0
check_gt() { # nome, SQL, mínimo (exclusivo)
  local n; n="$(q "$2" | tr -d '[:space:]')" || { log "FALHA: $1 (consulta falhou)"; FAILED=1; return; }
  if [ "${n:-0}" -gt "$3" ]; then log "ok: $1 = $n"; else log "FALHA: $1 = ${n:-?} (esperado > $3)"; FAILED=1; fi
}
n="$(q 'select count(*) from alembic_version' | tr -d '[:space:]')" || n=""
if [ "$n" = 1 ]; then log "ok: alembic_version = 1 ($(q 'select version_num from alembic_version'))"
else log "FALHA: alembic_version tem ${n:-?} linhas (esperado exatamente 1)"; FAILED=1; fi
check_gt "users" "select count(*) from users" 0
check_gt "workspaces" "select count(*) from workspaces" 0

CHAIN="$SCRIPT_DIR/check_migration_chain.py"
if [ -f "$CHAIN" ]; then
  PY="$(command -v python3 || command -v python || true)"
  if [ -n "$PY" ]; then
    if (cd "$SCRIPT_DIR/.." && "$PY" scripts/check_migration_chain.py >/dev/null); then log "ok: check_migration_chain.py"
    else log "FALHA: check_migration_chain.py"; FAILED=1; fi
  else log "AVISO: python não encontrado; check_migration_chain.py ignorado"; fi
fi

# ── Relatório ───────────────────────────────────────────────────────────────
ELAPSED=$((SECONDS - START_TS))
log "tempo decorrido (estimativa de RTO, sem rede/provisionamento): ${ELAPSED}s (meta: ${RTO_LIMIT_S}s)"
log "RPO — $RPO_NOTE"
[ "$ELAPSED" -le "$RTO_LIMIT_S" ] || { log "FALHA: RTO acima do limite"; FAILED=1; }
if [ "$FAILED" != 0 ]; then fail "exercício de restauração reprovado"; fi
log "exercício de restauração APROVADO"
