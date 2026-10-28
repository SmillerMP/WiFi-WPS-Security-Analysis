-- Wardriving database schema
-- Compatible con docker-entrypoint-initdb.d de PostgreSQL
-- La base de datos debe crearse con POSTGRES_DB=wardriving

CREATE SCHEMA IF NOT EXISTS wardriving;

SET search_path = wardriving;

CREATE TABLE IF NOT EXISTS wardriving_session (
    session_id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    started_at TIMESTAMP NOT NULL,
    ended_at TIMESTAMP,
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS wifi_network (
    wifi_id BIGSERIAL PRIMARY KEY,
    session_id BIGINT REFERENCES wardriving_session(session_id) ON DELETE SET NULL,
    ssid TEXT,
    bssid TEXT UNIQUE NOT NULL,
    manufacturer TEXT,
    channel INTEGER,
    frequency_khz INTEGER,
    encryption TEXT,
    signal_dbm INTEGER,
    lat DOUBLE PRECISION,
    lon DOUBLE PRECISION,
    first_seen TIMESTAMP,
    last_seen TIMESTAMP,
    wps_state INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_wifi_geo ON wifi_network(lat, lon);
CREATE INDEX IF NOT EXISTS idx_wifi_wps ON wifi_network(wps_state);
CREATE INDEX IF NOT EXISTS idx_wifi_last_seen ON wifi_network(last_seen);
CREATE INDEX IF NOT EXISTS idx_wifi_session ON wifi_network(session_id);

COMMENT ON SCHEMA wardriving IS 'Esquema para almacenar datos procesados del sistema de wardriving';

COMMENT ON TABLE wardriving_session IS 'Sesiones de captura de wardriving';
COMMENT ON TABLE wifi_network IS 'Redes inalámbricas detectadas durante las sesiones de wardriving';