"""Verifica la base generada por `python -m eic.etl`. Uso: python tests/test_etl.py"""

import os
import pathlib

import duckdb

con = duckdb.connect(os.environ.get("EIC_DB", "data/eic.duckdb"), read_only=True)
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
# temas: todo indicador 2015 tiene uno con el mismo nombre que en 2025
assert q("SELECT count(*) FROM indicador WHERE tema_id IS NULL") == [(0,)]
assert q("""SELECT count(*) FROM tema a WHERE dataset_id = 'eic2015_distritos'
            AND nombre NOT IN (SELECT nombre FROM tema WHERE dataset_id = 'eic2025_localidades')""") == [(0,)]
# equivalencias: códigos existentes y un par exacto con valores nacionales coherentes
assert q("SELECT tipo, count(*) FROM equivalencia GROUP BY 1 ORDER BY 1") == [('aproximada', 10), ('exacta', 23), ('no_comparable', 5)]
assert q("""SELECT count(*) FROM equivalencia q
            ANTI JOIN indicador a ON a.dataset_id = 'eic2015_distritos' AND a.codigo = q.codigo_2015""") == [(0,)]
assert q("""SELECT count(*) FROM equivalencia q
            ANTI JOIN indicador b ON b.dataset_id = 'eic2025_localidades' AND b.codigo = q.codigo_2025""") == [(0,)]
assert q("SELECT count(*) FROM equivalencia WHERE tipo IN ('aproximada', 'no_comparable') AND nota IS NULL") == [(0,)]
assert q("""SELECT b.valor / a.valor BETWEEN 1.0 AND 1.2 FROM equivalencia q
            JOIN estimacion a ON a.dataset_id = 'eic2015_distritos' AND a.cvegeo = '00000' AND a.indicador = q.codigo_2015
            JOIN estimacion b ON b.dataset_id = 'eic2025_localidades' AND b.cvegeo = '000000000' AND b.indicador = q.codigo_2025
            WHERE q.codigo_2025 = 'POBTOT'""") == [(True,)]  # la población creció, pero menos de 20 %
# descargas para pandas: ancho (una fila por lugar) y largo (una fila por estimación)
d = pathlib.Path(os.environ.get("EIC_DB", "data/eic.duckdb")).parent / "descargas"
ancho = lambda f: con.execute(f"SELECT count(*), (SELECT count(*) FROM (DESCRIBE SELECT * FROM '{d / f}')) FROM '{d / f}'").fetchone()
assert ancho("eic2025.csv") == (2776, 5 + 341) and ancho("eic2015.csv") == (333, 6 + 107)
assert q(f"SELECT count(*), count(precision) FROM '{d}/eic2025_completo.csv.gz'") == [(946616, 946616)]
assert q(f"SELECT count(*) FROM '{d}/eic2015_completo.csv.gz'") == [(35631,)]
assert q(f"SELECT count(*) FROM '{d}/indicadores.csv'") == [(448,)]
print("ok")
