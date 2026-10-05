"""Verifica la base generada por `python -m eic.etl`. Uso: python tests/test_etl.py"""

import duckdb

con = duckdb.connect("data/eic.duckdb", read_only=True)
q = lambda sql: con.execute(sql).fetchall()

assert q("SELECT dataset_id, count(*) FROM geografia GROUP BY 1 ORDER BY 1") == [
    ("eic2015_distritos", 333), ("eic2025_localidades", 2776)]
assert q("SELECT valor, error_estandar FROM estimacion "
         "WHERE dataset_id='eic2025_localidades' AND cvegeo='000000000' AND indicador='POBTOT'") == [(130393389, 498654.44)]
assert q("SELECT valor FROM estimacion WHERE dataset_id='eic2015_distritos' AND cvegeo='00000' AND indicador='IND_001'") == [(119530753,)]
assert q("SELECT count(*) FROM estimacion WHERE valor IS NOT NULL AND NOT (lim_inf <= valor AND valor <= lim_sup)") == [(0,)]
assert q("SELECT count(*) FROM estimacion WHERE dataset_id='eic2025_localidades' AND valor IS NULL AND nota IS NULL") == [(0,)]
assert q("SELECT count(*) FROM estimacion WHERE valor IS NOT NULL AND nota IS NOT NULL") == [(0,)]
assert q("SELECT count(*) FROM entidad") == [(33,)]
# toda estimación apunta a una geografía y un indicador existentes
assert q("SELECT count(*) FROM estimacion e ANTI JOIN geografia g USING (dataset_id, cvegeo)") == [(0,)]
assert q("SELECT count(*) FROM estimacion e ANTI JOIN indicador i ON i.dataset_id=e.dataset_id AND i.codigo=e.indicador") == [(0,)]
# toda geografía (salvo la nacional) tiene un padre existente
assert q("SELECT count(*) FROM geografia c ANTI JOIN geografia p "
         "ON p.dataset_id=c.dataset_id AND p.cvegeo=c.padre_cvegeo WHERE c.nivel<>'nacional'") == [(0,)]
print("ok")
