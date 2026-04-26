import sqlite3
import sys
import os
from datetime import datetime

# ─────────────────────────────────────────
#  CONFIGURACIÓN
# ─────────────────────────────────────────
WPS_STATES = {
    1: "Habilitado",
}

# ─────────────────────────────────────────
#  UTILIDADES
# ─────────────────────────────────────────
def ts_to_str(ts):
    """Convierte unix timestamp a string legible."""
    if ts:
        try:
            return datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d %H:%M:%S")
        except:
            return str(ts)
    return "N/A"

def safe(val, default="N/A"):
    return val if val is not None else default

def wps_state_label(val):
    try:
        return WPS_STATES.get(int(val), "No habilitado")
    except:
        return "No habilitado"

def to_int_or_none(val):
    try:
        return int(val)
    except:
        return None

# ─────────────────────────────────────────
#  EXTRACCIÓN
# ─────────────────────────────────────────
def extract(kismet_path):
    if not os.path.exists(kismet_path):
        print(f"[ERROR] Archivo no encontrado: {kismet_path}")
        sys.exit(1)

    print(f"\n{'═'*70}")
    print(f"  EXTRACCIÓN KISMET: {kismet_path}")
    print(f"{'═'*70}\n")

    conn = sqlite3.connect(kismet_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
        SELECT
            d.devmac,
            json_extract(d.device, '$."kismet.device.base.name"')                            AS essid,
            json_extract(d.device, '$."kismet.device.base.manuf"')                           AS manufacturer,
            json_extract(d.device, '$."kismet.device.base.channel"')                         AS channel,
            json_extract(d.device, '$."kismet.device.base.frequency"')                       AS frequency,
            json_extract(d.device, '$."kismet.device.base.crypt"')                           AS encryption,
            json_extract(d.device, '$."kismet.device.base.first_time"')                      AS first_seen,
            json_extract(d.device, '$."kismet.device.base.last_time"')                       AS last_seen,
            json_extract(d.device, '$."kismet.device.base.signal"."kismet.common.signal.last_signal"')  AS signal,
            json_extract(d.device, '$."kismet.device.base.signal"."kismet.common.signal.max_signal"')   AS signal_max,
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
        GROUP BY d.devmac
        ORDER BY last_seen DESC
    """)

    rows = cur.fetchall()
    conn.close()

    if not rows:
        print("[!] No se encontraron APs en el archivo.")
        return

    print(f"  Total de redes detectadas: {len(rows)}\n")

    # ── Contadores para resumen ──
    total_wps       = 0
    fabricantes     = {}

    for i, row in enumerate(rows, 1):
        wps_val = to_int_or_none(row["wps_state"])
        wps_label = wps_state_label(wps_val)

        if wps_val == 1:
            total_wps += 1

        manuf = safe(row["manufacturer"])
        fabricantes[manuf] = fabricantes.get(manuf, 0) + 1

        print(f"┌─ [{i}] {safe(row['essid'])} ")
        print(f"│  BSSID         : {safe(row['devmac'])}")
        print(f"│  Fabricante    : {manuf}")
        print(f"│  Canal         : {safe(row['channel'])}  │  Frecuencia: {safe(row['frequency'])} KHz")
        print(f"│  Cifrado       : {safe(row['encryption'])}")
        print(f"│  Señal         : {safe(row['signal'])} dBm  (max: {safe(row['signal_max'])} dBm)")
        print(f"│  Coordenadas   : {safe(row['avg_lat'])}, {safe(row['avg_lon'])}")
        print(f"│  Primera vez   : {ts_to_str(row['first_seen'])}")
        print(f"│  Última vez    : {ts_to_str(row['last_seen'])}")
        print(f"│  ── WPS ───────────────────────────────────")
        print(f"│  WPS habilitado: {wps_label}")
        print(f"└{'─'*60}\n")

    # ─────────────────────────────────────────
    #  RESUMEN FINAL
    # ─────────────────────────────────────────
    print(f"\n{'═'*70}")
    print(f"  RESUMEN")
    print(f"{'═'*70}")
    print(f"  Total redes          : {len(rows)}")
    print(f"  Con WPS habilitado   : {total_wps} ({total_wps/len(rows)*100:.1f}%)")
    print(f"  Sin WPS              : {len(rows) - total_wps}")

    print(f"\n  Top fabricantes:")
    for fab, count in sorted(fabricantes.items(), key=lambda x: x[1], reverse=True)[:10]:
        bar = "█" * count
        print(f"    {fab:<30} {count:>4}  {bar}")

    print(f"\n{'═'*70}\n")


# ─────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python3 extract_kismet.py <archivo.kismet>")
        print("Ejemplo: python3 extract_kismet.py Kismet-20260421-19-24-00.kismet")
        sys.exit(1)

    extract(sys.argv[1])