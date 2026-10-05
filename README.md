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
