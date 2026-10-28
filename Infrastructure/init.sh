#!/usr/bin/env bash
# Este script esta pensado para las personas que quieran simplemente correr la infraestructura de Wardriving sin tener que preocuparse por la configuración de PostgreSQL y Grafana, carga directamente un dump existente y levanta todo lo necesario.

set -Eeuo pipefail

# Rutas del proyecto
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="$ROOT_DIR/docker-compose.yaml"
DUMP_FILE="$ROOT_DIR/DB/db.dump"

CONTAINER="wardriving_postgres"
DB_NAME="wardriving"
DB_USER="postgres"
MARKER="/var/lib/postgresql/data/.wardriving_restored"

cd "$ROOT_DIR"

echo "=== Inicializando infraestructura Wardriving ==="

# 1. Verificar el dump
if [[ ! -f "$DUMP_FILE" ]]; then
    echo "ERROR: No existe $DUMP_FILE"
    exit 1
fi

# 2. Levantar PostgreSQL
echo "[1/4] Iniciando PostgreSQL..."
docker compose -f "$COMPOSE_FILE" up -d postgres

# 3. Esperar a que PostgreSQL esté listo
echo "[2/4] Esperando PostgreSQL..."

READY=false
for i in {1..60}; do
    if docker exec "$CONTAINER" \
        pg_isready -U "$DB_USER" -d "$DB_NAME" \
        >/dev/null 2>&1; then
        READY=true
        break
    fi
    sleep 2
done

if [[ "$READY" != true ]]; then
    echo "ERROR: PostgreSQL no respondió."
    exit 1
fi

# 4. Restaurar una sola vez
if docker exec "$CONTAINER" test -f "$MARKER"; then
    echo "[3/4] Base de datos ya restaurada. Omitiendo."
else
    echo "[3/4] Verificando y restaurando dump..."

    # Comprobar compatibilidad con pg_restore del contenedor
    docker exec -i "$CONTAINER" \
        pg_restore -l < "$DUMP_FILE" > /dev/null

    docker exec -i "$CONTAINER" \
        pg_restore \
        -U "$DB_USER" \
        -d "$DB_NAME" \
        --clean \
        --if-exists \
        --no-owner \
        --no-acl \
        --exit-on-error \
        -v < "$DUMP_FILE"

    # Marcar restauración exitosa en el volumen persistente
    docker exec "$CONTAINER" touch "$MARKER"

    echo "Restauración completada."
fi

# 5. Levantar el resto de servicios
echo "[4/4] Iniciando Grafana..."
docker compose -f "$COMPOSE_FILE" up -d

echo ""
echo "=== Infraestructura inicializada ==="
docker compose -f "$COMPOSE_FILE" ps

# 6. Enlace directo a Grafana
GRAFANA_URL="http://localhost:3000"

ESC=$'\033'
RESET="${ESC}[0m"
BOLD="${ESC}[1m"
NARANJA="${ESC}[38;5;208m"
GRIS="${ESC}[38;5;245m"

# Hipervínculo OSC 8: hace el texto clickeable en terminales compatibles
LINK_OPEN="${ESC}]8;;${GRAFANA_URL}${ESC}\\"
LINK_CLOSE="${ESC}]8;;${ESC}\\"

echo ""
echo "${BOLD}${NARANJA}>> Abre Grafana aquí:${RESET} ${NARANJA}${LINK_OPEN}${BOLD}${GRAFANA_URL}${RESET}${NARANJA}${LINK_CLOSE}${RESET}"
echo "${GRIS}   Si aún no carga, dale unos segundos para que Grafana termine de levantarse.${RESET}"
echo "${GRIS}   Si tu terminal no lo abre con un clic, usa Ctrl + clic (o copia el enlace).${RESET}"
echo ""
