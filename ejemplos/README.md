# Ejemplos

Recursos para usar la [EIC API + MCP](../README.md) sin empezar desde cero.

## 📓 Notebooks

Se abren en Google Colab sin instalar nada. Todo parte de un `pd.read_csv(url)`.

| Notebook | Qué enseña | |
|---|---|---|
| [01_inicio_rapido](notebooks/01_inicio_rapido.ipynb) | Cargar toda la EIC 2025 en un DataFrame, entender sus columnas, ordenar entidades, filtrar municipios y revisar la precisión de cada cifra | [![Abrir en Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/zamax14/EIC-API-MCP/blob/main/ejemplos/notebooks/01_inicio_rapido.ipynb) |
| [02_2015_vs_2025](notebooks/02_2015_vs_2025.ipynb) | Qué cambió entre las dos encuestas, qué cambios son estadísticamente claros y qué no se debe comparar | [![Abrir en Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/zamax14/EIC-API-MCP/blob/main/ejemplos/notebooks/02_2015_vs_2025.ipynb) |

En local: `pip install pandas matplotlib jupyter`.

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
