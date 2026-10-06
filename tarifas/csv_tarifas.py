"""
Convierte los valores extraídos del pliego en el CSV que lee la plantilla Excel.

Formato: una fila por periodo + comuna + sector + red, y una columna por cargo.
Los nombres de columna son cortos y fijos (la plantilla los busca por nombre):

  BT1_fijo, BT1_transporte, BT1_energia, BT1_compras_pot, BT1_pot_base_t1..t6
  BT2_fijo, BT3_fijo, BT23_transporte, BT23_energia, BT23_PP, BT23_PPP
  BT41_fijo, BT42_fijo, BT43_fijo, BT4_transporte, BT4_energia, BT4_dem_sum, BT4_dem_punta
  AT2_fijo, AT3_fijo, AT23_transporte, AT23_energia, AT23_PP, AT23_PPP
  AT41_fijo, AT42_fijo, AT43_fijo, AT4_transporte, AT4_energia, AT4_dem_sum, AT4_dem_punta
  SP_t1..SP_t5   (cargo por servicio público por tramo, sin IVA)
  INY_BT, INY_AT (precio de inyección, sin IVA)

Todos los cargos van TAL COMO LOS PUBLICA CGE: con IVA, salvo SP_* e INY_*.
"""

import csv
import os

PREFIJO = {"BT1": "BT1", "BT2": "BT2", "BT3": "BT3", "BT2/BT3": "BT23",
           "BT4.1": "BT41", "BT4.2": "BT42", "BT4.3": "BT43", "BT4": "BT4",
           "AT2": "AT2", "AT3": "AT3", "AT2/AT3": "AT23",
           "AT4.1": "AT41", "AT4.2": "AT42", "AT4.3": "AT43", "AT4": "AT4"}
CONCEPTO = {"Cargo fijo": "fijo", "Transporte": "transporte", "Energía": "energia",
            "Compras de potencia": "compras_pot",
            "Potencia presente en punta (PP)": "PP",
            "Potencia parcialmente presente en punta (PPP)": "PPP",
            "Demanda máxima suministrada": "dem_sum", "Demanda máxima en punta": "dem_punta"}
CLAVE = ["periodo", "distribuidora", "empresa", "comuna", "sector", "red"]


def columna(r):
    """Nombre de columna para un registro, o None si no se publica."""
    c, t = r["concepto"], r["tarifa"]
    if t == "Inyección":
        return "INY_BT" if c.endswith("BT") else "INY_AT"
    if c.startswith("SP tramo"):
        return "SP_t" + c.split()[-1]
    if t not in PREFIJO:
        return None  # p. ej. el primer bloque de la página AT, que el modelo no usa
    if c.startswith("Potencia base tramo"):
        return "%s_pot_base_t%s" % (PREFIJO[t], c.split()[-1])
    if c not in CONCEPTO:
        return None  # p. ej. el primer bloque de la página AT, que el modelo no usa
    return "%s_%s" % (PREFIJO[t], CONCEPTO[c])


def a_filas(distribuidora, periodo, registros):
    filas = {}
    for r in registros:
        col = columna(r)
        if not col:
            continue
        k = (periodo, distribuidora, r["empresa"], r["comuna"], r["sector"], r["red"])
        fila = filas.setdefault(k, dict(zip(CLAVE, k)))
        fila.setdefault(col, r["valor"])  # SP se repite en cada bloque: basta el primero
    return list(filas.values())


def leer(ruta):
    if not os.path.exists(ruta):
        return []
    with open(ruta, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def escribir(ruta, filas):
    """Escribe ordenado (periodo más reciente primero) con columnas fijas."""
    cols = list(CLAVE)
    for f in filas:
        cols += [c for c in f if c not in cols]
    fijas = CLAVE + sorted(c for c in cols if c not in CLAVE)
    filas = sorted(filas, key=lambda f: (f["distribuidora"], f["comuna"], f["sector"], f["red"]))
    filas = sorted(filas, key=lambda f: f["periodo"], reverse=True)
    os.makedirs(os.path.dirname(ruta) or ".", exist_ok=True)
    with open(ruta, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fijas, lineterminator="\n")
        w.writeheader()
        w.writerows(filas)
