"""API pública de solo lectura de la Encuesta Intercensal. Uso: uvicorn eic.api:app"""

import os
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Path, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from eic import queries

app = FastAPI(
    title="EIC API",
    description="Datos de la Encuesta Intercensal 2015 y 2025 (INEGI). Fuente: INEGI, https://www.inegi.org.mx/inegi/terminos.html",
    version="0.1.0",
    root_path=os.environ.get("EIC_ROOT_PATH", ""),  # prefijo público detrás del proxy, p. ej. /api
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"])


@app.exception_handler(LookupError)
def no_encontrado(_: Request, e: LookupError):
    return JSONResponse({"detail": str(e)}, status_code=404)


@app.exception_handler(ValueError)
def invalido(_: Request, e: ValueError):
    return JSONResponse({"detail": str(e)}, status_code=422)

Nivel = Literal["nacional", "entidad", "municipio", "localidad", "resto_localidades", "distrito"]
CveEnt = Annotated[str | None, Query(pattern=r"^\d{2}$", description="Clave de entidad, 00-32")]
Limit = Annotated[int, Query(ge=1, le=queries.MAX_LIMIT)]
Offset = Annotated[int, Query(ge=0)]
Tema = Annotated[str | None, Query(description="Id o nombre del tema, p. ej. 'vivienda'")]
Indicadores = Annotated[str | None, Query(description="Códigos separados por coma; sin ellos ni tema, los destacados")]


def dataset(dataset_id: Annotated[str, Path(description="eic2015_distritos | eic2025_localidades")]) -> str:
    if not queries.dataset_existe(dataset_id):
        raise HTTPException(404, f"dataset no encontrado: {dataset_id}")
    return dataset_id


def lista(csv: str | None) -> list[str] | None:
    return [x.strip() for x in csv.split(",") if x.strip()] if csv else None


@app.get("/datasets")
def get_datasets():
    return queries.datasets()


@app.get("/entidades")
def get_entidades():
    return queries.entidades()


@app.get("/datasets/{dataset_id}/temas")
def get_temas(dataset_id: str):
    return queries.temas(dataset(dataset_id))


@app.get("/datasets/{dataset_id}/indicadores")
def get_indicadores(dataset_id: str, tema: int | None = None,
                    q: Annotated[str | None, Query(description="Busca en código, nombre y descripción")] = None):
    return queries.indicadores(dataset(dataset_id), tema, q)


@app.get("/datasets/{dataset_id}/geografias")
def get_geografias(dataset_id: str, nivel: Nivel | None = None, cve_ent: CveEnt = None,
                   q: Annotated[str | None, Query(description="Busca en el nombre")] = None,
                   limit: Limit = 1000, offset: Offset = 0):
    return queries.geografias(dataset(dataset_id), nivel, cve_ent, q, limit, offset)


@app.get("/datasets/{dataset_id}/datos")
def get_datos(dataset_id: str,
              indicador: Annotated[str, Query(description="Códigos separados por coma, p. ej. POBTOT,POBFEM")],
              cvegeo: Annotated[str | None, Query(description="Claves geográficas separadas por coma")] = None,
              nivel: Nivel | None = None, cve_ent: CveEnt = None,
              limit: Limit = 1000, offset: Offset = 0):
    return queries.datos(dataset(dataset_id), lista(indicador), lista(cvegeo), nivel, cve_ent, limit, offset)


# ---------- análisis ----------

@app.get("/ubicar")
def get_ubicar(q: Annotated[str, Query(min_length=2, description="'Zapopan', 'Juárez, Chihuahua', 'CDMX'…")],
               dataset_id: Annotated[str, Query(alias="dataset")] = "eic2025_localidades"):
    return queries.ubicar(q, dataset(dataset_id))


@app.get("/datasets/{dataset_id}/ranking")
def get_ranking(dataset_id: str, indicador: str, nivel: Nivel = "municipio", cve_ent: CveEnt = None,
                orden: Literal["desc", "asc"] = "desc", n: Annotated[int, Query(ge=1, le=100)] = 10,
                excluir_baja_precision: bool = False):
    return queries.ranking(dataset(dataset_id), indicador, nivel, cve_ent, orden, n, excluir_baja_precision)


@app.get("/datasets/{dataset_id}/perfil/{cvegeo}")
def get_perfil(dataset_id: str, cvegeo: str, indicador: Indicadores = None, tema: Tema = None,
               conjunto: Literal["destacados", "vulnerabilidad"] = "destacados"):
    return queries.perfil(dataset(dataset_id), cvegeo, lista(indicador), tema, conjunto)


@app.get("/datasets/{dataset_id}/comparar")
def get_comparar(dataset_id: str,
                 cvegeo: Annotated[str, Query(description="2 a 10 claves separadas por coma")],
                 indicador: Indicadores = None, tema: Tema = None):
    claves = lista(cvegeo) or []
    if not 2 <= len(claves) <= 10:
        raise HTTPException(422, "cvegeo debe traer entre 2 y 10 claves")
    return queries.comparar(dataset(dataset_id), claves, lista(indicador), tema)


@app.get("/datasets/{dataset_id}/brecha-genero/{cvegeo}")
def get_brecha_genero(dataset_id: str, cvegeo: str, tema: Tema = None):
    return queries.brecha_genero(dataset(dataset_id), cvegeo, tema)


@app.get("/evolucion")
def get_evolucion(cve_ent: Annotated[str, Query(pattern=r"^\d{2}$", description="00 = nacional")] = "00",
                  tema: Annotated[str | None, Query(description="Nombre del tema, p. ej. 'vivienda'")] = None):
    return queries.evolucion(cve_ent, tema)


@app.get("/equivalencias")
def get_equivalencias():
    return queries.equivalencias()
