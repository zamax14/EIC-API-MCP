-- Modelo largo: una fila de `estimacion` por (dataset, geografía, indicador).

CREATE TABLE dataset (
    id               VARCHAR PRIMARY KEY,   -- eic2015_distritos | eic2025_localidades
    anio             INTEGER NOT NULL,
    titulo           VARCHAR NOT NULL,
    geografia        VARCHAR NOT NULL,      -- descripción de la desagregación
    fuente_url       VARCHAR NOT NULL,
    licencia         VARCHAR,
    fecha_modificado VARCHAR,
    descargado_en    TIMESTAMP NOT NULL
);

CREATE TABLE entidad (
    cve_ent VARCHAR PRIMARY KEY,            -- 00 = nacional
    nombre  VARCHAR NOT NULL
);

CREATE TABLE tema (
    dataset_id VARCHAR NOT NULL,
    id         INTEGER NOT NULL,
    nombre     VARCHAR NOT NULL,
    PRIMARY KEY (dataset_id, id)
);

CREATE TABLE indicador (
    dataset_id    VARCHAR NOT NULL,
    codigo        VARCHAR NOT NULL,         -- 2025: POBTOT; 2015: IND_001
    nombre        VARCHAR NOT NULL,
    descripcion   VARCHAR,
    tema_id       INTEGER,
    mnemonico_alt VARCHAR,                  -- 2015: pob_tot
    PRIMARY KEY (dataset_id, codigo)
);

CREATE TABLE geografia (
    dataset_id   VARCHAR NOT NULL,
    cvegeo       VARCHAR NOT NULL,
    nivel        VARCHAR NOT NULL,          -- nacional|entidad|municipio|localidad|resto_localidades|distrito
    cve_ent      VARCHAR NOT NULL,
    cve_mun      VARCHAR,
    cve_loc      VARCHAR,
    cve_distrito VARCHAR,
    nombre       VARCHAR NOT NULL,
    nom_ent      VARCHAR NOT NULL,
    nom_mun      VARCHAR,
    padre_cvegeo VARCHAR,
    atributos    JSON,
    PRIMARY KEY (dataset_id, cvegeo)
);

CREATE TABLE estimacion (
    dataset_id     VARCHAR NOT NULL,
    cvegeo         VARCHAR NOT NULL,
    indicador      VARCHAR NOT NULL,
    valor          DOUBLE,
    error_estandar DOUBLE,
    lim_inf        DOUBLE,                  -- límites de confianza al 90%
    lim_sup        DOUBLE,
    coef_var       DOUBLE,
    nota           VARCHAR,                 -- MI: muestra insuficiente; NA: no aplica
    PRIMARY KEY (dataset_id, cvegeo, indicador)
);

-- Pares curados de indicadores comparables entre 2015 y 2025 (src/eic/equivalencias.csv).
CREATE TABLE equivalencia (
    codigo_2015 VARCHAR NOT NULL,
    codigo_2025 VARCHAR NOT NULL,
    tipo        VARCHAR NOT NULL CHECK (tipo IN ('exacta', 'aproximada')),
    nota        VARCHAR,                -- por qué es aproximada
    PRIMARY KEY (codigo_2015, codigo_2025)
);
