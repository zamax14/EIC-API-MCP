"""Prueba las tools del MCP en memoria contra data/eic.duckdb. Uso: python tests/test_mcp.py"""

import asyncio

from fastmcp import Client

from eic.mcp_server import mcp


async def main():
    async with Client(mcp) as c:
        tools = {t.name: t for t in await c.list_tools()}
        assert set(tools) == {"listar_datasets", "buscar_indicadores", "buscar_geografias", "obtener_datos"}
        assert all(t.annotations.readOnlyHint for t in tools.values())

        call = lambda name, **kw: c.call_tool(name, kw)
        ds = (await call("listar_datasets")).structured_content["result"]
        assert len(ds) == 2 and len(next(d for d in ds if d["id"] == "eic2025_localidades")["temas"]) == 16

        inds = (await call("buscar_indicadores", dataset="eic2025_localidades", texto="poblacion")).structured_content["result"]
        assert any(i["codigo"] == "POBTOT" for i in inds)

        geo = (await call("buscar_geografias", dataset="eic2025_localidades", texto="tijuana", nivel="localidad")).structured_content
        assert geo["items"][0]["cvegeo"] == "020040001"

        d = (await call("obtener_datos", dataset="eic2025_localidades", indicadores=["POBTOT"], nivel="entidad")).structured_content
        assert d["total"] == 32 and all(f["precision"] for f in d["items"])

        # sin filtro geográfico se rechaza; límites del esquema se validan
        assert (await c.call_tool("obtener_datos", {"dataset": "eic2025_localidades", "indicadores": ["POBTOT"]},
                                  raise_on_error=False)).is_error
        assert (await c.call_tool("obtener_datos", {"dataset": "eic2025_localidades", "indicadores": ["POBTOT"],
                                                    "nivel": "entidad", "limite": 100000}, raise_on_error=False)).is_error
    print("ok")


asyncio.run(main())
