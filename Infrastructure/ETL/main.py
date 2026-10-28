import os
import sqlite3
import sys
from datetime import datetime

import psycopg2
from psycopg2.extras import execute_values


# ─────────────────────────────────────────
#  CONFIGURACIÓN
# ─────────────────────────────────────────

DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/wardriving"


# ─────────────────────────────────────────
#  UTILIDADES
# ─────────────────────────────────────────

def ts_to_dt(ts):
    """Convierte timestamp Unix a datetime. Si falla, devuelve None."""
    try:
        return datetime.fromtimestamp(int(ts))
    except Exception:
        return None


def to_int_or_none(val):
    """Convierte un valor a int. Si falla, devuelve None."""
    try:
        return int(val)
    except Exception:
        return None


def to_float_or_none(val):
    """Convierte un valor a float. Si falla, devuelve None."""
    try:
        return float(val)
    except Exception:
        return None


def valid_coordinates(lat, lon):
    """
    Valida coordenadas geográficas.

    Se descartan:
    - Valores nulos
    - Coordenadas 0,0
    - Latitudes fuera de -90 a 90
    - Longitudes fuera de -180 a 180
    """
    lat = to_float_or_none(lat)
    lon = to_float_or_none(lon)

    if lat is None or lon is None:
        return False

    if lat == 0 and lon == 0:
        return False

    if not (-90 <= lat <= 90):
        return False

    if not (-180 <= lon <= 180):
        return False

    return True


def normalize_wps_state(val):
    """
    Normaliza el estado WPS.

    Para este análisis:
    1 = WPS habilitado
    0 = WPS no habilitado, no detectado o desconocido
    """
    try:
        return 1 if int(val) == 1 else 0
    except Exception:
        return 0


def is_better_signal(new_signal, current_signal):
    """
    Compara señales en dBm.

    En dBm, una señal más cercana a 0 es mejor.
    Ejemplo:
    -40 dBm es mejor que -80 dBm.
    """
    if new_signal is None:
        return False

    if current_signal is None:
        return True

    return new_signal > current_signal


# ─────────────────────────────────────────
#  EXTRACCIÓN PRINCIPAL
# ─────────────────────────────────────────

def extract(kismet_path, db_dsn=None):
    if not os.path.exists(kismet_path):
        print(f"[ERROR] Archivo no encontrado: {kismet_path}")
        sys.exit(1)

    # ─────────────────────────────────────────
    #  LECTURA DE ARCHIVO KISMET SQLITE
    # ─────────────────────────────────────────

    sqlite_conn = sqlite3.connect(kismet_path)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cur = sqlite_conn.cursor()

    sqlite_cur.execute("""
        SELECT
            d.devmac,
            json_extract(d.device, '$."kismet.device.base.name"') AS essid,
            json_extract(d.device, '$."kismet.device.base.manuf"') AS manufacturer,
            json_extract(d.device, '$."kismet.device.base.channel"') AS channel,
            json_extract(d.device, '$."kismet.device.base.frequency"') AS frequency,
            json_extract(d.device, '$."kismet.device.base.crypt"') AS encryption,
            json_extract(d.device, '$."kismet.device.base.first_time"') AS first_seen,
            json_extract(d.device, '$."kismet.device.base.last_time"') AS last_seen,
            json_extract(d.device, '$."kismet.device.base.signal"."kismet.common.signal.last_signal"') AS signal,
            d.avg_lat,
            d.avg_lon,
            COALESCE(
                json_extract(d.device, '$."dot11.device"."dot11.device.wps_state"'),
                json_extract(d.device, '$."dot11.device"."dot11.device.last_beaconed_ssid_record"."dot11.advertisedssid.wps_state"'),
                json_extract(ssid_entry.value, '$."dot11.advertisedssid.wps_state"')
            ) AS wps_state
        FROM devices d
        LEFT JOIN json_each(
            json_extract(d.device, '$."dot11.device"."dot11.device.advertised_ssid_map"')
        ) AS ssid_entry ON 1=1
        WHERE d.type = 'Wi-Fi AP'
        ORDER BY last_seen DESC
    """)

    rows = sqlite_cur.fetchall()
    sqlite_conn.close()

    total_rows = len(rows)

    if total_rows == 0:
        print("No se encontraron puntos de acceso WiFi en el archivo.")
        return

    # ─────────────────────────────────────────
    #  LIMPIEZA Y CONSOLIDACIÓN POR BSSID
    # ─────────────────────────────────────────

    discarded_no_bssid = 0
    discarded_no_geo = 0
    duplicated_rows = 0

    best_by_bssid = {}

    for row in rows:
        bssid = row["devmac"]

        if not bssid:
            discarded_no_bssid += 1
            continue

        lat = to_float_or_none(row["avg_lat"])
        lon = to_float_or_none(row["avg_lon"])

        if not valid_coordinates(lat, lon):
            discarded_no_geo += 1
            continue

        signal_dbm = to_int_or_none(row["signal"])
        current_best = best_by_bssid.get(bssid)

        if current_best is not None:
            duplicated_rows += 1

        # Se conserva la observación con mejor señal.
        # Esto asocia el BSSID a la coordenada donde fue detectado con mayor intensidad.
        if current_best is None or is_better_signal(signal_dbm, current_best["signal_dbm"]):
            best_by_bssid[bssid] = {
                # No se guarda ESSID para reducir exposición de nombres de red.
                # Si quisieras guardarlo, cambia None por row["essid"].
                "ssid": None,
                "manufacturer": row["manufacturer"],
                "channel": to_int_or_none(row["channel"]),
                "frequency_khz": to_int_or_none(row["frequency"]),
                "encryption": row["encryption"],
                "signal_dbm": signal_dbm,
                "lat": lat,
                "lon": lon,
                "first_seen": ts_to_dt(row["first_seen"]),
                "last_seen": ts_to_dt(row["last_seen"]),
                "wps_state": normalize_wps_state(row["wps_state"]),
            }

    valid_unique_networks = len(best_by_bssid)

    if valid_unique_networks == 0:
        print("\nResumen de extracción")
        print("────────────────────────────────────────")
        print(f"Archivo Kismet              : {os.path.basename(kismet_path)}")
        print(f"Registros AP encontrados    : {total_rows}")
        print(f"BSSID únicos válidos        : 0")
        print(f"Descartados sin BSSID       : {discarded_no_bssid}")
        print(f"Descartados sin ubicación   : {discarded_no_geo}")
        print("────────────────────────────────────────\n")
        return

    # ─────────────────────────────────────────
    #  FECHAS DE SESIÓN
    # ─────────────────────────────────────────

    first_times = [
        data["first_seen"]
        for data in best_by_bssid.values()
        if data["first_seen"] is not None
    ]

    last_times = [
        data["last_seen"]
        for data in best_by_bssid.values()
        if data["last_seen"] is not None
    ]

    session_started = min(first_times) if first_times else datetime.now()
    session_ended = max(last_times) if last_times else None
    session_name = os.path.basename(kismet_path)

    # ─────────────────────────────────────────
    #  INSERCIÓN / ACTUALIZACIÓN EN POSTGRESQL
    # ─────────────────────────────────────────

    pg_conn = psycopg2.connect(db_dsn or DATABASE_URL)
    pg_conn.autocommit = False
    pg_cur = pg_conn.cursor()

    try:
        # Registrar sesión de procesamiento
        pg_cur.execute(
            """
            INSERT INTO wardriving.wardriving_session 
                (name, started_at, ended_at)
            VALUES 
                (%s, %s, %s)
            RETURNING session_id
            """,
            (session_name, session_started, session_ended),
        )

        session_id = pg_cur.fetchone()[0]

        bssids = list(best_by_bssid.keys())

        # Consultar BSSID existentes y su señal actual
        pg_cur.execute(
            """
            SELECT bssid, signal_dbm
            FROM wardriving.wifi_network
            WHERE bssid = ANY(%s)
            """,
            (bssids,),
        )

        existing_networks = {
            row[0]: row[1]
            for row in pg_cur.fetchall()
        }

        insert_count = 0
        update_count = 0
        skip_count = 0

        for bssid, data in best_by_bssid.items():
            new_signal = data["signal_dbm"]

            if bssid not in existing_networks:
                insert_count += 1
            else:
                current_signal = existing_networks[bssid]

                if is_better_signal(new_signal, current_signal):
                    update_count += 1
                else:
                    skip_count += 1

        insert_rows = [
            (
                session_id,
                data["ssid"],
                bssid,
                data["manufacturer"],
                data["channel"],
                data["frequency_khz"],
                data["encryption"],
                data["signal_dbm"],
                data["lat"],
                data["lon"],
                data["first_seen"],
                data["last_seen"],
                data["wps_state"],
            )
            for bssid, data in best_by_bssid.items()
        ]

        execute_values(
            pg_cur,
            """
            INSERT INTO wardriving.wifi_network (
                session_id,
                ssid,
                bssid,
                manufacturer,
                channel,
                frequency_khz,
                encryption,
                signal_dbm,
                lat,
                lon,
                first_seen,
                last_seen,
                wps_state
            ) VALUES %s
            ON CONFLICT (bssid) DO UPDATE
            SET
                session_id = EXCLUDED.session_id,
                ssid = EXCLUDED.ssid,
                manufacturer = EXCLUDED.manufacturer,
                channel = EXCLUDED.channel,
                frequency_khz = EXCLUDED.frequency_khz,
                encryption = EXCLUDED.encryption,
                signal_dbm = EXCLUDED.signal_dbm,
                lat = EXCLUDED.lat,
                lon = EXCLUDED.lon,
                first_seen = EXCLUDED.first_seen,
                last_seen = EXCLUDED.last_seen,
                wps_state = EXCLUDED.wps_state,
                updated_at = NOW()
            WHERE
                EXCLUDED.signal_dbm IS NOT NULL
                AND (
                    wardriving.wifi_network.signal_dbm IS NULL
                    OR EXCLUDED.signal_dbm > wardriving.wifi_network.signal_dbm
                )
            """,
            insert_rows,
        )

        pg_conn.commit()

    except Exception as e:
        pg_conn.rollback()
        print(f"[ERROR] Falló la inserción en PostgreSQL: {e}")
        sys.exit(1)

    finally:
        pg_cur.close()
        pg_conn.close()

    # ─────────────────────────────────────────
    #  RESUMEN FINAL
    # ─────────────────────────────────────────

    discarded_total = discarded_no_bssid + discarded_no_geo + duplicated_rows
    not_loaded_as_new = discarded_total + skip_count + update_count

    print("\nResumen de extracción")
    print("────────────────────────────────────────")
    print(f"Archivo Kismet                : {session_name}")
    print(f"Registros AP encontrados      : {total_rows}")
    print(f"BSSID únicos válidos          : {valid_unique_networks}")
    print(f"Insertados nuevos             : {insert_count}")
    print(f"Actualizados por mejor señal  : {update_count}")
    print(f"Omitidos existentes           : {skip_count}")
    print(f"Descartados sin BSSID         : {discarded_no_bssid}")
    print(f"Descartados sin ubicación     : {discarded_no_geo}")
    print(f"Duplicados en el archivo      : {duplicated_rows}")
    print(f"Total no cargados como nuevo  : {not_loaded_as_new}")
    print("────────────────────────────────────────\n")


# ─────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso:")
        print("  python3 main.py <archivo.kismet>")
        print()
        print("Ejemplo:")
        print("  python3 main.py Captura_Ciudad-Vieja.kismet")
        sys.exit(1)

    extract(sys.argv[1])