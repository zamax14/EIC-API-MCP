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
# análisis
r = get("/datasets/eic2025_localidades/ranking?indicador=PCN_PSINDER&nivel=municipio&cve_ent=14&n=5")
valores = [i["valor"] for i in r["items"]]
assert r["unidades_con_dato"] == 125 and valores == sorted(valores, reverse=True) and len(valores) == 5
assert {x["nivel"] for x in r["referencias"]} == {"entidad", "nacional"}
asc = get("/datasets/eic2025_localidades/ranking?indicador=PCN_PSINDER&nivel=entidad&orden=asc&n=32")
assert [i["valor"] for i in asc["items"]] == sorted(i["valor"] for i in asc["items"]) and asc["unidades_con_dato"] == 32

p = get("/datasets/eic2025_localidades/perfil/141200000")
assert p["comparado_con"] == {"entidad": "Jalisco", "nacional": "Estados Unidos Mexicanos"}
assert all({"lugar", "entidad", "nacional"} <= set(i) for i in p["indicadores"])
assert len(get("/datasets/eic2025_localidades/perfil/141200000?conjunto=vulnerabilidad")["indicadores"]) == 16
assert c.get("/datasets/eic2025_localidades/perfil/nope").status_code == 404

cmp = get("/datasets/eic2025_localidades/comparar?cvegeo=140000000,190000000&tema=desplazamiento")
assert len(cmp["indicadores"]) == 2 and all(set(i["valores"]) == {"140000000", "190000000"} for i in cmp["indicadores"])

b = get("/datasets/eic2025_localidades/brecha-genero/000000000?tema=educacion")
g = next(i for i in b["items"] if i["base"] == "GRAPROES")
assert g["diferencia_mujeres_menos_hombres"] == round(g["valor_mujeres"]["valor"] - g["valor_hombres"]["valor"], 2)

e = get("/evolucion?cve_ent=14")
assert e["entidad"] == "Jalisco" and len(e["items"]) == 29
assert all(i["valor_2015"] is not None and i["valor_2025"] is not None for i in e["items"])
assert get("/ubicar?q=cdmx")[0]["cvegeo"] == "090000000"
assert len(get("/equivalencias")) == 29
assert c.get("/datasets/eic2025_localidades/ranking?indicador=POBTOT&n=101").status_code == 422
print("ok")
