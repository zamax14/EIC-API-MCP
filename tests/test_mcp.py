"""Prueba el MCP en memoria contra data/eic.duckdb. Uso: python tests/test_mcp.py"""

import asyncio

from fastmcp import Client
from mcp_types import PromptReference, ResourceTemplateReference

from eic.mcp_server import mcp

PROMPTS = {
    "guia_rapida": {},
    "perfil_lugar": {"lugar": "Zapopan, Jalisco (municipio)"},
    "comparar_lugares": {"lugares": "Jalisco; Nuevo León", "tema": "vivienda"},
    "ranking": {"indicador": "PCN_PSINDER", "entidad": "Jalisco", "orden": "menor"},
    "explorar_tema": {"tema": "vivienda", "anio": "2015"},
    "brecha_genero": {"lugar": "Oaxaca"},
    "vulnerabilidad_social": {"lugar": "Chiapas"},
    "evolucion_2015_2025": {"entidad": "Jalisco"},
    "ficha_distrito": {"entidad": "Jalisco", "distrito": "Distrito 010"},
}


async def main():
    async with Client(mcp) as c:
        tools = {t.name: t for t in await c.list_tools()}
        assert set(tools) == {"listar_datasets", "ubicar_lugar", "buscar_indicadores", "buscar_geografias",
                              "obtener_datos", "perfil_lugar", "comparar_lugares", "ranking", "brecha_genero",
                              "evolucion_2015_2025"}
        assert all(t.annotations.read_only_hint and t.title for t in tools.values())

        call = lambda name, **kw: c.call_tool(name, kw)
        ds = (await call("listar_datasets")).structured_content["result"]
        assert len(ds) == 2 and len(next(d for d in ds if d["id"] == "eic2025_localidades")["temas"]) == 16
        assert any(i["codigo"] == "POBTOT" for i in
                   (await call("buscar_indicadores", dataset="eic2025_localidades", texto="poblacion")).structured_content["result"])
        geo = (await call("buscar_geografias", dataset="eic2025_localidades", texto="tijuana", nivel="localidad")).structured_content
        assert geo["items"][0]["cvegeo"] == "020040001"
        d = (await call("obtener_datos", dataset="eic2025_localidades", indicadores=["POBTOT"], nivel="entidad")).structured_content
        assert d["total"] == 32 and all(f["precision"] for f in d["items"])

        # tools de análisis
        assert (await call("ubicar_lugar", texto="Zapopan")).structured_content["result"][0]["cvegeo"] == "141200000"
        p = (await call("perfil_lugar", cvegeo="141200000", conjunto="vulnerabilidad")).structured_content
        assert len(p["indicadores"]) == 16 and p["comparado_con"]["entidad"] == "Jalisco"
        cmp = (await call("comparar_lugares", cvegeos=["140000000", "190000000"], tema="vivienda")).structured_content
        assert len(cmp["lugares"]) == 2 and cmp["indicadores"]
        r = (await call("ranking", indicador="PCN_PSINDER", cve_ent="14", n=3)).structured_content
        assert len(r["items"]) == 3 and r["items"][0]["posicion"] == 1
        assert (await call("brecha_genero", cvegeo="000000000", tema="educacion")).structured_content["items"]
        ev = (await call("evolucion_2015_2025", cve_ent="14")).structured_content
        assert len(ev["items"]) == 33 and len(ev["no_comparables"]) == 5

        # errores legibles y validación del esquema
        for name, args in [("obtener_datos", {"dataset": "eic2025_localidades", "indicadores": ["POBTOT"]}),
                           ("obtener_datos", {"dataset": "eic2025_localidades", "indicadores": ["POBTOT"],
                                              "nivel": "entidad", "limite": 100000}),
                           ("evolucion_2015_2025", {"cve_ent": "99"}),
                           ("perfil_lugar", {"cvegeo": "14010", "dataset": "eic2015_distritos", "conjunto": "vulnerabilidad"})]:
            assert (await c.call_tool(name, args, raise_on_error=False)).is_error, name

        # prompts: todos renderizan y cierran citando la fuente
        assert {p.name for p in await c.list_prompts()} == set(PROMPTS)
        for name, args in PROMPTS.items():
            texto = (await c.get_prompt(name, args)).messages[0].content.text
            assert "Fuente: INEGI" in texto and all(v.split(";")[0] in texto for v in args.values()), name

        # resources
        assert {str(r.uri) for r in await c.list_resources()} == {"eic://guia", "eic://entidades", "eic://equivalencias"}
        assert "Criterio INEGI" in (await c.read_resource("eic://guia"))[0].text
        assert "`IND_001`" in (await c.read_resource("eic://datasets/eic2015_distritos/diccionario"))[0].text

        # autocompletado
        complete = lambda prompt, name, value, ctx=None: c.complete(
            PromptReference(type="ref/prompt", name=prompt), {"name": name, "value": value}, ctx)
        assert (await complete("perfil_lugar", "lugar", "zapo")).values[0] == "Zapopan, Jalisco (municipio)"
        assert (await complete("comparar_lugares", "lugares", "Jalisco; nuevo l")).values[0] == "Jalisco; Nuevo León"
        assert len((await complete("ficha_distrito", "distrito", "", {"entidad": "Jalisco"})).values) == 20
        assert (await complete("ranking", "indicador", "pobtot")).values[0].startswith("POBTOT")
        assert (await complete("evolucion_2015_2025", "entidad", "na")).values[0] == "nacional"
        tpl = ResourceTemplateReference(type="ref/resource", uri="eic://datasets/{dataset}/diccionario")
        assert (await c.complete(tpl, {"name": "dataset", "value": "eic2015"})).values == ["eic2015_distritos"]
    print("ok")


asyncio.run(main())
