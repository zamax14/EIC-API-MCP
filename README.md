# EIC API + MCP

ETL de la Encuesta Intercensal (INEGI) hacia DuckDB, base de una API pública y un servidor MCP.

| Dataset | Desagregación |
|---|---|
| `eic2015_distritos` | Nacional, entidad y distrito electoral federal (Estadísticas Intercensales a Escalas Geoelectorales) |
| `eic2025_localidades` | Nacional, entidad, municipio y localidades de 50 000 y más habitantes |

## ETL

```sh
uv sync
uv run python -m eic.etl            # descarga de INEGI (se salta lo que no cambió) y reconstruye data/eic.duckdb
uv run python -m eic.etl --offline  # usa los zips de data/raw
uv run python tests/test_etl.py
```

Salidas: `data/eic.duckdb` y `data/parquet/<tabla>.parquet`. El esquema está en `src/eic/schema.sql`: tablas `estimacion` (formato largo, con valor, EE, límites al 90 % y CV), `indicador`, `tema`, `geografia`, `entidad` y `dataset`.

Para correrlo automáticamente cada semana con cron:

```cron
0 4 * * 1  cd /ruta/EIC-API-MCP && uv run python -m eic.etl >> data/etl.log 2>&1
```

## API

```sh
uv run uvicorn eic.api:app --host 0.0.0.0 --port 8000   # docs en /docs
uv run python tests/test_api.py
```

| Ruta (GET) | Parámetros |
|---|---|
| `/datasets` | |
| `/entidades` | |
| `/datasets/{id}/temas` | |
| `/datasets/{id}/indicadores` | `tema`, `q` (sin acentos ni mayúsculas) |
| `/datasets/{id}/geografias` | `nivel`, `cve_ent`, `q`, `limit`, `offset` |
| `/datasets/{id}/datos` | `indicador` (obligatorio, separados por coma), `cvegeo`, `nivel`, `cve_ent`, `limit` (≤ 10 000), `offset` |

Ejemplo: `/datasets/eic2025_localidades/datos?indicador=POBTOT,POBFEM&nivel=entidad`

La API abre la base en modo solo lectura y la vuelve a abrir sola cuando el ETL la reemplaza. `EIC_DB` cambia la ruta. DuckDB no deja abrirla mientras otro proceso, como DBeaver, la tenga abierta en modo escritura. El rate limiting va en el proxy (Caddy o nginx).

## Despliegue con Docker

```sh
docker compose up -d --build        # 1) etl corre una vez  2) api arranca si el etl terminó bien  3) nginx en 127.0.0.1:8081, bajo /api
docker compose run --rm etl         # recargar datos; la API toma la base nueva sin reiniciar
```

Para recargar cada semana desde el cron del servidor:

```cron
0 4 * * 1  cd /ruta/EIC-API-MCP && docker compose run --rm etl >> /var/log/eic-etl.log 2>&1
```

Protección contra abuso (`deploy/nginx.conf`); la API no se publica directamente:

| Capa | Límite |
|---|---|
| nginx | 5 req/s por IP con ráfaga de 20, 10 conexiones simultáneas por IP; el exceso recibe 429 |
| nginx | caché de 10 min para las respuestas (los datos solo cambian con el ETL), solo GET/HEAD y body de 1 KB como máximo |
| API | 64 peticiones en curso por worker (2 workers), páginas de 10 000 filas como máximo, parámetros validados |
| DuckDB | `EIC_DB_MEMORY` (384MB) y `EIC_DB_THREADS` (2) por proceso |
| Contenedor | api: 1 GB / 2 CPU; nginx: 256 MB |

Variables: `EIC_PORT` (8081, solo en 127.0.0.1) y `EIC_DB_MEMORY`/`EIC_DB_THREADS`. La API se sirve bajo `/api` (`EIC_ROOT_PATH`) y nginx toma la IP real del cliente desde `CF-Connecting-IP` (Cloudflare Tunnel).
