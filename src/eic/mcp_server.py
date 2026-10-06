"""Servidor MCP de la Encuesta Intercensal (INEGI).

HTTP:  uvicorn eic.mcp_server:app   (endpoint /mcp, sin sesión)
stdio: python -m eic.mcp_server
"""

import json
from typing import Annotated, Literal

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.prompts import Message
from mcp_types import PromptReference
from pydantic import Field

from eic import queries

MAX_FILAS = 500  # tope por llamada: respuestas grandes saturan el contexto del modelo

GUIA = """# Guía de la Encuesta Intercensal (EIC) · INEGI

## Datasets
- **eic2025_localidades**: EIC 2025 (levantada en 2025). Niveles: nacional, entidad, municipio, localidad de
  50 000 y más habitantes y `resto_localidades` (localidades menores de 50 000 por entidad). 341 indicadores en 16 temas.
- **eic2015_distritos**: EIC 2015. Niveles: nacional, entidad y distrito electoral federal (300). 107 indicadores.
  Los distritos traen atributos: si es distrito indígena y su grupo de complejidad electoral.

## Claves geográficas (`cvegeo`)
- 2025: entidad (2) + municipio (3) + localidad (4). Nacional `000000000`, entidad `140000000`,
  municipio `141200000`, localidad `141200001`.
- 2015: entidad (2) + distrito (3). Nacional `00000`, entidad `14000`, distrito `14010`.

## Cómo leer una estimación
Son estimaciones por muestreo. Cada valor trae error estándar, límites de confianza al 90 % y coeficiente de
variación (CV). Criterio INEGI de precisión: CV < 15 **alta**; 15–30 **moderada** (usar con cautela);
> 30 **baja** (no usar para conclusiones). Un municipio "censado" se levantó completo y tiene CV 0.
`nota = MI`: no disponible por muestra insuficiente. `nota = NA`: no aplica.

## Comparar 2015 con 2025
Solo a nivel nacional o por entidad y solo con los pares de `eic://equivalencias` (tool `evolucion_2015_2025`).
Los pares "aproximada" cambiaron de definición: menciona la nota. Si los intervalos al 90 % no se traslapan,
la diferencia es estadísticamente clara.

## Ojo con los porcentajes por sexo
Algunos indicadores _F/_M son tasas dentro de cada sexo (p. ej. % de mujeres analfabetas) y otros son la
composición de un grupo (p. ej. % de la PEA que son mujeres). Lee el nombre del indicador antes de interpretarlo.

## Fuente
INEGI, Encuesta Intercensal 2015 y 2025. Términos de uso: https://www.inegi.org.mx/inegi/terminos.html
"""

mcp = FastMCP(
    "eic-inegi",
    instructions="""Datos de la Encuesta Intercensal (EIC) del INEGI, México: 2025 por entidad, municipio y
localidades de 50 000 y más habitantes; 2015 por entidad y distrito electoral federal.

Flujo recomendado:
1. ubicar_lugar para convertir un nombre ("Zapopan", "CDMX", "Juárez, Chihuahua") en su cvegeo.
2. Según la pregunta: perfil_lugar (ficha de un lugar frente a su entidad y el país), comparar_lugares,
   ranking (mayores/menores de un nivel), brecha_genero, evolucion_2015_2025 (cambios entre encuestas).
3. buscar_indicadores y obtener_datos para lo que no cubran las anteriores.

Son estimaciones por muestreo: reporta la precisión (CV < 15 alta, 15–30 moderada, > 30 baja) y no
presentes como sólidas las de precisión baja o con nota MI (muestra insuficiente). 2015 y 2025 solo se
comparan con evolucion_2015_2025. Cita siempre: "Fuente: INEGI, Encuesta Intercensal". Detalles en eic://guia.""",
    website_url="https://github.com/zamax14/EIC-API-MCP",
)

Dataset = Literal["eic2025_localidades", "eic2015_distritos"]
Nivel = Literal["nacional", "entidad", "municipio", "localidad", "resto_localidades", "distrito"]
CveEnt = Annotated[str, Field(pattern=r"^\d{2}$", description="Clave de entidad 01-32; 00 = nacional")]
Tema = Annotated[str | None, Field(description="Id o nombre del tema, p. ej. 'vivienda' o 'educación'")]
SOLO_LECTURA = {"readOnlyHint": True, "openWorldHint": False}


def _q(fn, *args, **kwargs):
    """Errores de búsqueda (lugar, tema o indicador inexistente) vuelven al modelo como ToolError legible."""
    try:
        return fn(*args, **kwargs)
    except (LookupError, ValueError) as e:
        raise ToolError(str(e)) from None


# ---------- tools: exploración ----------

@mcp.tool(title="Listar datasets", annotations=SOLO_LECTURA)
def listar_datasets() -> list[dict]:
    """Lista los datasets disponibles con su descripción, fuente y temas (id, nombre, número de indicadores)."""
    return [d | {"temas": queries.temas(d["id"])} for d in queries.datasets()]


@mcp.tool(title="Ubicar lugar", annotations=SOLO_LECTURA)
def ubicar_lugar(
    texto: Annotated[str, Field(description="'Zapopan', 'Juárez, Chihuahua', 'CDMX' o 'Zapopan, Jalisco (municipio)'")],
    dataset: Dataset = "eic2025_localidades",
) -> list[dict]:
    """Convierte el nombre de un lugar en candidatos con su cvegeo, nivel y entidad (coincidencia exacta primero).
    Si hay varios con el mismo nombre, pregunta o usa la entidad para elegir."""
    return queries.ubicar(texto, dataset)


@mcp.tool(title="Buscar indicadores", annotations=SOLO_LECTURA)
def buscar_indicadores(
    dataset: Dataset,
    texto: Annotated[str | None, Field(description="Palabras a buscar en código, nombre o descripción; sin acentos funciona")] = None,
    tema_id: Annotated[int | None, Field(description="Id de tema, de listar_datasets")] = None,
) -> list[dict]:
    """Busca indicadores (variables) de un dataset. Devuelve el código a usar en las demás tools."""
    return queries.indicadores(dataset, tema_id, texto)


@mcp.tool(title="Buscar geografías", annotations=SOLO_LECTURA)
def buscar_geografias(
    dataset: Dataset,
    texto: Annotated[str | None, Field(description="Nombre a buscar, p. ej. 'Tijuana' o 'Oaxaca'")] = None,
    nivel: Nivel | None = None,
    cve_ent: Annotated[str | None, Field(pattern=r"^\d{2}$", description="Clave de entidad 01-32")] = None,
    limite: Annotated[int, Field(ge=1, le=MAX_FILAS)] = 50,
) -> dict:
    """Lista unidades geográficas con su cvegeo, p. ej. todos los distritos o municipios de una entidad."""
    return queries.geografias(dataset, nivel, cve_ent, texto, limite, 0)


@mcp.tool(title="Obtener datos", annotations=SOLO_LECTURA)
def obtener_datos(
    dataset: Dataset,
    indicadores: Annotated[list[str], Field(min_length=1, max_length=20, description="Códigos de buscar_indicadores")],
    cvegeo: Annotated[list[str] | None, Field(max_length=100, description="Claves de ubicar_lugar o buscar_geografias")] = None,
    nivel: Annotated[Nivel | None, Field(description="Todas las geografías de un nivel, p. ej. 'entidad' para comparar estados")] = None,
    cve_ent: Annotated[str | None, Field(pattern=r"^\d{2}$")] = None,
    limite: Annotated[int, Field(ge=1, le=MAX_FILAS)] = 200,
    desplazamiento: Annotated[int, Field(ge=0)] = 0,
) -> dict:
    """Obtiene estimaciones crudas: valor, error estándar, límites de confianza al 90 %, CV, precisión y nota (MI/NA).
    Filtra por cvegeo, por nivel y/o por cve_ent. Si total > limite, pagina con desplazamiento."""
    if not (cvegeo or nivel or cve_ent):
        raise ToolError("Indica al menos uno: cvegeo, nivel o cve_ent")
    return queries.datos(dataset, indicadores, cvegeo, nivel, cve_ent, limite, desplazamiento)


# ---------- tools: análisis ----------

@mcp.tool(title="Perfil de un lugar", annotations=SOLO_LECTURA)
def perfil_lugar(
    cvegeo: Annotated[str, Field(description="Clave de ubicar_lugar")],
    dataset: Dataset = "eic2025_localidades",
    conjunto: Annotated[Literal["destacados", "vulnerabilidad"], Field(
        description="Indicadores por defecto si no das indicadores ni tema: un vistazo general o carencias sociales (solo 2025)")] = "destacados",
    indicadores: Annotated[list[str] | None, Field(max_length=100)] = None,
    tema: Tema = None,
) -> dict:
    """Ficha de un lugar: cada indicador con su valor, CV y precisión, junto a los de su entidad y el total nacional."""
    return _q(queries.perfil, dataset, cvegeo, indicadores, tema, conjunto)


@mcp.tool(title="Comparar lugares", annotations=SOLO_LECTURA)
def comparar_lugares(
    cvegeos: Annotated[list[str], Field(min_length=2, max_length=10, description="Claves de ubicar_lugar")],
    dataset: Dataset = "eic2025_localidades",
    indicadores: Annotated[list[str] | None, Field(max_length=100)] = None,
    tema: Tema = None,
) -> dict:
    """Tabla indicador × lugar (valor, CV, precisión). Sin indicadores ni tema usa los destacados."""
    return _q(queries.comparar, dataset, cvegeos, indicadores, tema)


@mcp.tool(title="Ranking", annotations=SOLO_LECTURA)
def ranking(
    indicador: Annotated[str, Field(description="Código, p. ej. PCN_PSINDER")],
    nivel: Nivel = "municipio",
    dataset: Dataset = "eic2025_localidades",
    cve_ent: Annotated[str | None, Field(pattern=r"^\d{2}$", description="Limitar a una entidad")] = None,
    orden: Annotated[Literal["desc", "asc"], Field(description="desc = mayores primero; asc = menores")] = "desc",
    n: Annotated[int, Field(ge=1, le=100)] = 10,
    excluir_baja_precision: Annotated[bool, Field(description="Descarta estimaciones con CV > 30")] = False,
) -> dict:
    """Los n mayores o menores valores de un indicador entre las geografías de un nivel, con la entidad y el
    país como referencia. Excluye datos con nota MI/NA."""
    return _q(queries.ranking, dataset, indicador, nivel, cve_ent, orden, n, excluir_baja_precision)


@mcp.tool(title="Brecha de género", annotations=SOLO_LECTURA)
def brecha_genero(
    cvegeo: Annotated[str, Field(description="Clave de ubicar_lugar (dataset 2025)")],
    tema: Tema = None,
) -> dict:
    """Indicadores de mujeres frente a hombres en un lugar (EIC 2025), con su total y la diferencia.
    Lee el nombre de cada indicador: unos son tasas dentro de cada sexo y otros la composición de un grupo."""
    return _q(queries.brecha_genero, "eic2025_localidades", cvegeo, tema)


@mcp.tool(title="Evolución 2015 → 2025", annotations=SOLO_LECTURA)
def evolucion_2015_2025(cve_ent: CveEnt = "00", tema: Tema = None) -> dict:
    """Cambios entre la EIC 2015 y la 2025 para el país o una entidad, solo con indicadores equivalentes.
    Incluye cambio absoluto y relativo, precisión de cada año y si los intervalos al 90 % se traslapan."""
    return _q(queries.evolucion, cve_ent, tema)


# ---------- resources ----------

@mcp.resource("eic://guia", name="Guía metodológica", mime_type="text/markdown")
def guia() -> str:
    """Cómo leer las estimaciones, claves geográficas y comparabilidad entre 2015 y 2025."""
    return GUIA


@mcp.resource("eic://entidades", name="Entidades federativas", mime_type="application/json")
def entidades() -> str:
    return json.dumps(queries.entidades(), ensure_ascii=False)


@mcp.resource("eic://equivalencias", name="Equivalencias 2015 ↔ 2025", mime_type="application/json")
def equivalencias() -> str:
    """Pares curados de indicadores comparables entre levantamientos."""
    return json.dumps(queries.equivalencias(), ensure_ascii=False)


@mcp.resource("eic://datasets/{dataset}/diccionario", name="Diccionario de indicadores", mime_type="text/markdown")
def diccionario(dataset: str) -> str:
    """Indicadores de un dataset agrupados por tema."""
    if not queries.dataset_existe(dataset):
        raise ValueError(f"dataset no encontrado: {dataset}")
    lineas, tema_actual = [f"# Indicadores de {dataset}"], None
    for i in queries.indicadores(dataset):
        if i["tema"] != tema_actual:
            tema_actual = i["tema"]
            lineas.append(f"\n## {tema_actual or 'Sin tema'}\n")
        lineas.append(f"- `{i['codigo']}`: {i['nombre']}")
    return "\n".join(lineas)


# ---------- prompts (pre-consultas) ----------

REGLAS = """
Reglas para la respuesta:
- Responde en español, con tablas cuando haya varias cifras.
- Junto a cada cifra relevante indica su precisión (alta, moderada o baja según el CV). Si es baja o tiene
  nota MI (muestra insuficiente), dilo explícitamente y no saques conclusiones de ella.
- No inventes datos: si algo no está en las herramientas, dilo.
- Cierra con: "Fuente: INEGI, Encuesta Intercensal {anio}." """


def _prompt(texto: str, anio: str = "2025") -> list[Message]:
    return [Message(texto.strip() + "\n" + REGLAS.format(anio=anio))]


@mcp.prompt(title="Guía rápida")
def guia_rapida() -> list[Message]:
    """Qué datos hay y qué tipo de preguntas se pueden hacer."""
    return _prompt("""
Lee el resource eic://guia y llama a listar_datasets. Luego explícame en pocas líneas qué datos de la Encuesta
Intercensal hay disponibles (años, niveles geográficos y temas) y propón 6 preguntas concretas e interesantes
que pueda hacer, una por tipo de análisis: perfil de un lugar, comparación, ranking, brecha de género,
vulnerabilidad social y evolución 2015 → 2025.""", "2015 y 2025")


@mcp.prompt(name="perfil_lugar", title="Perfil de un lugar")
def perfil_lugar_prompt(
    lugar: str,
) -> list[Message]:
    """Ficha sociodemográfica de un lugar frente a su entidad y el país.

    Args:
        lugar: Entidad, municipio o localidad, p. ej. 'Zapopan, Jalisco (municipio)'
    """
    return _prompt(f"""
Hazme el perfil sociodemográfico de **{lugar}** con la Encuesta Intercensal 2025.

1. Usa ubicar_lugar con "{lugar}". Si hay varios candidatos plausibles, elige el que coincida con la entidad y
   el nivel indicados; si sigue siendo ambiguo, pregúntame.
2. Llama a perfil_lugar con ese cvegeo (conjunto "destacados").
3. Presenta: un resumen de 3 o 4 líneas con lo más distintivo; luego una tabla por tema con el valor del lugar,
   el de su entidad y el nacional; y al final 3 hallazgos donde el lugar se aleje más del promedio nacional.""")


@mcp.prompt(name="comparar_lugares", title="Comparar lugares")
def comparar_lugares_prompt(
    lugares: str,
    tema: str = "",
) -> list[Message]:
    """Comparación lado a lado de varios lugares, en general o en un tema.

    Args:
        lugares: 2 a 10 lugares separados por punto y coma, p. ej. 'Jalisco; Nuevo León'
        tema: Tema opcional, p. ej. 'vivienda'
    """
    enfoque = f"en el tema **{tema}**" if tema else "en sus indicadores destacados"
    return _prompt(f"""
Compara estos lugares {enfoque}: {lugares}.

1. Resuelve cada lugar (separados por punto y coma) con ubicar_lugar y quédate con un cvegeo por lugar.
2. Llama a comparar_lugares con todos los cvegeo{f' y tema "{tema}"' if tema else ''}.
3. Presenta una tabla indicador × lugar y después un análisis breve: en qué destaca cada uno, las diferencias
   más grandes y cuáles diferencias no son concluyentes por baja precisión.""")


@mcp.prompt(name="ranking", title="Ranking")
def ranking_prompt(
    indicador: str,
    nivel: str = "municipio",
    entidad: str = "",
    orden: str = "mayor",
) -> list[Message]:
    """Los lugares con mayores o menores valores de un indicador.

    Args:
        indicador: Código o tema del indicador, p. ej. 'PCN_PSINDER' o 'sin derechohabiencia'
        nivel: entidad, municipio o localidad
        entidad: Limitar a una entidad, p. ej. 'Jalisco'
        orden: mayor o menor
    """
    return _prompt(f"""
Dame el ranking de {nivel}s{f' de {entidad}' if entidad else ' del país'} con {orden} valor en: **{indicador}**.

1. Si "{indicador}" no es un código (o viene como "CÓDIGO — nombre", usa el CÓDIGO), encuéntralo con
   buscar_indicadores en eic2025_localidades y elige el más adecuado; dime cuál elegiste y su definición.
{f'2. Obtén la clave de {entidad} con ubicar_lugar (su cve_ent son los dos primeros dígitos del cvegeo).' if entidad else '2. Sin filtro de entidad.'}
3. Llama a ranking con nivel "{nivel}", orden "{'asc' if orden.lower().startswith('men') else 'desc'}" y n = 10.
   Si hay municipios con precisión baja en el top, repite con excluir_baja_precision = true y muestra ambas.
4. Presenta la tabla (posición, lugar, valor, precisión) y compárala con los valores de referencia.
   Señala los municipios "censados" (CV 0) si aparecen.""")


@mcp.prompt(title="Explorar un tema")
def explorar_tema(
    tema: str,
    anio: str = "2025",
) -> list[Message]:
    """Qué mide un tema, panorama nacional y dónde destaca.

    Args:
        tema: p. ej. 'vivienda', 'desplazamiento forzado interno', 'alimentación'
        anio: 2025 o 2015
    """
    ds = "eic2015_distritos" if anio == "2015" else "eic2025_localidades"
    return _prompt(f"""
Explícame el tema **{tema}** de la Encuesta Intercensal {anio}.

1. Llama a listar_datasets para encontrar el tema en {ds} y luego a buscar_indicadores con su tema_id.
2. Resume en una lista qué mide (agrupando indicadores parecidos; no listes los {'' if anio == '2015' else 'casi '}cien códigos).
3. Llama a perfil_lugar con el cvegeo nacional ({'00000' if anio == '2015' else '000000000'}) y tema "{tema}"
   para dar el panorama nacional.
4. Elige los 2 o 3 indicadores más reveladores y usa ranking a nivel entidad para mostrar las 5 entidades
   con valores más altos y las 5 más bajas de cada uno.""", anio)


@mcp.prompt(name="brecha_genero", title="Brecha de género")
def brecha_genero_prompt(
    lugar: str,
    tema: str = "",
) -> list[Message]:
    """Diferencias entre mujeres y hombres en un lugar.

    Args:
        lugar: Entidad, municipio o localidad
        tema: Tema opcional, p. ej. 'educación'
    """
    return _prompt(f"""
Analiza las brechas entre mujeres y hombres en **{lugar}**{f' en el tema {tema}' if tema else ''} (EIC 2025).

1. Resuelve el lugar con ubicar_lugar.
2. Llama a brecha_genero con ese cvegeo{f' y tema "{tema}"' if tema else ''}.
3. Antes de interpretar cada par, lee su nombre: distingue las tasas dentro de cada sexo (comparables entre sí)
   de las composiciones de un grupo (p. ej. "% de la PEA que son mujeres"), y explica cada una como corresponde.
4. Presenta una tabla con mujeres, hombres y diferencia; destaca las 3 brechas más grandes y omite las
   pirámides de edad salvo que sean relevantes.""")


@mcp.prompt(title="Vulnerabilidad social")
def vulnerabilidad_social(
    lugar: str,
) -> list[Message]:
    """Carencias en salud, educación, alimentación, vivienda, empleo y desplazamiento.

    Args:
        lugar: Entidad, municipio o localidad
    """
    return _prompt(f"""
Haz un diagnóstico de vulnerabilidad social de **{lugar}** con la EIC 2025.

1. Resuelve el lugar con ubicar_lugar.
2. Llama a perfil_lugar con ese cvegeo y conjunto "vulnerabilidad".
3. Agrupa los indicadores en: salud, educación, alimentación, vivienda y servicios, empleo e ingresos, y
   desplazamiento forzado. Para cada grupo indica si el lugar está mejor o peor que su entidad y que el país.
4. Termina con las 3 carencias más críticas y aclara que no es una medición oficial de pobreza
   (esa la hace el CONEVAL/INEGI con otra metodología).""")


@mcp.prompt(name="evolucion_2015_2025", title="Evolución 2015 → 2025")
def evolucion_prompt(
    entidad: str = "nacional",
) -> list[Message]:
    """Qué cambió entre la Intercensal 2015 y la 2025.

    Args:
        entidad: Entidad federativa o 'nacional'
    """
    return _prompt(f"""
¿Qué cambió en **{entidad}** entre la Encuesta Intercensal 2015 y la 2025?

1. Si no es "nacional", obtén su cve_ent con ubicar_lugar (los dos primeros dígitos del cvegeo); nacional = "00".
2. Llama a evolucion_2015_2025 con ese cve_ent.
3. Presenta una tabla por tema con el valor de 2015, el de 2025 y el cambio. Marca como "sin cambio claro"
   los indicadores cuyos intervalos se traslapan, y para los de equivalencia "aproximada" menciona su nota.
4. Cierra con los 5 cambios más grandes y estadísticamente claros.""", "2015 y 2025")


@mcp.prompt(title="Ficha de distrito electoral")
def ficha_distrito(
    entidad: str,
    distrito: str,
) -> list[Message]:
    """Perfil de un distrito electoral federal con la EIC 2015.

    Args:
        entidad: Entidad federativa, p. ej. 'Jalisco'
        distrito: p. ej. 'Distrito 010'
    """
    return _prompt(f"""
Hazme la ficha del **{distrito} de {entidad}** con la Encuesta Intercensal 2015 (cartografía electoral del INE).

1. Usa ubicar_lugar con texto "{distrito}, {entidad}" y dataset "eic2015_distritos".
2. Llama a perfil_lugar con ese cvegeo y dataset "eic2015_distritos".
3. Presenta sus atributos (si es distrito indígena y su grupo de complejidad electoral), una tabla del
   distrito frente a su entidad y el país, y 3 rasgos que lo distingan.
4. Aclara que los datos son de 2015 y con la distritación vigente en ese momento.""", "2015")


# ---------- autocompletado de argumentos ----------

NIVELES = ["entidad", "municipio", "localidad"]


@mcp.completion
def completar(ref, argument, context):
    if not isinstance(ref, PromptReference):
        if argument.name == "dataset":
            return [d["id"] for d in queries.datasets() if d["id"].startswith(argument.value)]
        return None
    v, previos = argument.value, (context.arguments if context and context.arguments else {})
    match argument.name:
        case "lugar":
            return queries.sugerir_lugares(v) if v else []
        case "lugares":  # completa el último elemento de la lista separada por ';'
            *antes, actual = v.split(";")
            prefijo = "; ".join(x.strip() for x in antes)
            return [f"{prefijo}; {s}" if prefijo else s for s in queries.sugerir_lugares(actual.strip())] if actual.strip() else []
        case "entidad":
            return (["nacional"] if "nacional".startswith(v.lower()) and ref.name == "evolucion_2015_2025" else []) + \
                queries.sugerir("entidad", v)
        case "tema":
            return queries.sugerir("tema", v)
        case "indicador":
            return queries.sugerir("indicador", v)
        case "distrito":
            return queries.sugerir_distritos(previos.get("entidad", ""), v)
        case "nivel":
            return [n for n in NIVELES if n.startswith(v.lower())]
        case "orden":
            return [o for o in ("mayor", "menor") if o.startswith(v.lower())]
        case "anio":
            return [a for a in ("2025", "2015") if a.startswith(v)]
    return None


app = mcp.http_app(path="/mcp", stateless_http=True, json_response=True)

if __name__ == "__main__":
    mcp.run(show_banner=False)
