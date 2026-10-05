"""Prueba la API contra data/eic.duckdb (correr antes el ETL). Uso: python tests/test_api.py"""

from fastapi.testclient import TestClient

from eic.api import app

c = TestClient(app)
get = lambda url: c.get(url).json()

assert [d["id"] for d in get("/datasets")] == ["eic2015_distritos", "eic2025_localidades"]
assert len(get("/entidades")) == 33
assert len(get("/datasets/eic2025_localidades/temas")) == 16
assert c.get("/datasets/nope/temas").status_code == 404

# búsqueda sin acentos ni mayúsculas
assert any(i["codigo"] == "POBTOT" for i in get("/datasets/eic2025_localidades/indicadores?q=poblacion"))

g = get("/datasets/eic2025_localidades/geografias?nivel=localidad&q=tijuana")
assert g["total"] == 1 and g["items"][0]["cvegeo"] == "020040001"

d = get("/datasets/eic2025_localidades/datos?indicador=pobtot,POBFEM&cvegeo=000000000")
assert d["total"] == 2
assert {r["indicador"]: r["valor"] for r in d["items"]} == {"POBFEM": 67678902, "POBTOT": 130393389}

# paginación estable: dos páginas sin traslape y cubren el total
p1 = get("/datasets/eic2025_localidades/datos?indicador=POBTOT&nivel=municipio&cve_ent=20&limit=300")
p2 = get("/datasets/eic2025_localidades/datos?indicador=POBTOT&nivel=municipio&cve_ent=20&limit=300&offset=300")
ids = [r["cvegeo"] for r in p1["items"] + p2["items"]]
assert len(ids) == len(set(ids)) == p1["total"] == 570 and ids == sorted(ids)

assert c.get("/datasets/eic2025_localidades/datos?indicador=POBTOT&limit=999999").status_code == 422
assert c.get("/datasets/eic2025_localidades/datos?indicador=POBTOT&cve_ent=1;drop").status_code == 422
print("ok")
