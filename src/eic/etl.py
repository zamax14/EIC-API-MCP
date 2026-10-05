"""ETL de la Encuesta Intercensal (INEGI): descarga los paquetes de datos abiertos,
los normaliza a formato largo y los carga en una base DuckDB.

Uso: python -m eic.etl [--offline] [--db data/eic.duckdb]
"""

import argparse
import csv
import io
import json
import os
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import httpx
import pyarrow as pa

DATA = Path("data")
RAW = DATA / "raw"
SCHEMA = Path(__file__).with_name("schema.sql")


# ---------- extract ----------

def download(url: str, offline: bool) -> Path:
    """Descarga el zip a data/raw; se salta si ya existe con el mismo tamaño."""
    dest = RAW / url.rsplit("/", 1)[1]
    if offline:
        if not dest.exists():
            raise SystemExit(f"--offline: falta {dest}")
        return dest
    with httpx.Client(follow_redirects=True, timeout=120) as client:
        remote = int(client.head(url).headers.get("content-length", -1))
        if dest.exists() and dest.stat().st_size == remote:
            print(f"  sin cambios: {dest.name}")
            return dest
        print(f"  descargando {url}")
        RAW.mkdir(parents=True, exist_ok=True)
        part = dest.with_suffix(".part")
        with client.stream("GET", url) as r, part.open("wb") as f:
            r.raise_for_status()
            for chunk in r.iter_bytes():
                f.write(chunk)
        part.replace(dest)
    return dest


def read_member(z: zipfile.ZipFile, suffix: str, encoding: str) -> str:
    name = next(n for n in z.namelist() if n.endswith(suffix))
    return z.read(name).decode(encoding)


def parse_metadata(text: str) -> dict:
    meta = {}
    for line in text.splitlines():
        if m := re.match(r"^(\w+):\s*(.+)$", line):
            meta.setdefault(m[1].lower(), m[2].strip())
    return meta


def num(v: str) -> float | None:
    try:
        return float(v)
    except ValueError:
        return None


# ---------- transform: EIC 2025, localidades de 50 000 y más ----------

ESTIMADORES_2025 = {
    "Valor": "valor",
    "Error estándar": "error_estandar",
    "Límite inferior de confianza": "lim_inf",
    "Límite superior de confianza": "lim_sup",
    "Coeficiente de variación": "coef_var",
}
# Sufijos en NOM_MUN, según las notas del diccionario.
MARCAS_MUN = {"**": "muestra_insuficiente", "*": "censado"}


def nivel_2025(ent: str, mun: str, loc: str) -> tuple[str, str | None]:
    if ent == "00":
        return "nacional", None
    if mun == "000":
        return "entidad", "000000000"
    if mun == "997":
        return "resto_localidades", f"{ent}0000000"
    if loc == "0000":
        return "municipio", f"{ent}0000000"
    return "localidad", f"{ent}{mun}0000"


def parse_2025(z: zipfile.ZipFile, ds: str) -> dict:
    rows = list(csv.DictReader(io.StringIO(read_member(z, "conjunto_de_datos/conjunto_datos_eic2025_105.csv", "latin-1"))))
    cols = list(rows[0])
    indicadores = cols[cols.index("ESTIMADOR") + 1:]

    geos, est = {}, {}
    for r in rows:
        g = r["CVEGEO"]
        if g not in geos:
            nom_mun, attrs = r["NOM_MUN"], {}
            for marca, significado in MARCAS_MUN.items():
                if nom_mun.endswith(marca):
                    nom_mun, attrs["marca_municipio"] = nom_mun[: -len(marca)], significado
                    break
            nivel, padre = nivel_2025(r["CVE_ENT"], r["CVE_MUN"], r["CVE_LOC"])
            nombre = {"nacional": r["NOM_ENT"], "entidad": r["NOM_ENT"], "municipio": nom_mun}.get(nivel, r["NOM_LOC"])
            geos[g] = dict(dataset_id=ds, cvegeo=g, nivel=nivel, cve_ent=r["CVE_ENT"], cve_mun=r["CVE_MUN"],
                           cve_loc=r["CVE_LOC"], cve_distrito=None, nombre=nombre, nom_ent=r["NOM_ENT"],
                           nom_mun=nom_mun, padre_cvegeo=padre, atributos=json.dumps(attrs) if attrs else None)
        campo = ESTIMADORES_2025[r["ESTIMADOR"]]
        for ind in indicadores:
            e = est.setdefault((g, ind), {"nota": None})
            e[campo] = num(r[ind])
            if campo == "valor" and e["valor"] is None:
                e["nota"] = r[ind] or None  # MI | NA

    temas, inds, tema_actual = {}, [], None
    for x in csv.reader(io.StringIO(read_member(z, "diccionario_datos_eic2025_105.csv", "utf-8"))):
        if not x or not x[0]:
            continue
        if x[0].isupper() and not any(x[1:]):  # fila de sección: POBLACIÓN, FECUNDIDAD…
            tema_actual = x[0].strip()
        elif x[0].strip().isdigit() and x[3] in indicadores:
            tid = temas.setdefault(tema_actual, len(temas) + 1)
            inds.append(dict(dataset_id=ds, codigo=x[3], nombre=x[1], descripcion=x[2], tema_id=tid, mnemonico_alt=None))

    return dict(
        geografia=list(geos.values()),
        estimacion=[dict(dataset_id=ds, cvegeo=g, indicador=i, **e) for (g, i), e in est.items()],
        indicador=inds,
        tema=[dict(dataset_id=ds, id=i, nombre=n) for n, i in temas.items()],
        metadata=parse_metadata(read_member(z, "metadatos_eic2025_105.txt", "utf-8")),
    )


# ---------- transform: EIC 2015, distritos electorales federales ----------

def parse_2015(z: zipfile.ZipFile, ds: str) -> dict:
    cat = {(r["cve_ent"], r["cve_distrito"]): r
           for r in csv.DictReader(io.StringIO(read_member(z, "cat_distritos.csv", "utf-8-sig")))}
    rows = list(csv.DictReader(io.StringIO(read_member(z, "conjunto_de_datos/eiege_eic_2015.csv", "utf-8-sig"))))
    indicadores = [c for c in rows[0] if re.fullmatch(r"IND_\d+", c)]

    geos, est = [], []
    for r in rows:
        ent, dist = r["CVE_ENT"], r["CVE_DISTRITO"]
        c = cat[(ent, dist)]
        if ent == "00":
            nivel, padre, nombre = "nacional", None, c["desc_ent"]
        elif dist == "000":
            nivel, padre, nombre = "entidad", "00000", c["desc_ent"]
        else:
            nivel, padre, nombre = "distrito", f"{ent}000", c["desc_distrito"]
        mi = r["MI"] == "*"
        attrs = {k: v for k, v in [("muestra_insuficiente", mi or None), ("indigena", r["Indigena"] or None),
                                   ("complejidad", r["Complejidad"] or None)] if v}
        g = ent + dist
        geos.append(dict(dataset_id=ds, cvegeo=g, nivel=nivel, cve_ent=ent, cve_mun=None, cve_loc=None,
                         cve_distrito=dist, nombre=nombre, nom_ent=c["desc_ent"], nom_mun=None,
                         padre_cvegeo=padre, atributos=json.dumps(attrs) if attrs else None))
        for ind in indicadores:
            valor = num(r[ind])
            # Se usan los sufijos de columna: el diccionario trae invertidas las
            # descripciones de _LI y _LS, pero en los datos LI < valor < LS.
            est.append(dict(dataset_id=ds, cvegeo=g, indicador=ind, valor=valor,
                            error_estandar=num(r[f"{ind}_EE"]), lim_inf=num(r[f"{ind}_LI"]),
                            lim_sup=num(r[f"{ind}_LS"]), coef_var=num(r[f"{ind}_CV"]),
                            nota="MI" if valor is None and mi else None))

    inds = [dict(dataset_id=ds, codigo=x["indicador"].upper(), nombre=x["descripcion"], descripcion=x["descripcion"],
                 tema_id=None, mnemonico_alt=x["mnemonico"])
            for x in csv.DictReader(io.StringIO(read_member(z, "fd_eiege_eic_2015.csv", "utf-8-sig")))
            if x["indicador"].upper() in indicadores]

    return dict(geografia=geos, estimacion=est, indicador=inds, tema=[],
                metadata=parse_metadata(read_member(z, "metadatos_eiege_eic_2015.txt", "utf-8-sig")))


# ---------- fuentes ----------
# Agregar un paquete de INEGI = agregar una entrada aquí (con su parser).

SOURCES = [
    dict(id="eic2015_distritos", anio=2015, geografia="Nacional, entidad y distrito electoral federal (INE)",
         url="https://www.inegi.org.mx/contenidos/programas/intercensal/2015/datosabiertos/eiege_eic_2015_csv.zip",
         parser=parse_2015),
    dict(id="eic2025_localidades", anio=2025,
         geografia="Nacional, entidad, municipio y localidades de 50 000 y más habitantes",
         url="https://www.inegi.org.mx/contenidos/programas/eic/2025/datosabiertos/conjunto_de_datos_eic2025_105_csv.zip",
         parser=parse_2025),
]


# ---------- load ----------

def insert(con: duckdb.DuckDBPyConnection, table: str, rows: list[dict]) -> None:
    if rows:
        con.register("_rows", pa.Table.from_pylist(rows))
        con.execute(f"INSERT INTO {table} BY NAME SELECT * FROM _rows")
        con.unregister("_rows")


def run(db: Path, offline: bool) -> None:
    tmp = db.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    db.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(tmp))
    con.execute(SCHEMA.read_text())
    entidades = {}
    now = datetime.now(timezone.utc)

    for src in SOURCES:
        print(f"[{src['id']}]")
        with zipfile.ZipFile(download(src["url"], offline)) as z:
            data = src["parser"](z, src["id"])
        meta = data.pop("metadata")
        insert(con, "dataset", [dict(id=src["id"], anio=src["anio"], titulo=meta["title"], geografia=src["geografia"],
                                     fuente_url=src["url"], licencia=meta.get("license"),
                                     fecha_modificado=meta.get("modified"), descargado_en=now)])
        for table, rows in data.items():
            insert(con, table, rows)
            print(f"  {table}: {len(rows):,}")
        # El dataset más reciente (último en SOURCES) define el nombre oficial.
        entidades |= {g["cve_ent"]: g["nom_ent"] for g in data["geografia"] if g["nivel"] in ("nacional", "entidad")}

    insert(con, "entidad", [dict(cve_ent=k, nombre=v) for k, v in sorted(entidades.items())])

    parquet = db.parent / "parquet"
    parquet.mkdir(exist_ok=True)
    for (t,) in con.execute("SELECT table_name FROM information_schema.tables").fetchall():
        con.execute(f"COPY {t} TO '{parquet / t}.parquet' (FORMAT parquet)")
    con.close()
    os.replace(tmp, db)  # swap atómico: quien lea la base nunca ve una carga a medias
    print(f"ok -> {db}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--offline", action="store_true", help="usar los zips ya presentes en data/raw")
    p.add_argument("--db", type=Path, default=DATA / "eic.duckdb")
    a = p.parse_args()
    run(a.db, a.offline)


if __name__ == "__main__":
    main()
