"""Servidor MCP de la Encuesta Intercensal (INEGI).

HTTP:  uvicorn eic.mcp_server:app   (endpoint /mcp, sin sesión)
stdio: python -m eic.mcp_server
"""

from typing import Annotated, Literal

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

from eic import queries

MAX_FILAS = 500  # tope por llamada: respuestas grandes saturan el contexto del modelo

mcp = FastMCP(
    "eic-inegi",
    instructions="""Datos de la Encuesta Intercensal (EIC) del INEGI, México.

Datasets:
- eic2025_localidades: EIC 2025 por nacional, entidad, municipio y localidades de 50 000 y más habitantes.
- eic2015_distritos: EIC 2015 por nacional, entidad y distrito electoral federal.
Las geografías de 2015 y 2025 solo son comparables a nivel nacional y por entidad, y los códigos de indicador difieren.

Flujo sugerido: listar_datasets → buscar_indicadores → (buscar_geografias) → obtener_datos.

Son estimaciones por muestreo: cita el coeficiente de variación (CV) cuando sea relevante.
Criterio INEGI: CV < 15 precisión alta, 15–30 moderada, > 30 baja (usar con reserva).
nota = MI: no disponible por muestra insuficiente; NA: no aplica. Los límites de confianza son al 90 %.
Fuente: INEGI, Encuesta Intercensal 2015 y 2025.""",
)

Dataset = Literal["eic2025_localidades", "eic2015_distritos"]
Nivel = Literal["nacional", "entidad", "municipio", "localidad", "resto_localidades", "distrito"]
SOLO_LECTURA = {"readOnlyHint": True, "openWorldHint": False}


def _precision(cv: float | None) -> str | None:
    if cv is None:
        return None
    return "alta" if cv < 15 else "moderada" if cv <= 30 else "baja"


@mcp.tool(annotations=SOLO_LECTURA)
def listar_datasets() -> list[dict]:
    """Lista los datasets disponibles con su descripción, fuente y temas (id, nombre, número de indicadores)."""
    return [d | {"temas": queries.temas(d["id"])} for d in queries.datasets()]


@mcp.tool(annotations=SOLO_LECTURA)
def buscar_indicadores(
    dataset: Dataset,
    texto: Annotated[str | None, Field(description="Palabras a buscar en código, nombre o descripción; sin acentos funciona")] = None,
    tema_id: Annotated[int | None, Field(description="Id de tema, de listar_datasets")] = None,
) -> list[dict]:
    """Busca indicadores (variables) de un dataset. Devuelve el código a usar en obtener_datos."""
    return queries.indicadores(dataset, tema_id, texto)


@mcp.tool(annotations=SOLO_LECTURA)
def buscar_geografias(
    dataset: Dataset,
    texto: Annotated[str | None, Field(description="Nombre a buscar, p. ej. 'Tijuana' o 'Oaxaca'")] = None,
    nivel: Nivel | None = None,
    cve_ent: Annotated[str | None, Field(pattern=r"^\d{2}$", description="Clave de entidad 01-32")] = None,
    limite: Annotated[int, Field(ge=1, le=MAX_FILAS)] = 50,
) -> dict:
    """Busca unidades geográficas y su clave `cvegeo`. Entidades: cve_ent 01 Aguascalientes … 32 Zacatecas, 00 nacional."""
    return queries.geografias(dataset, nivel, cve_ent, texto, limite, 0)


@mcp.tool(annotations=SOLO_LECTURA)
def obtener_datos(
    dataset: Dataset,
    indicadores: Annotated[list[str], Field(min_length=1, max_length=20, description="Códigos de buscar_indicadores")],
    cvegeo: Annotated[list[str] | None, Field(max_length=100, description="Claves de buscar_geografias")] = None,
    nivel: Annotated[Nivel | None, Field(description="Todas las geografías de un nivel, p. ej. 'entidad' para comparar estados")] = None,
    cve_ent: Annotated[str | None, Field(pattern=r"^\d{2}$")] = None,
    limite: Annotated[int, Field(ge=1, le=MAX_FILAS)] = 200,
    desplazamiento: Annotated[int, Field(ge=0)] = 0,
) -> dict:
    """Obtiene estimaciones: valor, error estándar, límites de confianza al 90 %, CV, precisión y nota (MI/NA).
    Filtra por cvegeo, por nivel y/o por cve_ent. Si total > limite, pagina con desplazamiento."""
    if not (cvegeo or nivel or cve_ent):
        raise ToolError("Indica al menos uno: cvegeo, nivel o cve_ent")
    r = queries.datos(dataset, indicadores, cvegeo, nivel, cve_ent, limite, desplazamiento)
    for fila in r["items"]:
        fila["precision"] = _precision(fila["coef_var"])
    return r


app = mcp.http_app(path="/mcp", stateless_http=True, json_response=True)

if __name__ == "__main__":
    mcp.run()
