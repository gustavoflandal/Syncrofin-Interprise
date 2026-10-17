#!/usr/bin/env bash
# Moves the data of an older Docker Compose project into this edition's own project.
#
#   scripts/migrate-docker-project.sh <old-project> [old-database] [compose-file]
#
# The Enterprise edition runs as the Compose project `syncrofin-enterprise`, with the database
# `syncrofin_enterprise` and its own volumes, so it can live next to the Community edition. An
# installation made earlier (project `financebr`, or `syncrofin`, database of the same name) keeps
# its data in volumes named after the old project. This copies them over and renames the database.
#
#   scripts/migrate-docker-project.sh financebr
#   scripts/migrate-docker-project.sh syncrofin syncrofin docker-compose.prod.yml
#
# Nothing is deleted: the old volumes stay until you remove them (the last lines say how).
# Stop and read before running it on a server that matters; take a backup first.
set -euo pipefail
export MSYS_NO_PATHCONV=1   # Git Bash on Windows would rewrite the /paths given to docker

OLD_PROJECT="${1:?usage: $0 <old-project> [old-database] [compose-file]}"
OLD_DB="${2:-$OLD_PROJECT}"
COMPOSE_FILE="${3:-docker-compose.yml}"
NEW_PROJECT="syncrofin-enterprise"
NEW_DB="syncrofin_enterprise"
COMPOSE=(docker compose -f "$COMPOSE_FILE")

if [ "$OLD_PROJECT" = "$NEW_PROJECT" ]; then
  echo "The old project is already $NEW_PROJECT: nothing to do." >&2
  exit 1
fi
[ -f "$COMPOSE_FILE" ] || { echo "No $COMPOSE_FILE here: run this from the repository root." >&2; exit 1; }

mapfile -t OLD_VOLUMES < <(docker volume ls -q --filter "name=^${OLD_PROJECT}_")
if [ "${#OLD_VOLUMES[@]}" -eq 0 ]; then
  echo "No volumes named ${OLD_PROJECT}_* were found: is $OLD_PROJECT the right project name?" >&2
  echo "(docker volume ls  shows them)" >&2
  exit 1
fi
for old in "${OLD_VOLUMES[@]}"; do
  new="${NEW_PROJECT}_${old#"${OLD_PROJECT}_"}"
  if docker volume inspect "$new" > /dev/null 2>&1; then
    echo "The volume $new already exists: the new project has data of its own. Remove it first if it is empty." >&2
    exit 1
  fi
done

echo "Moving  project $OLD_PROJECT (database $OLD_DB)  ->  project $NEW_PROJECT (database $NEW_DB)"
echo "Volumes: ${OLD_VOLUMES[*]}"

echo "1/5 stopping the old containers (their volumes stay)"
"${COMPOSE[@]}" -p "$OLD_PROJECT" down

echo "2/5 copying the volumes"
for old in "${OLD_VOLUMES[@]}"; do
  new="${NEW_PROJECT}_${old#"${OLD_PROJECT}_"}"
  docker volume create "$new" > /dev/null
  docker run --rm -v "$old":/from:ro -v "$new":/to alpine sh -c 'cp -a /from/. /to/'
  echo "    $old -> $new"
done

echo "3/5 starting the database of the new project"
"${COMPOSE[@]}" up -d db
for _ in $(seq 1 60); do
  "${COMPOSE[@]}" exec -T db pg_isready -U postgres > /dev/null 2>&1 && break
  sleep 2
done

echo "4/5 renaming the database $OLD_DB -> $NEW_DB"
have_old=$("${COMPOSE[@]}" exec -T db psql -U postgres -d postgres -Atc "select 1 from pg_database where datname='${OLD_DB}'" || true)
have_new=$("${COMPOSE[@]}" exec -T db psql -U postgres -d postgres -Atc "select 1 from pg_database where datname='${NEW_DB}'" || true)
if [ "$have_old" = "1" ] && [ "$have_new" != "1" ]; then
  "${COMPOSE[@]}" exec -T db psql -U postgres -d postgres -c "ALTER DATABASE \"${OLD_DB}\" RENAME TO \"${NEW_DB}\";"
elif [ "$have_new" = "1" ]; then
  echo "    $NEW_DB already exists: leaving it"
else
  echo "    no database named $OLD_DB in the volume: the application will create $NEW_DB empty" >&2
fi

echo "5/5 starting everything (building the images)"
"${COMPOSE[@]}" up -d --build

echo
echo "Done. The old volumes were kept. When you have checked the new stack, remove them with:"
echo "  docker volume rm ${OLD_VOLUMES[*]}"
