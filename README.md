# WiFI-Vulnerabilitys — Wardriving y análisis de redes WiFi

Repositorio del proyecto de tesis para **capturar, procesar, almacenar y visualizar** información de redes WiFi
obtenida mediante *wardriving* sobre una Raspberry Pi con GPS y pantalla táctil.

El sistema completo se compone de cuatro piezas:

1. **Captura** en una Raspberry Pi con Kismet, GPS y una interfaz táctil.
2. **ETL** en Python que limpia la captura de Kismet y la carga en PostgreSQL.
3. **Base de datos** PostgreSQL con el esquema `wardriving`.
4. **Visualización** en Grafana mediante un dashboard aprovisionado automáticamente.

---

## Índice

- [Arquitectura](#arquitectura)
- [Estructura del repositorio](#estructura-del-repositorio)
- [Requisitos](#requisitos)
- [Inicio rápido](#inicio-rápido)
- [¿Qué hace `init.sh` paso a paso?](#qué-hace-initsh-paso-a-paso)
- [Docker Compose en detalle](#docker-compose-en-detalle)
- [Base de datos: esquema y dump](#base-de-datos-esquema-y-dump)
- [Grafana: dashboard y filtros](#grafana-dashboard-y-filtros)
- [ETL: de Kismet a PostgreSQL](#etl-de-kismet-a-postgresql)
- [Raspberry Pi: captura y pantalla táctil](#raspberry-pi-captura-y-pantalla-táctil)
- [Flujo de trabajo completo](#flujo-de-trabajo-completo)
- [Comandos de referencia](#comandos-de-referencia)
- [Solución de problemas](#solución-de-problemas)
- [Seguridad, privacidad y ética](#seguridad-privacidad-y-ética)

---

## Arquitectura

```mermaid
flowchart LR
    subgraph RPI["Raspberry Pi (campo)"]
        GPS[GPS / gpsd] --> K[Kismet]
        WIFI[Adaptador WiFi en modo monitor] --> K
        LCD[Pantalla táctil 480x320] --> UI[script.py]
        UI --> K
        UI --> HTTP[Servidor HTTP :8000]
        K --> CAP[(Captura .kismet)]
        CAP --> HTTP
    end

    HTTP -->|descarga por red local| ETL[ETL Python]
    ETL -->|INSERT / UPSERT| PG[(PostgreSQL :5432)]
    PG --> G[Grafana :3000]
    G --> USER[Navegador]
```

| Componente | Tecnología | Puerto |
|---|---|---|
| Base de datos | PostgreSQL 16 | `5432` |
| Visualización | Grafana | `3000` |
| Captura | Kismet (Raspberry Pi) | — |
| Descarga de capturas | `python -m http.server` | `8000` |
| ETL | Python 3 + psycopg2 | — |

---

## Estructura del repositorio

```text
Repo_tesis/
├── Documentation/
│   └── imgs/                     # Capturas de pantalla del dashboard
│       ├── dashboard.png
│       ├── estadisticas.png
│       ├── filtros.png
│       └── filtros_aplicados.png
├── Infrastructure/
│   ├── DB/
│   │   ├── db.dump               # Dump PostgreSQL con datos ya procesados
│   │   └── schema.sql            # Esquema de la base de datos
│   ├── ETL/
│   │   ├── main.py               # Script de extracción, limpieza y carga
│   │   └── requirements.txt      # Dependencias de Python
│   ├── Grafana/
│   │   ├── dashboard.json        # Dashboard "Metricas"
│   │   ├── dashboard.yaml        # Aprovisionamiento de dashboards
│   │   └── datasources.yaml      # Aprovisionamiento de la fuente PostgreSQL
│   ├── docker-compose.yaml       # PostgreSQL + Grafana
│   └── init.sh                   # Arranque y restauración automática
├── RPI_scripts/
│   ├── script.py                 # Interfaz táctil + control de Kismet
│   └── lcd_test.py               # Prueba de pantalla y calibración táctil
├── .gitignore
└── README.md
```

> Las carpetas `venv/` y los directorios de datos locales están excluidos por `.gitignore`.

---

## Requisitos

### Para levantar la infraestructura

- **Docker Engine** 20.10 o superior.
- **Docker Compose v2** (el comando es `docker compose`, no `docker-compose`).
- Al menos **1 GB de espacio libre** y **512 MB de RAM** disponibles.
- Puertos **3000** y **5432** libres en la máquina.
- `bash`, `pg_restore` (opcional en el host, se usa dentro del contenedor).

Verificación:

```bash
docker --version
docker compose version
```

### Para ejecutar el ETL

- Python **3.9+**
- `pip` y `venv`
- Acceso al puerto `5432` de PostgreSQL

### Para la Raspberry Pi

- Raspberry Pi con Raspberry Pi OS.
- Adaptador WiFi compatible con **modo monitor**.
- GPS conectado y reconocido por `gpsd`.
- Pantalla TFT SPI de **480×320** y táctil resistivo.
- Paquetes: `kismet`, `gpsd`, `gpsd-clients`, `aircrack-ng`, `macchanger`, `iw`, `python3-pygame`.

---

## Inicio rápido

Todo el entorno se levanta con un solo comando:

```bash
cd Infrastructure
bash init.sh
```

Cuando termine, abre:

```text
http://localhost:3000
```

Grafana entra directamente al dashboard **Metricas** sin pedir usuario ni contraseña
(acceso anónimo configurado como *Viewer*).

Para comprobar el estado:

```bash
cd Infrastructure
docker compose ps
```

Deberías ver dos contenedores en estado `running`:

```text
NAME                   SERVICE    STATUS
wardriving_postgres    postgres   Up
wardriving_grafana     grafana    Up
```

### Detener el entorno

```bash
cd Infrastructure
docker compose down
```

Los datos se conservan en los volúmenes `postgres_data` y `grafana_data`.

### Borrar todo y empezar de cero

```bash
cd Infrastructure
docker compose down -v
bash init.sh
```

> `down -v` elimina los volúmenes. En el siguiente arranque, PostgreSQL vuelve a ejecutar
> `schema.sql` y `init.sh` restaura el dump desde cero.

---

## ¿Qué hace `init.sh` paso a paso?

`init.sh` es el punto de entrada pensado para quien solo quiere **ver la información y
explorar los datos** sin configurar PostgreSQL ni Grafana manualmente.

Se ejecuta con `bash`:

```bash
cd Infrastructure
bash init.sh
```

> El archivo es ejecutable, pero su *shebang* (`#!/usr/bin/env bash`) no está en la primera
> línea, sino después de un comentario. Por eso conviene invocarlo explícitamente con `bash`.
> Si intentas `./init.sh` y obtienes `Exec format error`, usa `bash init.sh`.

### Paso 0 — Preparación

```bash
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
```

Calcula la ruta absoluta de `Infrastructure/`, sin importar desde qué directorio se ejecute.
Luego define:

| Variable | Valor |
|---|---|
| `COMPOSE_FILE` | `Infrastructure/docker-compose.yaml` |
| `DUMP_FILE` | `Infrastructure/DB/db.dump` |
| `CONTAINER` | `wardriving_postgres` |
| `DB_NAME` | `wardriving` |
| `DB_USER` | `postgres` |
| `MARKER` | `/var/lib/postgresql/data/.wardriving_restored` |

El script usa `set -Eeuo pipefail`: se detiene ante cualquier error, variable no definida o
fallo dentro de una tubería.

### Paso 1 — Verificar que exista el dump

```bash
if [[ ! -f "$DUMP_FILE" ]]; then
    echo "ERROR: No existe $DUMP_FILE"
    exit 1
fi
```

Si `DB/db.dump` no está, el script termina sin tocar nada. Así se evita levantar una base
vacía por accidente.

### Paso 2 — Levantar solo PostgreSQL

```bash
docker compose -f "$COMPOSE_FILE" up -d postgres
```

Arranca únicamente el servicio `postgres` en segundo plano. Grafana **todavía no se levanta**,
porque necesita que la base esté lista y restaurada.

En este primer arranque, si el volumen está vacío, PostgreSQL ejecuta automáticamente
`DB/schema.sql` gracias al montaje en `/docker-entrypoint-initdb.d/`.

### Paso 3 — Esperar a que PostgreSQL responda

```bash
pg_isready -U postgres -d wardriving
```

El script hace hasta **60 intentos**, con **2 segundos** de espera entre cada uno
(120 segundos como máximo). Si el contenedor no responde, aborta con error.

Esto es más fiable que un simple `sleep`, porque comprueba que el servidor acepta conexiones.

### Paso 4 — Restaurar el dump una sola vez

El script comprueba si existe un archivo marcador dentro del volumen de datos:

```bash
docker exec "$CONTAINER" test -f "/var/lib/postgresql/data/.wardriving_restored"
```

- Si **existe**, imprime `[3/4] Base de datos ya restaurada. Omitiendo.` y continúa.
- Si **no existe**, restaura el dump.

Antes de restaurar valida que el archivo sea legible:

```bash
docker exec -i "$CONTAINER" pg_restore -l < "$DUMP_FILE" > /dev/null
```

Y después ejecuta la restauración real:

```bash
docker exec -i "$CONTAINER" pg_restore \
    -U postgres \
    -d wardriving \
    --clean \
    --if-exists \
    --no-owner \
    --no-acl \
    --exit-on-error \
    -v < "$DUMP_FILE"
```

| Opción | Para qué sirve |
|---|---|
| `--clean` | Elimina los objetos existentes antes de crearlos |
| `--if-exists` | Evita errores si el objeto a borrar no existe |
| `--no-owner` | No intenta asignar el propietario original del dump |
| `--no-acl` | No restaura permisos/ACL originales |
| `--exit-on-error` | Aborta al primer error real |
| `-v` | Muestra el progreso detallado |

Al terminar correctamente crea el marcador:

```bash
docker exec "$CONTAINER" touch "$MARKER"
```

Ese archivo vive **dentro del volumen** (`postgres_data`), no en el repositorio. Por eso la
restauración es idempotente: puedes ejecutar `init.sh` muchas veces y no volverá a cargar el
dump.

### Paso 5 — Levantar Grafana y el resto

```bash
docker compose -f "$COMPOSE_FILE" up -d
```

Levanta Grafana, que espera a PostgreSQL mediante `depends_on`. Al arrancar, Grafana lee los
archivos de aprovisionamiento y deja el datasource y el dashboard listos.

Finalmente muestra el estado:

```bash
docker compose -f "$COMPOSE_FILE" ps
```

### ¿Cómo vuelvo a restaurar el dump?

Elimina el marcador y vuelve a ejecutar el script:

```bash
docker compose -f Infrastructure/docker-compose.yaml exec postgres \
    rm -f /var/lib/postgresql/data/.wardriving_restored

bash Infrastructure/init.sh
```

O, más limpio, recrea el volumen:

```bash
cd Infrastructure
docker compose down -v
bash init.sh
```

---

## Docker Compose en detalle

Archivo: `Infrastructure/docker-compose.yaml`

```yaml
services:
  postgres:
    image: postgres:16
    container_name: wardriving_postgres
    environment:
      POSTGRES_DB: wardriving
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-postgres}
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./DB/schema.sql:/docker-entrypoint-initdb.d/schema.sql:ro
    networks:
      - wardriving-net

  grafana:
    image: grafana/grafana:latest
    ...
```

### Servicio `postgres`

| Elemento | Detalle |
|---|---|
| Imagen | `postgres:16` |
| Contenedor | `wardriving_postgres` |
| Base de datos | `wardriving` |
| Usuario | `postgres` |
| Contraseña | `postgres` por defecto, configurable con `POSTGRES_PASSWORD` |
| Puerto | `5432:5432` (host:contenedor) |
| Volumen | `postgres_data` → `/var/lib/postgresql/data` |
| Inicialización | `DB/schema.sql` → `/docker-entrypoint-initdb.d/schema.sql` |

El montaje de `schema.sql` se ejecuta **solo cuando el volumen está vacío**, es decir, la
primera vez que se crea la base. Si el volumen ya existe, el archivo se ignora.

### Servicio `grafana`

| Elemento | Detalle |
|---|---|
| Imagen | `grafana/grafana:latest` |
| Contenedor | `wardriving_grafana` |
| Puerto | `3000:3000` |
| Usuario admin | `admin` por defecto (`GRAFANA_ADMIN_USER`) |
| Contraseña admin | `admin` por defecto (`GRAFANA_ADMIN_PASSWORD`) |
| Acceso anónimo | Habilitado como `Viewer` |
| Formulario de login | Deshabilitado |
| Página de inicio | `/d/adwktd6/metricas` |

Variables de entorno relevantes:

```yaml
GF_AUTH_ANONYMOUS_ENABLED: "true"
GF_AUTH_ANONYMOUS_ORG_ROLE: Viewer
GF_AUTH_DISABLE_LOGIN_FORM: "true"
GF_USERS_HOME_PAGE: /d/adwktd6/metricas
```

- **Acceso anónimo**: cualquiera que abra `http://localhost:3000` puede ver el dashboard.
- **Login deshabilitado**: no aparece el formulario de inicio de sesión. Para editar el
  dashboard desde la UI hay que habilitar el login o cambiar el rol anónimo.
- **Página de inicio**: va directo al dashboard `Metricas`.

### Volúmenes

```yaml
volumes:
  postgres_data:
  grafana_data:
```

- `postgres_data`: datos de PostgreSQL, el marcador de restauración y la base completa.
- `grafana_data`: estado interno de Grafana (usuarios, preferencias, etc.).

### Red

```yaml
networks:
  wardriving-net:
```

Red interna tipo *bridge*. Grafana se conecta a PostgreSQL usando el nombre del servicio
como hostname: `postgres:5432`. Por eso `datasources.yaml` usa `url: postgres:5432` y no
`localhost`.

### Configuración con `.env` (opcional)

Puedes crear `Infrastructure/.env`:

```dotenv
POSTGRES_PASSWORD=postgres
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=admin
```

> **Importante:** si cambias `POSTGRES_PASSWORD`, también debes actualizar la contraseña en
> `Infrastructure/Grafana/datasources.yaml` (`secureJsonData.password`) y en
> `Infrastructure/ETL/main.py` (`DATABASE_URL`). Los tres deben coincidir.

### `depends_on`

```yaml
depends_on:
  - postgres
```

Grafana espera a que el contenedor de PostgreSQL **exista y arranque**, pero no garantiza que
la base esté lista para aceptar conexiones. Por eso `init.sh` arranca PostgreSQL primero,
espera con `pg_isready` y solo después levanta Grafana. Si arrancas todo con
`docker compose up -d` sin `init.sh`, puede que Grafana tarde unos segundos en conectar.

---

## Base de datos: esquema y dump

### `DB/schema.sql`

Crea el esquema `wardriving` y dos tablas.

#### `wardriving.wardriving_session`

Registra cada captura procesada.

| Columna | Tipo | Descripción |
|---|---|---|
| `session_id` | `BIGSERIAL` | PK autogenerada |
| `name` | `TEXT NOT NULL` | Nombre del archivo de captura |
| `started_at` | `TIMESTAMP NOT NULL` | Primera observación de la sesión |
| `ended_at` | `TIMESTAMP` | Última observación |
| `notes` | `TEXT` | Notas libres |
| `created_at` | `TIMESTAMP` | Fecha de creación, por defecto `NOW()` |

#### `wardriving.wifi_network`

Almacena una fila por red (BSSID único).

| Columna | Tipo | Descripción |
|---|---|---|
| `wifi_id` | `BIGSERIAL` | PK autogenerada |
| `session_id` | `BIGINT` | FK a `wardriving_session` (`ON DELETE SET NULL`) |
| `ssid` | `TEXT` | Nombre de la red (el ETL lo deja en `NULL` por privacidad) |
| `bssid` | `TEXT UNIQUE NOT NULL` | Identificador de la red (MAC del AP) |
| `manufacturer` | `TEXT` | Fabricante inferido por Kismet |
| `channel` | `INTEGER` | Canal WiFi |
| `frequency_khz` | `INTEGER` | Frecuencia en kHz |
| `encryption` | `TEXT` | Tipo de cifrado reportado |
| `signal_dbm` | `INTEGER` | Mejor señal observada (dBm) |
| `lat` | `DOUBLE PRECISION` | Latitud de la mejor observación |
| `lon` | `DOUBLE PRECISION` | Longitud de la mejor observación |
| `first_seen` | `TIMESTAMP` | Primera detección |
| `last_seen` | `TIMESTAMP` | Última detección |
| `wps_state` | `INTEGER` | `1` = WPS activado, `0` = no |
| `created_at` | `TIMESTAMP` | Creación de la fila |
| `updated_at` | `TIMESTAMP` | Última actualización |

Índices creados:

```sql
CREATE INDEX idx_wifi_geo       ON wifi_network(lat, lon);
CREATE INDEX idx_wifi_wps       ON wifi_network(wps_state);
CREATE INDEX idx_wifi_last_seen ON wifi_network(last_seen);
CREATE INDEX idx_wifi_session   ON wifi_network(session_id);
```

- `idx_wifi_geo`: acelera las consultas geográficas del mapa.
- `idx_wifi_wps`: acelera el filtro por WPS.
- `idx_wifi_last_seen`: acelera ordenamientos por última detección.
- `idx_wifi_session`: acelera la relación con sesiones.

### `DB/db.dump`

Dump en formato **custom** de PostgreSQL (`pg_dump -Fc`), comprimido con gzip.

| Dato | Valor |
|---|---|
| Base de origen | `wardriving` |
| Versión de PostgreSQL | 16.14 |
| Formato | Custom (`CUSTOM`) |
| Contenido | Esquema `wardriving`, tablas, secuencias, índices, constraints y datos |
| Redes almacenadas | 1 557 |
| Sesiones almacenadas | 1 |

El dump **ya contiene los datos procesados**, por lo que no necesitas ejecutar el ETL para
ver el dashboard.

Para inspeccionar su contenido sin restaurarlo:

```bash
# En el host (requiere cliente de PostgreSQL)
pg_restore -l Infrastructure/DB/db.dump | less

# O dentro del contenedor
cd Infrastructure
docker compose exec -T postgres pg_restore -l < DB/db.dump
```

La salida muestra las entradas del archivo: `SCHEMA`, `TABLE`, `SEQUENCE`, `TABLE DATA`,
`INDEX`, `CONSTRAINT`, etc. Es útil para comprobar que el dump corresponde a la versión de
PostgreSQL del contenedor.

### Restauración manual (sin `init.sh`)

```bash
cd Infrastructure
docker compose up -d postgres
docker compose exec -T postgres pg_restore \
    -U postgres \
    -d wardriving \
    --clean --if-exists --no-owner --no-acl --exit-on-error -v \
    < DB/db.dump
docker compose up -d
```

### Conectarse a la base

```bash
cd Infrastructure
docker compose exec postgres psql -U postgres -d wardriving
```

O desde el host, si tienes `psql`:

```bash
psql "postgresql://postgres:postgres@localhost:5432/wardriving"
```

Dentro de `psql`:

```sql
SET search_path TO wardriving;

\dt                 -- listar tablas
\d wifi_network     -- describir la tabla
SELECT count(*) FROM wifi_network;
```

### Consultas de ejemplo

```sql
SET search_path TO wardriving;

-- Total de redes
SELECT count(*) AS total FROM wifi_network;

-- Redes con WPS activado / desactivado
SELECT
    count(*) FILTER (WHERE wps_state = 1) AS wps_activado,
    count(*) FILTER (WHERE wps_state = 0) AS wps_desactivado
FROM wifi_network;

-- Distribución por tipo de cifrado
SELECT
    CASE
        WHEN encryption ILIKE '%WPA3%' THEN 'WPA3'
        WHEN encryption ILIKE '%WPA2%' THEN 'WPA2'
        WHEN encryption ILIKE '%WPA%'  THEN 'WPA'
        WHEN encryption ILIKE '%WEP%'  THEN 'WEP'
        WHEN encryption IS NULL OR trim(encryption) = '' THEN 'Open'
        ELSE 'Otro'
    END AS cifrado,
    count(*) AS total
FROM wifi_network
GROUP BY 1
ORDER BY total DESC;

-- Top 10 fabricantes
SELECT manufacturer, count(*) AS total
FROM wifi_network
GROUP BY manufacturer
ORDER BY total DESC
LIMIT 10;

-- Señal promedio y rango
SELECT
    round(avg(signal_dbm)) AS promedio_dbm,
    min(signal_dbm) AS mejor,
    max(signal_dbm) AS peor
FROM wifi_network
WHERE signal_dbm IS NOT NULL;
```

> Evita publicar consultas que devuelvan `bssid`, `lat` y `lon` en conjunto: son datos
> sensibles que permiten geolocalizar redes concretas.

---

## Grafana: dashboard y filtros

Grafana se aprovisiona automáticamente con tres archivos:

| Archivo | Montaje en el contenedor | Función |
|---|---|---|
| `Grafana/datasources.yaml` | `/etc/grafana/provisioning/datasources/datasources.yaml` | Fuente de datos PostgreSQL |
| `Grafana/dashboard.yaml` | `/etc/grafana/provisioning/dashboards/dashboard.yaml` | Proveedor de dashboards desde archivos |
| `Grafana/dashboard.json` | `/var/lib/grafana/dashboards/dashboard.json` | Dashboard **Metricas** |

### Fuente de datos

`Grafana/datasources.yaml`:

```yaml
datasources:
  - name: postgresql-datasource
    uid: wardriving-postgres
    type: postgres
    access: proxy
    isDefault: true
    url: postgres:5432
    user: postgres
    secureJsonData:
      password: postgres
    jsonData:
      database: wardriving
      sslmode: disable
```

- `url: postgres:5432`: usa el nombre del servicio de Compose.
- `sslmode: disable`: conexión sin TLS dentro de la red interna de Docker.
- Es la fuente por defecto (`isDefault: true`).

### Aprovisionamiento del dashboard

`Grafana/dashboard.yaml` le dice a Grafana que cargue todos los JSON de
`/var/lib/grafana/dashboards`:

```yaml
providers:
  - name: wardriving
    type: file
    disableDeletion: false
    updateIntervalSeconds: 10
    allowUiUpdates: true
    options:
      path: /var/lib/grafana/dashboards
```

- `updateIntervalSeconds: 10`: Grafana revisa cambios cada 10 segundos.
- `allowUiUpdates: true`: permite guardar cambios desde la interfaz.
- `disableDeletion: false`: permite eliminar el dashboard desde la UI (volverá a aparecer si
  el archivo sigue presente).

### Dashboard "Metricas"

El dashboard está exportado con el formato **v2** de Grafana
(`apiVersion: dashboard.grafana.app/v2`) y se muestra en `http://localhost:3000/d/adwktd6/metricas`.

![Dashboard general](Documentation/imgs/dashboard.png)

Contiene siete paneles:

| Panel | Tipo | Qué muestra |
|---|---|---|
| **Total de redes detectadas** | Bar gauge (LCD) | `COUNT(*)` de `wifi_network` |
| **Top 15 fabricantes detectados** | Barras horizontales | 15 fabricantes con más redes |
| **Fabricantes identificados** | Gauge | Número de fabricantes distintos |
| **Proporción de redes según estado WPS** | Pie chart | Activado vs. desactivado |
| **Proporción de redes según tipo de cifrado** | Pie chart | WPA3 / WPA2 / WPA / WEP / Open / Otro |
| **Distribución geográfica según estado WPS** | Geomap | Puntos coloreados por WPS |
| **Distribución geográfica según tipo de cifrado** | Geomap | Puntos coloreados por cifrado |

![Estadísticas y fabricantes](Documentation/imgs/estadisticas.png)

Detalles de implementación:

- Los mapas usan **OpenStreetMap** como *basemap* y descartan coordenadas nulas o `(0,0)`.
- Los fabricantes `NULL`, vacíos o `unknown` se agrupan como **"Desconocido"**.
- El cifrado se normaliza con `ILIKE`:
  - `%WPA3%` → WPA3
  - `%WPA2%` → WPA2
  - `%WPA%` → WPA
  - `%WEP%` → WEP
  - vacío / `NULL` / `%OPEN%` / `%NONE%` → Open
  - resto → Otro
- Los paneles **Total de redes** y **Fabricantes identificados** usan consultas sin filtros,
  por lo que sus valores no cambian al aplicar los filtros del dashboard.
- El rango de tiempo superior (`Last 6 hours`) **no afecta** las consultas: el dashboard no
  filtra por tiempo.

### Filtros

En la parte superior hay tres variables:

| Filtro | Tipo | Valores | Origen |
|---|---|---|---|
| **WPS** | Variable personalizada | `All`, `Activado`, `Desactivado` | Lista fija |
| **Fabricante** | Variable de consulta | Fabricantes de la BD | `SELECT` sobre `wifi_network` |
| **Cifrado** | Variable de consulta | WPA3, WPA2, WPA, WEP, Open, Otro | Clasificación calculada |

![Filtros disponibles](Documentation/imgs/filtros.png)

Los filtros se aplican con las variables `${WPS}`, `${Fabricante}` y `${Cifrado}` en las
consultas SQL de los paneles. Al seleccionar un valor, se recalcula el panel correspondiente.

Ejemplo con **Fabricante = HUAWEI TECHNOLOGIES CO.,LTD**:

![Filtros aplicados](Documentation/imgs/filtros_aplicados.png)

> Observa que **Total de redes detectadas** sigue mostrando 1 557 y **Fabricantes
> identificados** sigue mostrando 58: son paneles globales sin filtros. Los paneles que sí
> cambian son las proporciones, el top de fabricantes y los mapas.

---

## ETL: de Kismet a PostgreSQL

Archivo: `Infrastructure/ETL/main.py`

Convierte una captura de **Kismet** (archivo SQLite `.kismet`) en filas limpias dentro de
PostgreSQL.

### Requisitos

```bash
cd Infrastructure/ETL
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

`requirements.txt`:

```text
psycopg2==2.9.13
```

### Ejecución

```bash
cd Infrastructure/ETL
source venv/bin/activate
python3 main.py /ruta/a/Captura_Ciudad-Vieja.kismet
```

El script espera un único argumento: la ruta al archivo `.kismet`. Si no se pasa, muestra el
uso y termina.

> La conexión está definida al inicio del archivo:
>
> ```python
> DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/wardriving"
> ```
>
> Si cambiaste la contraseña, el puerto o ejecutas el ETL en otra máquina, edita esa línea.

### ¿Qué hace el ETL?

#### 1. Lectura del archivo Kismet

Abre el archivo SQLite y consulta la tabla `devices`, extrayendo del JSON interno de Kismet:

- `devmac` → BSSID
- `kismet.device.base.name` → SSID
- `kismet.device.base.manuf` → fabricante
- `kismet.device.base.channel` → canal
- `kismet.device.base.frequency` → frecuencia
- `kismet.device.base.crypt` → cifrado
- `kismet.device.base.first_time` / `last_time` → primera y última detección
- `kismet.device.base.signal.last_signal` → señal
- `avg_lat` / `avg_lon` → coordenadas promedio
- `wps_state` → estado WPS, con varios *fallbacks* según el formato del dispositivo

Solo considera dispositivos de tipo `Wi-Fi AP`.

#### 2. Limpieza y consolidación

| Regla | Detalle |
|---|---|
| **BSSID obligatorio** | Descarta filas sin `devmac` |
| **Coordenadas válidas** | Descarta `NULL`, `(0,0)`, latitud fuera de `[-90, 90]` y longitud fuera de `[-180, 180]` |
| **Un registro por BSSID** | Si un BSSID aparece varias veces, conserva la observación con **mejor señal** |
| **Mejor señal** | En dBm, el valor más cercano a `0` es mejor (ej. `-40` es mejor que `-80`) |
| **WPS normalizado** | `1` si el valor original es `1`; en cualquier otro caso `0` |
| **SSID privado** | Guarda `ssid = NULL` intencionalmente para no exponer nombres de red |
| **Fechas de sesión** | `started_at` = mínimo `first_seen`; `ended_at` = máximo `last_seen` |

#### 3. Inserción en PostgreSQL

- Crea una fila en `wardriving.wardriving_session` con el nombre del archivo.
- Inserta o actualiza redes con `ON CONFLICT (bssid)`.
- Solo actualiza una red existente si la nueva señal es **mejor** que la almacenada.
- Todo ocurre en una transacción: si falla algo, hace `ROLLBACK`.

### Resumen de salida

Al terminar, imprime un resumen como este:

```text
Resumen de extracción
────────────────────────────────────────
Archivo Kismet                : Captura_Ciudad-Vieja.kismet
Registros AP encontrados      : 1234
BSSID únicos válidos          : 567
Insertados nuevos             : 500
Actualizados por mejor señal  : 40
Omitidos existentes           : 27
Descartados sin BSSID         : 2
Descartados sin ubicación     : 100
Duplicados en el archivo      : 65
Total no cargados como nuevo  : 194
────────────────────────────────────────
```

| Campo | Significado |
|---|---|
| `Registros AP encontrados` | Filas devueltas por la consulta a Kismet |
| `BSSID únicos válidos` | Redes únicas tras limpiar y consolidar |
| `Insertados nuevos` | BSSID que no existían en la base |
| `Actualizados por mejor señal` | BSSID existentes con mejor señal en esta captura |
| `Omitidos existentes` | BSSID existentes sin mejora de señal |
| `Descartados sin BSSID` | Filas sin identificador |
| `Descartados sin ubicación` | Filas sin coordenadas válidas |
| `Duplicados en el archivo` | Repeticiones del mismo BSSID dentro de la captura |
| `Total no cargados como nuevo` | Suma de descartes, duplicados y omitidos |

### Procesar varias capturas

El ETL es acumulativo: puedes ejecutarlo con distintas capturas y la base irá incorporando
redes nuevas y mejorando la ubicación/señal de las existentes.

```bash
for f in /ruta/capturas/*.kismet; do
    python3 main.py "$f"
done
```

---

## Raspberry Pi: captura y pantalla táctil

La carpeta `RPI_scripts/` contiene la interfaz local del dispositivo de captura.

### `script.py` — interfaz principal

Interfaz gráfica en **pygame** que se dibuja directamente sobre el framebuffer de una
pantalla TFT de **480×320**.

```python
W, H = 480, 320
FB   = "/dev/fb1"            # framebuffer de la pantalla
DEV  = "/dev/input/event0"   # dispositivo táctil
```

> Estos dispositivos pueden variar según el modelo de pantalla y la configuración del
> sistema. Verifica con `ls /dev/fb*` y `evtest` cuáles corresponden en tu Raspberry.

La calibración del táctil está fijada en:

```python
X_MIN=200
X_MAX=3900
Y_MIN=200
Y_MAX=3900
```

Si el toque no coincide con los botones, usa `lcd_test.py` para recalibrar.

#### Botones

| Botón | Acción |
|---|---|
| **START** | Inicia el modo monitor y lanza Kismet |
| **STOP** | Detiene Kismet y `cgps` |
| **RESET** | Restaura la interfaz a modo managed, recupera la MAC original y reinicia NetworkManager |
| **SHUTDOWN** | Apaga la Raspberry (requiere **doble toque** en menos de 1 segundo) |

La pantalla se apaga automáticamente tras **60 segundos** sin actividad (`DIM_TIMEOUT`) y se
reactiva al tocar.

#### Secuencia de START

```text
sudo systemctl start gpsd
sudo airmon-ng check kill
sudo ip link set <iface> down
sudo macchanger -r <iface>          # MAC aleatoria
sudo iw dev <iface> set type monitor
sudo ip link set <iface> up
cgps &                              # visor de GPS
kismet -c <iface> -t <fecha> --override wardrive &
```

- Detecta automáticamente la interfaz WiFi con `iw dev`.
- Cambia la MAC a una aleatoria antes de capturar.
- Guarda la captura con un nombre basado en la fecha (`YYYY-MM-DD_HH-MM-SS`).
- Kismet se lanza con el *override* `wardrive`.

#### Secuencia de RESET

```text
pkill kismet
pkill cgps
sudo systemctl stop gpsd
sudo pkill gpsd
sudo ip link set <iface> down
sudo macchanger -p <iface>          # recupera la MAC original
sudo iw dev <iface> set type managed
sudo ip link set <iface> up
sudo systemctl restart NetworkManager
```

Después de restaurar la red, vuelve a iniciar el servidor HTTP.

#### Servidor HTTP para descargar capturas

`script.py` levanta un servidor HTTP en el puerto **8000**:

```python
http_server_proc = subprocess.Popen(
    [sys.executable, "-m", "http.server", "8000"],
    cwd="/home/samuel/Test",
    ...
)
```

- Sirve el contenido de `/home/samuel/Test`.
- Desde otra máquina de la red local: `http://<IP-de-la-Raspberry>:8000`
- El servidor se detiene al iniciar el modo monitor y se vuelve a levantar tras un RESET.
- **Ajusta `server_dir`** a la carpeta donde Kismet guarda las capturas en tu instalación.

La IP y el modo actual de la interfaz se muestran en la esquina superior de la pantalla.

#### Ejecución

```bash
sudo python3 RPI_scripts/script.py
```

El script necesita permisos para cambiar la interfaz, ejecutar `macchanger`, iniciar `gpsd`
y lanzar Kismet. Si no quieres ejecutarlo como root, configura `sudo` sin contraseña para los
comandos concretos.

### `lcd_test.py` — prueba de pantalla y táctil

Script reducido para validar la pantalla y el táctil antes de usar la interfaz completa.

```bash
python3 RPI_scripts/lcd_test.py
```

- Dibuja dos botones grandes (`+` y `-`).
- Lee eventos de `/dev/input/event0`.
- Imprime en consola las coordenadas detectadas.
- Sirve para comprobar la rotación y ajustar `X_MIN`, `X_MAX`, `Y_MIN`, `Y_MAX`.

---

## Flujo de trabajo completo

1. **Encender** la Raspberry Pi y abrir `script.py`.
2. Pulsar **START** para poner la interfaz en modo monitor y lanzar Kismet.
3. Recorrer la zona con el GPS activo. Kismet guarda la captura en un archivo `.kismet`.
4. Pulsar **STOP** al terminar.
5. Pulsar **RESET** para devolver la interfaz a modo managed y recuperar la MAC original.
6. Descargar la captura desde `http://<IP-Raspberry>:8000` a tu equipo de análisis.
7. Levantar la infraestructura:

   ```bash
   cd Infrastructure
   bash init.sh
   ```

8. Cargar la captura con el ETL:

   ```bash
   cd Infrastructure/ETL
   source venv/bin/activate
   python3 main.py /ruta/a/captura.kismet
   ```

9. Abrir `http://localhost:3000` y explorar el dashboard **Metricas**.
10. Aplicar filtros por **WPS**, **Fabricante** y **Cifrado** para el análisis.

---

## Comandos de referencia

### Infraestructura

```bash
# Levantar y restaurar todo
cd Infrastructure && bash init.sh

# Ver estado
docker compose ps

# Ver logs
docker compose logs -f
docker compose logs -f postgres
docker compose logs -f grafana

# Detener sin borrar datos
docker compose down

# Detener y borrar volúmenes
docker compose down -v

# Reiniciar un servicio
docker compose restart grafana
```

### Base de datos

Todos los comandos se ejecutan desde `Infrastructure/`:

```bash
cd Infrastructure

# Consola psql
docker compose exec postgres psql -U postgres -d wardriving

# Ejecutar una consulta puntual
docker compose exec postgres psql -U postgres -d wardriving \
  -c "SELECT count(*) FROM wardriving.wifi_network;"

# Ver las tablas del esquema wardriving
docker compose exec postgres psql -U postgres -d wardriving -c '\dt wardriving.*'

# Inspeccionar el dump
pg_restore -l DB/db.dump | less

# Restaurar manualmente
docker compose exec -T postgres pg_restore -U postgres -d wardriving \
  --clean --if-exists --no-owner --no-acl --exit-on-error -v < DB/db.dump
```

### ETL

```bash
cd Infrastructure/ETL
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 main.py /ruta/captura.kismet
deactivate
```

### Grafana

```bash
# Abrir en el navegador
xdg-open http://localhost:3000

# Verificar que el datasource responde
curl -s http://localhost:3000/api/health

# Recargar aprovisionamiento (reiniciar Grafana)
docker compose restart grafana
```

### Raspberry Pi

```bash
# Interfaz principal
sudo python3 RPI_scripts/script.py

# Prueba de pantalla/táctil
python3 RPI_scripts/lcd_test.py

# Comprobar interfaz WiFi
iw dev

# Comprobar GPS
cgps

# Ver dispositivos de entrada
evtest
```

---

## Solución de problemas

| Síntoma | Causa probable | Solución |
|---|---|---|
| `./init.sh: Exec format error` | El *shebang* no está en la primera línea | Ejecuta `bash init.sh` |
| `permission denied` al ejecutar `init.sh` | Falta permiso de ejecución | `chmod +x init.sh` o usa `bash init.sh` |
| `port is already allocated` en 3000 o 5432 | Otro servicio usa el puerto | `sudo ss -lptn 'sport = :3000'` y detén el proceso, o cambia el mapeo en Compose |
| `docker: command not found` | Docker no instalado | Instala Docker Engine y el plugin Compose v2 |
| `docker compose: command not found` | Solo está `docker-compose` v1 | Instala el plugin v2 (`docker compose`) |
| PostgreSQL no responde tras 120 s | Contenedor caído o volumen corrupto | `docker compose logs postgres`; luego `docker compose down -v && bash init.sh` |
| `pg_restore: error: unsupported version` | Dump creado con una versión más nueva | Usa una imagen `postgres:16` o superior |
| El dump no se restaura en el segundo arranque | El marcador `.wardriving_restored` ya existe | Bórralo o usa `docker compose down -v` |
| Grafana muestra "No data" | Datasource mal configurado o base vacía | Revisa `docker compose logs grafana` y ejecuta `SELECT count(*) FROM wardriving.wifi_network;` |
| Grafana no abre el dashboard | El JSON no se cargó | `docker compose restart grafana` y revisa *Provisioning* en los logs |
| El dashboard no aparece en la página de inicio | `GF_USERS_HOME_PAGE` apunta a otro UID | Abre manualmente `http://localhost:3000/d/adwktd6/metricas` |
| Los filtros no cambian los totales | Es el comportamiento esperado | Los paneles de totales son globales y no usan variables |
| `psycopg2` no instala | Faltan dependencias de compilación | `sudo apt install libpq-dev python3-dev` o usa `psycopg2-binary` |
| El ETL no conecta | PostgreSQL no está arriba o la URL es incorrecta | Inicia `init.sh` y revisa `DATABASE_URL` |
| El táctil no responde | `/dev/input/event0` no es el dispositivo correcto | Identifica el evento con `evtest` y ajusta `DEV` |
| El toque está descalibrado | Orientación o rangos incorrectos | Ajusta `X_MIN/X_MAX/Y_MIN/Y_MAX` con `lcd_test.py` |
| Kismet no captura | Interfaz no está en modo monitor | Revisa `iw dev` y ejecuta **RESET** y luego **START** |
| No se puede descargar la captura | `server_dir` no existe o no hay IP | Ajusta la ruta en `script.py` y verifica la IP en pantalla |

### Ver logs completos

```bash
cd Infrastructure
docker compose logs --tail=200 postgres
docker compose logs --tail=200 grafana
```

### Comprobar la base desde fuera

```bash
psql "postgresql://postgres:postgres@localhost:5432/wardriving" \
     -c "SELECT count(*) FROM wardriving.wifi_network;"
```

---

## Seguridad, privacidad y ética

### Este entorno es para laboratorio

La configuración por defecto está pensada para **uso local y demostración**:

- Grafana permite acceso **anónimo** y tiene el **login deshabilitado**.
- PostgreSQL escucha en `0.0.0.0:5432` con usuario `postgres` y contraseña `postgres`.
- No hay TLS entre los contenedores.

No expongas estos puertos a Internet. Si necesitas acceso remoto, usa una VPN, un *reverse
proxy* con autenticación y contraseñas robustas.

Para limitar el acceso al propio equipo, cambia los mapeos de puertos:

```yaml
ports:
  - "127.0.0.1:5432:5432"
  - "127.0.0.1:3000:3000"
```

### Datos sensibles

La base y el dump contienen **BSSID** (identificadores únicos de puntos de acceso) y
**coordenadas geográficas**. Aunque el ETL no almacena el SSID, la combinación de BSSID y
ubicación permite identificar redes físicas concretas.

- No publiques el dump ni volcados de la tabla `wifi_network` con `bssid`, `lat` y `lon`.
- No publiques capturas crudas de Kismet: contienen mucha más información.
- Anonimiza o agrega los datos antes de compartirlos en publicaciones o presentaciones.
- Ten en cuenta que las capturas incluyen direcciones MAC de dispositivos y clientes.

### Aspecto legal

El *wardriving* consiste en escuchar tramas WiFi difundidas públicamente. Aun así:

- La legalidad varía según el país y la jurisdicción.
- Captura solo en espacios públicos o con autorización expresa.
- No intentes acceder, asociarte ni interactuar con redes ajenas.
- No uses la información para identificar personas o dispositivos.
- Documenta el consentimiento cuando corresponda y sigue las normas de tu institución.

Este repositorio tiene fines **académicos y de investigación**. El uso indebido es
responsabilidad de quien lo realice.

---

## Licencia y autoría

Proyecto de tesis — análisis de vulnerabilidades en redes WiFi mediante wardriving.

Repositorio: [`SmillerMP/WiFI-Vulnerabilitys`](https://github.com/SmillerMP/WiFI-Vulnerabilitys)
