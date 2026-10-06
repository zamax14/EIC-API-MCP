# Ejemplos

Recursos para usar la [EIC API + MCP](../README.md) sin empezar desde cero.

## 📓 Notebooks

Todos usan la API pública y se pueden abrir directo en Google Colab, sin instalar nada.

| Notebook | Qué enseña | |
|---|---|---|
| [01_consultas_api](notebooks/01_consultas_api.ipynb) | Pasar de una pregunta a un DataFrame: catálogos, búsqueda de indicadores, datos con intervalos de confianza, rankings y perfiles | [![Abrir en Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/zamax14/EIC-API-MCP/blob/main/ejemplos/notebooks/01_consultas_api.ipynb) |
| [02_base_completa_parquet](notebooks/02_base_completa_parquet.ipynb) | Descargar la base completa (~1 millón de estimaciones), unir tablas, medir la precisión municipal y consultar con DuckDB sobre la URL | [![Abrir en Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/zamax14/EIC-API-MCP/blob/main/ejemplos/notebooks/02_base_completa_parquet.ipynb) |
| [03_evolucion_2015_2025](notebooks/03_evolucion_2015_2025.ipynb) | Comparar la Intercensal 2015 con la 2025 bien: equivalencias, advertencias, cambios estadísticamente claros y lo que no se debe comparar | [![Abrir en Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/zamax14/EIC-API-MCP/blob/main/ejemplos/notebooks/03_evolucion_2015_2025.ipynb) |

En local: `pip install pandas pyarrow matplotlib duckdb jupyter` y abre la carpeta `notebooks/`.

## 🤖 Configuración MCP

| Archivo | Cliente | Cómo usarlo |
|---|---|---|
| [`mcp/claude-code.mcp.json`](mcp/claude-code.mcp.json) | Claude Code | Cópialo como `.mcp.json` en la raíz de tu proyecto. Claude Code te pedirá aprobar el servidor la primera vez. |
| [`mcp/codex.config.toml`](mcp/codex.config.toml) | Codex | Agrega la sección a `~/.codex/config.toml` (Codex usa TOML, no JSON). |

Atajos equivalentes desde la terminal:

```sh
claude mcp add --transport http eic https://eic.datzin.com.mx/mcp   # Claude Code
codex mcp add eic --url https://eic.datzin.com.mx/mcp               # Codex
```

Si montaste tu propia instancia, cambia la `url` por la de tu dominio (`https://tu-dominio/mcp`).

Para otros clientes (Claude Desktop, Cursor, VS Code, ChatGPT), revisa la sección [Conecta tu IA](../README.md#-conecta-tu-ia-mcp) del README principal.
