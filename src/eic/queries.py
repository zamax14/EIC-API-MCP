"""Consultas de solo lectura sobre data/eic.duckdb, compartidas por la API y el MCP."""

import os
from functools import lru_cache

import duckdb

MAX_LIMIT = 10_000


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
    return [dict(zip(cols, r)) for r in rel.fetchall()]


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
    sql = """SELECT i.codigo, i.nombre, i.descripcion, i.mnemonico_alt, i.tema_id, t.nombre AS tema
             FROM indicador i LEFT JOIN tema t ON t.dataset_id = i.dataset_id AND t.id = i.tema_id
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
               e.valor, e.error_estandar, e.lim_inf, e.lim_sup, e.coef_var, e.nota
        FROM estimacion e
        JOIN geografia g USING (dataset_id, cvegeo)
        JOIN indicador i ON i.dataset_id = e.dataset_id AND i.codigo = e.indicador
        WHERE e.dataset_id = ? AND e.indicador IN (SELECT unnest(?::VARCHAR[])){filtro}"""
    return _page(sql, [ds, [i.upper() for i in indicadores], *params], "cvegeo, indicador", limit, offset)
