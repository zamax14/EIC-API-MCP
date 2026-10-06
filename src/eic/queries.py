"""Consultas de solo lectura sobre data/eic.duckdb, compartidas por la API y el MCP."""

import json
import os
import re
import unicodedata
from functools import lru_cache

import duckdb

MAX_LIMIT = 10_000
MAX_INDICADORES = 100  # tope de indicadores por perfil o comparación (el tema más grande tiene 82)

# Criterio INEGI para estimaciones por muestreo, según el coeficiente de variación.
PRECISION = """CASE WHEN e.coef_var IS NULL THEN NULL WHEN e.coef_var < 15 THEN 'alta'
                    WHEN e.coef_var <= 30 THEN 'moderada' ELSE 'baja' END"""

# Indicadores por defecto de un perfil: un vistazo a cada tema.
DESTACADOS = {
    "eic2025_localidades": [
        "POBTOT", "REL_H_M", "MEDIANA_POBTOT", "TGF", "PCN_POB_IND", "PCN_POB_AFRO", "PCN_PNACOE",
        "GRAPROES", "PCN_P15YM_AN", "PCN_P15YM_ES", "PCN_PEA", "PCN_PDESOCUP", "PCN_PSINDER",
        "PROM_OCUP", "PCN_VPH_DRENAJ", "PCN_VPH_INTER", "PCN_HOG_ALIM_N", "PCN_HOG_GOB", "PCN_DESP_INSEG",
    ],
    "eic2015_distritos": [
        "IND_001", "IND_003", "IND_004", "IND_005", "IND_141", "IND_128", "IND_126", "IND_079", "IND_083",
        "IND_095", "IND_098", "IND_119", "IND_056", "IND_058", "IND_062", "IND_065",
    ],
}

# Carencias sociales que capta la EIC 2025 (no es una medición oficial de pobreza).
VULNERABILIDAD = [
    "PCN_PSINDER", "PCN_P15YM_SE", "PCN_P15YM_AN", "PCN_P6A14_NOA", "PCN_HOG_ALIM_N", "PCN_ALIM_ADL2",
    "PCN_ALIM_MEN1", "PCN_VPH_PISOTI", "PCN_VPH_1CUART", "PCN_VPH_AGUADV", "PCN_VPH_DRENAJ", "PCN_VPH_INTER",
    "PCN_PDESOCUP", "PCN_HOG_GOB", "PCN_DESP_INSEG", "PCN_DESP_CATAS",
]


@lru_cache(maxsize=1)
def _open(path: str, mtime_ns: int) -> duckdb.DuckDBPyConnection:
    # Topes por proceso para que una consulta pesada no se coma la máquina.
    config = {"memory_limit": os.environ.get("EIC_DB_MEMORY", "512MB"),
              "threads": int(os.environ.get("EIC_DB_THREADS", "2"))}
    return duckdb.connect(path, read_only=True, config=config)


def _con() -> duckdb.DuckDBPyConnection:
    # El ETL sustituye el archivo con os.replace; si cambia el mtime se reabre la base nueva sin reiniciar.
    path = os.environ.get("EIC_DB", "data/eic.duckdb")
    return _open(path, os.stat(path).st_mtime_ns)


def _rows(sql: str, params: list | None = None) -> list[dict]:
    cur = _con().cursor()  # un cursor por llamada: la conexión no es segura entre hilos
    rel = cur.execute(sql, params or [])
    cols = [d[0] for d in rel.description]
    rows = [dict(zip(cols, r)) for r in rel.fetchall()]
    if "atributos" in cols:  # DuckDB devuelve JSON como texto
        for r in rows:
            r["atributos"] = json.loads(r["atributos"]) if r["atributos"] else None
    return rows


def _page(sql: str, params: list, order: str, limit: int, offset: int) -> dict:
    limit = max(1, min(limit, MAX_LIMIT))
    rows = _rows(f"SELECT *, count(*) OVER () AS _total FROM ({sql}) ORDER BY {order} LIMIT ? OFFSET ?",
                 [*params, limit, max(0, offset)])
    total = rows[0]["_total"] if rows else 0
    for r in rows:
        del r["_total"]
    return {"total": total, "limit": limit, "offset": offset, "items": rows}


def _texto(columna: str) -> str:
    """Filtro de búsqueda sin distinguir mayúsculas ni acentos."""
    return f"strip_accents(lower({columna})) LIKE '%' || strip_accents(lower(?)) || '%'"


def _tema(ds: str, tema: int | str | None) -> list[int] | None:
    """Acepta el id del tema o parte de su nombre (sin acentos ni mayúsculas)."""
    if tema is None or tema == "":
        return None
    if isinstance(tema, int) or str(tema).isdigit():
        return [int(tema)]
    ids = [r["id"] for r in _rows(f"SELECT id FROM tema t WHERE dataset_id = ? AND {_texto('t.nombre')}", [ds, tema])]
    if not ids:
        raise LookupError(f"tema no encontrado en {ds}: {tema}")
    return ids


def datasets() -> list[dict]:
    return _rows("SELECT * FROM dataset ORDER BY anio")


def dataset_existe(ds: str) -> bool:
    return bool(_rows("SELECT 1 FROM dataset WHERE id = ?", [ds]))


def entidades() -> list[dict]:
    return _rows("SELECT * FROM entidad ORDER BY cve_ent")


def temas(ds: str) -> list[dict]:
    return _rows("""
        SELECT t.id, t.nombre, count(i.codigo) AS indicadores
        FROM tema t LEFT JOIN indicador i ON i.dataset_id = t.dataset_id AND i.tema_id = t.id
        WHERE t.dataset_id = ? GROUP BY ALL ORDER BY t.id""", [ds])


def indicadores(ds: str, tema: int | None = None, q: str | None = None) -> list[dict]:
    # comparable_2015_2025: exacta | aproximada | no_comparable | sin_equivalente (ver evolucion)
    sql = """SELECT i.codigo, i.nombre, i.descripcion, i.mnemonico_alt, i.tema_id, t.nombre AS tema,
                    coalesce(q.tipo, 'sin_equivalente') AS comparable_2015_2025
             FROM indicador i LEFT JOIN tema t ON t.dataset_id = i.dataset_id AND t.id = i.tema_id
             LEFT JOIN equivalencia q ON i.codigo = CASE i.dataset_id WHEN 'eic2015_distritos' THEN q.codigo_2015
                                                                      ELSE q.codigo_2025 END
             WHERE i.dataset_id = ?"""
    params: list = [ds]
    if tema is not None:
        sql += " AND i.tema_id = ?"
        params.append(tema)
    if q:
        sql += f" AND ({_texto('i.codigo')} OR {_texto('i.nombre')} OR {_texto('i.descripcion')})"
        params += [q, q, q]
    return _rows(sql + " ORDER BY i.tema_id, i.codigo", params)


def _filtro_geo(nivel: str | None, cve_ent: str | None, cvegeo: list[str] | None) -> tuple[str, list]:
    sql, params = "", []
    if nivel:
        sql += " AND g.nivel = ?"
        params.append(nivel)
    if cve_ent:
        sql += " AND g.cve_ent = ?"
        params.append(cve_ent)
    if cvegeo:
        sql += " AND g.cvegeo IN (SELECT unnest(?::VARCHAR[]))"
        params.append(cvegeo)
    return sql, params


def geografias(ds: str, nivel: str | None = None, cve_ent: str | None = None, q: str | None = None,
               limit: int = 1000, offset: int = 0) -> dict:
    filtro, params = _filtro_geo(nivel, cve_ent, None)
    sql = f"SELECT g.* EXCLUDE (dataset_id) FROM geografia g WHERE g.dataset_id = ?{filtro}"
    params = [ds, *params]
    if q:
        sql += f" AND {_texto('g.nombre')}"
        params.append(q)
    return _page(sql, params, "cvegeo", limit, offset)


def datos(ds: str, indicadores: list[str], cvegeo: list[str] | None = None, nivel: str | None = None,
          cve_ent: str | None = None, limit: int = 1000, offset: int = 0) -> dict:
    filtro, params = _filtro_geo(nivel, cve_ent, cvegeo)
    sql = f"""
        SELECT e.cvegeo, g.nombre, g.nivel, g.nom_ent, e.indicador, i.nombre AS indicador_nombre,
               e.valor, e.error_estandar, e.lim_inf, e.lim_sup, e.coef_var, {PRECISION} AS precision, e.nota
        FROM estimacion e
        JOIN geografia g USING (dataset_id, cvegeo)
        JOIN indicador i ON i.dataset_id = e.dataset_id AND i.codigo = e.indicador
        WHERE e.dataset_id = ? AND e.indicador IN (SELECT unnest(?::VARCHAR[])){filtro}"""
    codigos = [i.upper() for i in indicadores]
    return _page(sql, [ds, codigos, *params], "cvegeo, indicador", limit, offset) | {
        "comparabilidad_2015_2025": comparabilidad(ds, codigos)}


AVISO_COMPARABILIDAD = ("Para comparar con el otro levantamiento usa solo evolucion_2015_2025 (o /evolucion). "
                        "No emparejes por nombre los indicadores 'sin_equivalente' ni los 'no_comparable'.")


def comparabilidad(ds: str, codigos: list[str]) -> dict:
    """Estado de cada indicador frente al otro levantamiento: exacta, aproximada, no_comparable o sin_equivalente."""
    propio, otro = ("codigo_2015", "codigo_2025") if ds == "eic2015_distritos" else ("codigo_2025", "codigo_2015")
    pares = {r[propio]: r for r in _rows(f"""SELECT {propio}, {otro} AS contraparte, tipo AS estado, nota
                                             FROM equivalencia WHERE {propio} IN (SELECT unnest(?::VARCHAR[]))""",
                                         [codigos])}
    return {"aviso": AVISO_COMPARABILIDAD,
            "indicadores": {c: {k: v for k, v in pares[c].items() if k != propio} if c in pares
                            else {"estado": "sin_equivalente"} for c in codigos}}


# ---------- análisis ----------

def _geo(ds: str, cvegeo: str) -> dict:
    rows = _rows("SELECT * EXCLUDE (dataset_id) FROM geografia WHERE dataset_id = ? AND cvegeo = ?", [ds, cvegeo])
    if not rows:
        raise LookupError(f"geografía no encontrada en {ds}: {cvegeo}")
    return rows[0]


def _seleccion(ds: str, indicadores: list[str] | None, tema: int | str | None,
               por_defecto: list[str] | None = None) -> list[dict]:
    """Metadatos de los indicadores pedidos, por códigos o por tema; si no hay ninguno, `por_defecto`."""
    sql = """SELECT i.codigo, i.nombre, t.nombre AS tema FROM indicador i
             LEFT JOIN tema t ON t.dataset_id = i.dataset_id AND t.id = i.tema_id WHERE i.dataset_id = ?"""
    codigos = [c.upper() for c in indicadores] if indicadores else None
    tema_ids = _tema(ds, tema)
    if not codigos and not tema_ids:
        codigos = por_defecto or DESTACADOS.get(ds, [])
    params: list = [ds]
    if codigos:
        sql += " AND i.codigo IN (SELECT unnest(?::VARCHAR[]))"
        params.append(codigos)
    if tema_ids:
        sql += " AND i.tema_id IN (SELECT unnest(?::INTEGER[]))"
        params.append(tema_ids)
    meta = {r["codigo"]: r for r in _rows(sql, params)}
    orden = [c for c in codigos if c in meta] if codigos else sorted(meta)  # respeta el orden pedido
    return [meta[c] for c in orden][:MAX_INDICADORES]


def _celdas(ds: str, cvegeos: list[str], codigos: list[str]) -> dict[tuple[str, str], dict]:
    rows = _rows(f"""
        SELECT e.cvegeo, e.indicador, e.valor, e.coef_var, {PRECISION} AS precision, e.nota
        FROM estimacion e WHERE e.dataset_id = ?
          AND e.cvegeo IN (SELECT unnest(?::VARCHAR[])) AND e.indicador IN (SELECT unnest(?::VARCHAR[]))""",
                 [ds, cvegeos, codigos])
    return {(r.pop("cvegeo"), r.pop("indicador")): r for r in rows}


def ranking(ds: str, indicador: str, nivel: str, cve_ent: str | None = None, orden: str = "desc",
            n: int = 10, excluir_baja_precision: bool = False) -> dict:
    """Mayores (desc) o menores (asc) valores de un indicador entre las geografías de un nivel."""
    meta = _seleccion(ds, [indicador], None)
    if not meta:
        raise LookupError(f"indicador no encontrado en {ds}: {indicador}")
    filtro, params = _filtro_geo(nivel, cve_ent, None)
    if excluir_baja_precision:
        filtro += " AND e.coef_var <= 30"
    direccion = "ASC" if orden == "asc" else "DESC"
    base = f"""FROM estimacion e JOIN geografia g USING (dataset_id, cvegeo)
               WHERE e.dataset_id = ? AND e.indicador = ? AND e.valor IS NOT NULL{filtro}"""
    params = [ds, meta[0]["codigo"], *params]
    items = _rows(f"""
        SELECT row_number() OVER (ORDER BY e.valor {direccion}, e.cvegeo) AS posicion, e.cvegeo, g.nombre,
               g.nom_ent, g.nom_mun, g.atributos, e.valor, e.coef_var, {PRECISION} AS precision
        {base} ORDER BY e.valor {direccion}, e.cvegeo LIMIT ?""", [*params, max(1, min(n, 100))])
    total = _rows(f"SELECT count(*) AS n {base}", params)[0]["n"]
    refs = _rows(f"""
        SELECT g.nivel, g.nombre, e.valor FROM estimacion e JOIN geografia g USING (dataset_id, cvegeo)
        WHERE e.dataset_id = ? AND e.indicador = ?
          AND (g.nivel = 'nacional' OR (g.nivel = 'entidad' AND g.cve_ent = ?))""", [ds, meta[0]["codigo"], cve_ent])
    return {"indicador": meta[0], "nivel": nivel, "orden": "asc" if direccion == "ASC" else "desc",
            "unidades_con_dato": total, "referencias": refs, "items": items}


def perfil(ds: str, cvegeo: str, indicadores: list[str] | None = None, tema: int | str | None = None,
           conjunto: str = "destacados") -> dict:
    """Indicadores de un lugar junto a los de su entidad y el total nacional.
    Sin indicadores ni tema usa el `conjunto`: destacados, o vulnerabilidad (solo 2025)."""
    if conjunto == "vulnerabilidad" and not indicadores and not tema:
        if ds != "eic2025_localidades":
            raise ValueError("el conjunto 'vulnerabilidad' solo existe para eic2025_localidades")
        indicadores = VULNERABILIDAD
    lugar = _geo(ds, cvegeo)
    refs = {"lugar": cvegeo}
    for r in _rows("""SELECT nivel, cvegeo FROM geografia WHERE dataset_id = ?
                      AND (nivel = 'nacional' OR (nivel = 'entidad' AND cve_ent = ?))
                      ORDER BY nivel = 'nacional'""", [ds, lugar["cve_ent"]]):
        if r["cvegeo"] != cvegeo:
            refs[r["nivel"]] = r["cvegeo"]
    meta = _seleccion(ds, indicadores, tema)
    celdas = _celdas(ds, list(refs.values()), [m["codigo"] for m in meta])
    return {
        "lugar": lugar,
        "comparado_con": {rol: _geo(ds, g)["nombre"] for rol, g in refs.items() if rol != "lugar"},
        "indicadores": [m | {rol: celdas.get((g, m["codigo"])) for rol, g in refs.items()} for m in meta],
    }


def comparar(ds: str, cvegeos: list[str], indicadores: list[str] | None = None, tema: int | str | None = None) -> dict:
    """Tabla indicador × lugar."""
    lugares = [_geo(ds, g) for g in dict.fromkeys(cvegeos)][:10]
    meta = _seleccion(ds, indicadores, tema)
    celdas = _celdas(ds, [l["cvegeo"] for l in lugares], [m["codigo"] for m in meta])
    return {
        "lugares": [{k: l[k] for k in ("cvegeo", "nombre", "nivel", "nom_ent")} for l in lugares],
        "indicadores": [m | {"valores": {l["cvegeo"]: celdas.get((l["cvegeo"], m["codigo"])) for l in lugares}}
                        for m in meta],
    }


def brecha_genero(ds: str, cvegeo: str, tema: int | str | None = None) -> dict:
    """Pares de indicadores mujeres (_F) / hombres (_M) de un lugar, con su total si existe."""
    lugar = _geo(ds, cvegeo)
    sql = """SELECT i.codigo, i.nombre, t.nombre AS tema FROM indicador i
             LEFT JOIN tema t ON t.dataset_id = i.dataset_id AND t.id = i.tema_id WHERE i.dataset_id = ?"""
    params: list = [ds]
    if tema_ids := _tema(ds, tema):
        sql += " AND i.tema_id IN (SELECT unnest(?::INTEGER[]))"
        params.append(tema_ids)
    todos = {r["codigo"]: r for r in _rows(sql, params)}
    bases = sorted(c[:-2] for c in todos if c.endswith("_F") and c[:-2] + "_M" in todos)
    codigos = [c for b in bases for c in (b, b + "_F", b + "_M") if c in todos]
    celdas = _celdas(ds, [cvegeo], codigos)
    items = []
    for b in bases:
        f, m = celdas.get((cvegeo, b + "_F")), celdas.get((cvegeo, b + "_M"))
        items.append({
            "base": b, "tema": todos[b + "_F"]["tema"],
            "mujeres": todos[b + "_F"]["nombre"], "hombres": todos[b + "_M"]["nombre"],
            "valor_mujeres": f, "valor_hombres": m, "total": celdas.get((cvegeo, b)),
            "diferencia_mujeres_menos_hombres": round(f["valor"] - m["valor"], 2)
            if f and m and f["valor"] is not None and m["valor"] is not None else None,
        })
    return {"lugar": lugar, "items": items}


LECTURA_EVOLUCION = (
    "Solo los indicadores de `items` son comparables entre 2015 y 2025; no compares ningún otro aunque tenga un "
    "nombre parecido. Los de `no_comparables` cambiaron de definición o de universo: no reportes su cambio. "
    "Si un indicador trae `advertencia`, menciónala junto a la cifra. Un cambio es estadísticamente claro solo "
    "si `intervalos_se_traslapan` es false."
)


def evolucion(cve_ent: str = "00", tema: str | None = None) -> dict:
    """Indicadores equivalentes 2015 → 2025 para el país (00) o una entidad, y los que no se deben comparar."""
    nombre = _rows("SELECT nombre FROM entidad WHERE cve_ent = ?", [cve_ent])
    if not nombre:
        raise LookupError(f"entidad no encontrada: {cve_ent}")
    filtro_tema = f" AND {_texto('t.nombre')}" if tema else ""
    extra = [tema] if tema else []
    items = _rows(f"""
        WITH v AS (
            SELECT e.dataset_id, e.indicador, e.valor, e.lim_inf, e.lim_sup, e.coef_var, {PRECISION} AS precision
            FROM estimacion e JOIN geografia g USING (dataset_id, cvegeo)
            WHERE g.cve_ent = ? AND g.nivel IN ('nacional', 'entidad'))
        SELECT q.codigo_2015, q.codigo_2025, i.nombre, t.nombre AS tema, q.tipo,
               CASE WHEN q.tipo = 'aproximada' THEN q.nota END AS advertencia,
               round(a.valor, 2) AS valor_2015, round(a.coef_var, 2) AS cv_2015, a.precision AS precision_2015,
               b.valor AS valor_2025, b.coef_var AS cv_2025, b.precision AS precision_2025,
               round(b.valor - a.valor, 2) AS cambio,
               round((b.valor - a.valor) / nullif(a.valor, 0) * 100, 1) AS cambio_relativo_pct,
               -- con intervalos al 90 % que no se traslapan, la diferencia es estadísticamente clara
               NOT (a.lim_sup < b.lim_inf OR b.lim_sup < a.lim_inf) AS intervalos_se_traslapan
        FROM equivalencia q
        JOIN indicador i ON i.dataset_id = 'eic2025_localidades' AND i.codigo = q.codigo_2025
        LEFT JOIN tema t ON t.dataset_id = i.dataset_id AND t.id = i.tema_id
        LEFT JOIN v a ON a.dataset_id = 'eic2015_distritos' AND a.indicador = q.codigo_2015
        LEFT JOIN v b ON b.dataset_id = 'eic2025_localidades' AND b.indicador = q.codigo_2025
        WHERE q.tipo <> 'no_comparable'{filtro_tema}
        ORDER BY tema, q.codigo_2025""", [cve_ent, *extra])
    no_comparables = _rows(f"""
        SELECT q.codigo_2015, q.codigo_2025, i.nombre, t.nombre AS tema, q.nota AS razon
        FROM equivalencia q
        JOIN indicador i ON i.dataset_id = 'eic2025_localidades' AND i.codigo = q.codigo_2025
        LEFT JOIN tema t ON t.dataset_id = i.dataset_id AND t.id = i.tema_id
        WHERE q.tipo = 'no_comparable'{filtro_tema} ORDER BY q.codigo_2025""", extra)
    return {"entidad": nombre[0]["nombre"], "cve_ent": cve_ent, "como_leer": LECTURA_EVOLUCION,
            "items": items, "no_comparables": no_comparables}


def equivalencias() -> list[dict]:
    return _rows("SELECT * FROM equivalencia ORDER BY codigo_2015")


# ---------- autocompletado ----------

def sugerir_lugares(texto: str, limit: int = 20) -> list[str]:
    """Etiquetas 'Nombre, Entidad (nivel)' de geografías 2025 que contienen el texto."""
    rows = _rows(f"""
        SELECT nombre, nom_ent, nivel FROM geografia g
        WHERE dataset_id = 'eic2025_localidades' AND nivel IN ('entidad', 'municipio', 'localidad')
          AND {_texto('g.nombre')}
        ORDER BY NOT starts_with(strip_accents(lower(nombre)), strip_accents(lower(?))),
                 nivel = 'localidad', length(nombre), nombre
        LIMIT ?""", [texto, texto, limit])
    return [r["nombre"] if r["nivel"] == "entidad" else f"{r['nombre']}, {r['nom_ent']} ({r['nivel']})" for r in rows]


def sugerir(tabla: str, texto: str, limit: int = 50) -> list[str]:
    """Nombres de entidades, temas o indicadores ('CÓDIGO — nombre') que contienen el texto."""
    sql = {
        "entidad": f"""SELECT nombre AS v FROM entidad e WHERE cve_ent <> '00' AND {_texto('e.nombre')}
                       ORDER BY NOT starts_with(strip_accents(lower(nombre)), strip_accents(lower(?))), cve_ent""",
        "tema": f"""SELECT DISTINCT nombre AS v FROM tema t WHERE {_texto('t.nombre')}
                    ORDER BY NOT starts_with(strip_accents(lower(v)), strip_accents(lower(?))), v""",
        "indicador": f"""SELECT codigo || ' — ' || nombre AS v FROM indicador i
                         WHERE dataset_id = 'eic2025_localidades' AND ({_texto('i.codigo')} OR {_texto('i.nombre')})
                         ORDER BY NOT starts_with(lower(codigo), lower(?)), codigo""",
    }[tabla]
    params = [texto] * sql.count("?")  # el mismo texto filtra y ordena
    return [r["v"] for r in _rows(f"{sql} LIMIT ?", [*params, limit])]


def sugerir_distritos(entidad: str, texto: str) -> list[str]:
    return [r["nombre"] for r in _rows(f"""
        SELECT g.nombre FROM geografia g JOIN entidad e USING (cve_ent)
        WHERE g.dataset_id = 'eic2015_distritos' AND g.nivel = 'distrito'
          AND {_texto('e.nombre')} AND {_texto('g.nombre')} ORDER BY g.cvegeo""", [entidad, texto])]


ALIAS = {"cdmx": "Ciudad de México", "df": "Ciudad de México", "edomex": "México", "estado de mexico": "México",
         "mexico": "Estados Unidos Mexicanos", "nacional": "Estados Unidos Mexicanos", "pais": "Estados Unidos Mexicanos"}


def ubicar(texto: str, dataset: str = "eic2025_localidades", limit: int = 10) -> list[dict]:
    """Resuelve 'Nombre', 'Nombre, Entidad' o 'Nombre, Entidad (nivel)' a geografías, coincidencia exacta primero."""
    m = re.fullmatch(r"\s*(.+?)\s*(?:,\s*(.+?))?\s*(?:\((\w+)\))?\s*", texto)
    nombre, entidad, nivel = m.groups() if m else (texto, None, None)
    clave = unicodedata.normalize("NFKD", nombre.lower()).encode("ascii", "ignore").decode()
    nombre = ALIAS.get(clave, nombre)
    sql = f"SELECT g.* EXCLUDE (dataset_id) FROM geografia g WHERE g.dataset_id = ? AND {_texto('g.nombre')}"
    params: list = [dataset, nombre]
    if entidad:
        sql += f" AND {_texto('g.nom_ent')}"
        params.append(entidad)
    if nivel:
        sql += " AND g.nivel = ?"
        params.append(nivel)
    sql += """ ORDER BY strip_accents(lower(g.nombre)) <> strip_accents(lower(?)),
                        g.nivel NOT IN ('entidad', 'municipio'), length(g.nombre) LIMIT ?"""
    return _rows(sql, [*params, nombre, limit])
