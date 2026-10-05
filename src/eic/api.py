"""API pública de solo lectura de la Encuesta Intercensal. Uso: uvicorn eic.api:app"""

import os
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Path, Query
from fastapi.middleware.cors import CORSMiddleware

from eic import queries

app = FastAPI(
    title="EIC API",
    description="Datos de la Encuesta Intercensal 2015 y 2025 (INEGI). Fuente: INEGI, https://www.inegi.org.mx/inegi/terminos.html",
    version="0.1.0",
    root_path=os.environ.get("EIC_ROOT_PATH", ""),  # prefijo público detrás del proxy, p. ej. /api
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"])

Nivel = Literal["nacional", "entidad", "municipio", "localidad", "resto_localidades", "distrito"]
CveEnt = Annotated[str | None, Query(pattern=r"^\d{2}$", description="Clave de entidad, 00-32")]
Limit = Annotated[int, Query(ge=1, le=queries.MAX_LIMIT)]
Offset = Annotated[int, Query(ge=0)]


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
