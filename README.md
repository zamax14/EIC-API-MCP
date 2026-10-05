# EIC · API + MCP

**La Encuesta Intercensal del INEGI (2015 y 2025) como API pública y como servidor MCP para IAs.**

Un ETL descarga los paquetes de datos abiertos directamente de INEGI y los normaliza en una base DuckDB. Sobre esa base corren una API REST de solo lectura y un servidor [MCP](https://modelcontextprotocol.io) para que asistentes como Claude, ChatGPT o Cursor consulten los datos.

![Python](https://img.shields.io/badge/python-3.12+-3776AB?logo=python&logoColor=white)
![DuckDB](https://img.shields.io/badge/DuckDB-FFF000?logo=duckdb&logoColor=black)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![MCP](https://img.shields.io/badge/MCP-FastMCP-8A2BE2)
![Docker](https://img.shields.io/badge/Docker-compose-2496ED?logo=docker&logoColor=white)

## 🌐 Ya está en línea, úsalo sin montar nada

| Qué | URL |
|---|---|
| Documentación interactiva (Swagger) | **https://eic.datzin.com.mx/api/docs** |
| Esquema OpenAPI | https://eic.datzin.com.mx/api/openapi.json |
| API REST | `https://eic.datzin.com.mx/api/…` |
| Servidor MCP (streamable HTTP, sin autenticación) | **`https://eic.datzin.com.mx/mcp`** |

Es gratis y abierto, con límite de peticiones por IP. Si necesitas más volumen o quieres tu propia copia, [móntalo tú mismo](#-móntalo-tú-mismo).

## ⚡ Pruébalo

```sh
# Población 2025 de todas las entidades
curl "https://eic.datzin.com.mx/api/datasets/eic2025_localidades/datos?indicador=POBTOT&nivel=entidad"

# ¿Qué indicadores hay sobre desplazamiento forzado? (la búsqueda ignora acentos)
curl "https://eic.datzin.com.mx/api/datasets/eic2025_localidades/indicadores?q=desplazamiento"

# Busca una localidad y su clave geográfica
curl "https://eic.datzin.com.mx/api/datasets/eic2025_localidades/geografias?nivel=localidad&q=tijuana"
```

Cada estimación trae su precisión estadística:

```json
{
  "cvegeo": "010000000",
  "nombre": "Aguascalientes",
  "nivel": "entidad",
  "indicador": "POBTOT",
  "indicador_nombre": "Población en viviendas particulares habitadas",
  "valor": 1534416.0,
  "error_estandar": 58302.68,
  "lim_inf": 1438496.15,
  "lim_sup": 1630335.85,
  "coef_var": 3.8,
  "nota": null
}
```

### Rutas de la API

Todas son `GET`.

| Ruta | Parámetros |
|---|---|
| `/api/datasets` | |
| `/api/entidades` | |
| `/api/datasets/{id}/temas` | |
| `/api/datasets/{id}/indicadores` | `tema`, `q` |
| `/api/datasets/{id}/geografias` | `nivel`, `cve_ent`, `q`, `limit`, `offset` |
| `/api/datasets/{id}/datos` | `indicador` (obligatorio; varios separados por coma), `cvegeo`, `nivel`, `cve_ent`, `limit` (≤ 10 000), `offset` |

`nivel` acepta `nacional`, `entidad`, `municipio`, `localidad`, `resto_localidades` o `distrito`.

## 🤖 Conecta tu IA (MCP)

Usa la instancia pública `https://eic.datzin.com.mx/mcp`, o la URL de tu propia instancia si lo montas.

<details open>
<summary><b>Cursor, Windsurf y clientes con soporte HTTP</b> (<code>mcp.json</code>)</summary>

```json
{
  "mcpServers": {
    "eic": {
      "url": "https://eic.datzin.com.mx/mcp"
    }
  }
}
```
</details>

<details>
<summary><b>VS Code</b> (<code>.vscode/mcp.json</code>)</summary>

```json
{
  "servers": {
    "eic": {
      "type": "http",
      "url": "https://eic.datzin.com.mx/mcp"
    }
  }
}
```
</details>

<details>
<summary><b>Claude Desktop</b> (<code>claude_desktop_config.json</code>, usa el puente <a href="https://www.npmjs.com/package/mcp-remote">mcp-remote</a>)</summary>

```json
{
  "mcpServers": {
    "eic": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "https://eic.datzin.com.mx/mcp"]
    }
  }
}
```

También puedes agregarlo sin JSON: en claude.ai o Claude Desktop, Configuración → Conectores → Agregar conector personalizado.
</details>

<details>
<summary><b>Claude Code</b></summary>

```sh
claude mcp add --transport http eic https://eic.datzin.com.mx/mcp
```
</details>

<details>
<summary><b>ChatGPT</b></summary>

1. Activa el modo desarrollador en Configuración → Aplicaciones y conectores → Configuración avanzada.
2. Crea un conector con la URL `https://eic.datzin.com.mx/mcp`.
3. Elige autenticación: "Sin autenticación".
</details>

<details>
<summary><b>Local por stdio</b> (si clonaste el repo y corriste el ETL)</summary>

```json
{
  "mcpServers": {
    "eic": {
      "command": "uv",
      "args": ["--directory", "/ruta/a/EIC-API-MCP", "run", "python", "-m", "eic.mcp_server"]
    }
  }
}
```
</details>

### Tools

| Tool | Qué hace |
|---|---|
| `listar_datasets` | Datasets disponibles con sus temas |
| `buscar_indicadores` | Encuentra códigos de indicador por texto o tema |
| `buscar_geografias` | Encuentra la clave `cvegeo` por nombre, nivel o entidad |
| `obtener_datos` | Estimaciones con error estándar, límites al 90 %, CV, `precision` (criterio INEGI) y nota MI/NA |

Todas las tools son de solo lectura. El servidor le indica al modelo cómo leer la precisión de cada estimación, para que no presente como sólidas cifras con muestra insuficiente.

Preguntas que puedes hacerle:
- *¿Qué municipio de Jalisco tiene mayor porcentaje de hogares desplazados por inseguridad?*
- *Compara los hogares afrodescendientes entre entidades en 2025.*
- *¿Cuántos habitantes tiene Tijuana según la Intercensal 2025 y qué tan precisa es la estimación?*

## 📊 Datos

| Dataset | Fuente INEGI | Desagregación | Indicadores |
|---|---|---|---|
| `eic2025_localidades` | [EIC 2025](https://www.inegi.org.mx/programas/eic/2025/), principales resultados por localidad de 50 000 y más habitantes | Nacional, 32 entidades, 2,478 municipios, 233 localidades | 341 en 16 temas |
| `eic2015_distritos` | [EIC 2015](https://www.inegi.org.mx/programas/intercensal/2015/), estadísticas a escalas geoelectorales | Nacional, 32 entidades, 300 distritos electorales federales | 107 |

> [!IMPORTANT]
> Son **estimaciones por muestreo**. Según el criterio de INEGI, un coeficiente de variación (CV) menor a 15 indica precisión alta, de 15 a 30 moderada, y mayor a 30 baja.
> `nota = MI` significa que el dato no está disponible por muestra insuficiente; `NA`, que no aplica.
> 2015 y 2025 solo son comparables a nivel nacional y por entidad, porque usan geografías distintas y sus códigos de indicador difieren.

### Modelo

Usa formato largo: una fila por dataset, geografía e indicador. Así cualquier consulta funciona igual sin importar si el CSV original tenía 349 o 540 columnas.

```mermaid
erDiagram
    dataset   ||--o{ indicador  : tiene
    dataset   ||--o{ geografia  : tiene
    dataset   ||--o{ tema       : tiene
    tema      ||--o{ indicador  : agrupa
    geografia ||--o{ geografia  : "padre_cvegeo"
    geografia ||--o{ estimacion : "de"
    indicador ||--o{ estimacion : mide
    entidad   ||--o{ geografia  : cve_ent
    estimacion {
        varchar dataset_id
        varchar cvegeo
        varchar indicador
        double  valor
        double  error_estandar
        double  lim_inf
        double  lim_sup
        double  coef_var
        varchar nota
    }
```

El esquema completo está en [`src/eic/schema.sql`](src/eic/schema.sql). El ETL también exporta cada tabla a Parquet en `data/parquet/`, por si prefieres analizar los datos con pandas, polars o DuckDB directamente.

## 🧱 Arquitectura

```mermaid
flowchart LR
    INEGI[(inegi.org.mx<br/>datos abiertos)] -->|zip CSV| ETL[etl<br/>corre y termina]
    ETL -->|swap atómico| DB[(eic.duckdb<br/>volumen)]
    DB -->|solo lectura| API[api<br/>FastAPI]
    DB -->|solo lectura| MCP[mcp<br/>FastMCP]
    API --> NGINX[nginx<br/>rate limit + caché]
    MCP --> NGINX
    NGINX -->|127.0.0.1:8081| PROXY[tu proxy con TLS<br/>Caddy · nginx · Cloudflare Tunnel]
    PROXY --> U((usuarios e IAs))
```

## 🐳 Móntalo tú mismo

Solo necesitas Docker con Compose v2.

```sh
git clone https://github.com/zamax14/EIC-API-MCP.git
cd EIC-API-MCP
docker compose up -d --build
```

Al arrancar, compose levanta todo en este orden:

1. **`etl`** descarga los datos de INEGI, construye la base en un volumen y termina.
2. **`api`** y **`mcp`** arrancan solo si el ETL terminó bien, y abren la base en solo lectura.
3. **`nginx`** las expone en `http://127.0.0.1:8081`: la API en `/api` y el MCP en `/mcp`.

```sh
curl http://127.0.0.1:8081/api/datasets   # comprobar
```

### Publicarlo con tu dominio

nginx solo escucha en `127.0.0.1`. Para exponerlo pon delante un proxy con TLS que reenvíe todo tu dominio, o las rutas `/api` y `/mcp`, a `http://127.0.0.1:8081`. Por ejemplo:

**Caddy** (obtiene el certificado HTTPS solo):

```caddy
eic.tudominio.com {
    reverse_proxy 127.0.0.1:8081
}
```

**Cloudflare Tunnel:** en el panel del túnel, agrega un *public hostname* con tipo de servicio `HTTP` y URL `localhost:8081`. Usa `HTTP`, no `HTTPS`: el TLS lo pone Cloudflare.

nginx toma la IP real del cliente de `X-Forwarded-For`, que mandan estos proxies, así que el límite se aplica a cada usuario y no al proxy.

### Configuración

Las variables se definen en el entorno o en un archivo `.env` junto a `compose.yaml`.

| Variable | Default | Qué controla |
|---|---|---|
| `EIC_PORT` | `8081` | Puerto local de nginx (solo en 127.0.0.1) |
| `EIC_DB_MEMORY` | `384MB` | Memoria máxima de DuckDB por proceso |
| `EIC_DB_THREADS` | `2` | Hilos de DuckDB por proceso |

Los límites contra abuso están en [`deploy/nginx.conf`](deploy/nginx.conf) y en [`compose.yaml`](compose.yaml):

| Capa | Protección |
|---|---|
| nginx | 5 req/s por IP con ráfaga de 20 y 10 conexiones simultáneas por IP; lo que excede recibe `429` |
| nginx | Caché de 10 min para la API (los datos solo cambian con el ETL); solo GET en `/api` y cuerpo de 64 KB como máximo en `/mcp` |
| API / MCP | Concurrencia acotada por worker, máximo 10 000 filas por página (500 en el MCP), parámetros validados y SQL siempre parametrizado |
| DuckDB | Base en solo lectura con memoria e hilos limitados por proceso |
| Contenedores | Memoria y CPU acotadas; usuario sin privilegios |

Si cambias `deploy/nginx.conf`, aplica la configuración con `docker compose up -d --force-recreate nginx`.

### Actualizar los datos

```sh
docker compose run --rm etl
```

El ETL se salta las descargas que no cambiaron. La API y el MCP detectan la base nueva sin reiniciar. Para programarlo cada semana con cron:

```cron
0 4 * * 1  cd /ruta/a/EIC-API-MCP && docker compose run --rm etl >> /var/log/eic-etl.log 2>&1
```

## 🛠️ Desarrollo local

Requiere [uv](https://docs.astral.sh/uv/).

```sh
uv sync
uv run python -m eic.etl                    # descarga de INEGI y construye data/eic.duckdb (~5 s)
uv run uvicorn eic.api:app --reload         # API en http://localhost:8000/docs
uv run python -m eic.mcp_server             # MCP por stdio
uv run python tests/test_etl.py && uv run python tests/test_api.py && uv run python tests/test_mcp.py
```

`python -m eic.etl --offline` reconstruye la base con los zips que ya están en `data/raw`, sin descargar. `EIC_DB` cambia la ruta de la base.

Para agregar otro paquete de datos abiertos de INEGI, añade una entrada a `SOURCES` en [`src/eic/etl.py`](src/eic/etl.py) con su URL y su parser.

## 📄 Fuente y créditos

Datos: **INEGI, Encuesta Intercensal 2015 y 2025**, usados conforme a los [términos de libre uso de la información del INEGI](https://www.inegi.org.mx/inegi/terminos.html). Este proyecto no está afiliado al INEGI. Si citas los datos, menciona a INEGI como fuente.
