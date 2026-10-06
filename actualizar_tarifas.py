"""
Actualiza datos/tarifas_cge.csv con los pliegos publicados por CGE.

GitHub Actions lo corre solo el día 5 de cada mes (ver .github/workflows/tarifas.yml).
También se puede correr a mano:  python actualizar_tarifas.py

Qué hace:
  1. Lista los pliegos "vigentes a partir del 1 de ..." publicados en cge.cl.
  2. Compara con los meses que ya están en el CSV.
  3. Descarga y lee solo los meses que faltan (mantiene los últimos MESES_HISTORIA).
  4. Si un mes falla, sigue con los demás y al final termina con error para que
     GitHub te avise por correo.

Opciones:
  --carpeta DIR   lee los pliegos desde archivos locales cge_AAAA-MM.pdf/.zip (pruebas)
  --forzar        vuelve a leer todos los meses
"""

import argparse
import datetime as dt
import pathlib
import sys

from tarifas import cge, csv_tarifas

# ------------------------- CONFIGURACIÓN (editable) -------------------------
MESES_HISTORIA = 13                          # meses que se mantienen en el CSV
EMPRESAS_A_GUARDAR = ["CGE DISTRIBUCIÓN"]    # el PDF trae también CONAFE, ELECDA, etc.
ARCHIVO_CSV = "datos/tarifas_cge.csv"
# -----------------------------------------------------------------------------


def periodo_minimo(hoy):
    a, m = hoy.year, hoy.month - MESES_HISTORIA + 1
    while m <= 0:
        a, m = a - 1, m + 12
    return "%d-%02d" % (a, m)


def fuentes(carpeta):
    if carpeta:
        return {p.stem.replace("cge_", ""): str(p)
                for p in sorted(pathlib.Path(carpeta).glob("cge_*.*"))
                if p.suffix.lower() in (".pdf", ".zip")}
    return cge.listar_pliegos()


def leer_pdf(fuente):
    if fuente.startswith("http"):
        return cge.descargar(fuente)
    return cge.abrir_pdf_bytes(pathlib.Path(fuente).read_bytes())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--carpeta")
    ap.add_argument("--forzar", action="store_true")
    args = ap.parse_args()

    desde = periodo_minimo(dt.date.today())
    existentes = [f for f in csv_tarifas.leer(ARCHIVO_CSV) if f["periodo"] >= desde]
    ya = set() if args.forzar else {f["periodo"] for f in existentes}
    publicados = {p: u for p, u in fuentes(args.carpeta).items() if p >= desde}
    pendientes = sorted(p for p in publicados if p not in ya)
    print("CGE: %d pliegos desde %s · por cargar: %s"
          % (len(publicados), desde, ", ".join(pendientes) or "ninguno"))

    nuevas, errores = [], []
    for periodo in pendientes:
        try:
            registros, avisos = cge.extraer(leer_pdf(publicados[periodo]))
            registros = [r for r in registros if r["empresa"] in EMPRESAS_A_GUARDAR]
            filas = csv_tarifas.a_filas("CGE", periodo, registros)
            if not filas:
                raise ValueError("no se encontraron filas de %s" % EMPRESAS_A_GUARDAR)
            nuevas += filas
            print("  %s: OK, %d filas (comuna/sector/red)" % (periodo, len(filas)))
            comunas = {f["comuna"] for f in filas}
            for a in avisos:
                if any((" %s " % c) in a for c in comunas):
                    print("      aviso:", a)
        except Exception as e:  # un mes con problemas no detiene los demás
            errores.append("%s: %s" % (periodo, e))
            print("  %s: ERROR %s" % (periodo, e))

    if nuevas:
        cargados = {f["periodo"] for f in nuevas}
        finales = [f for f in existentes if f["periodo"] not in cargados] + nuevas
        csv_tarifas.escribir(ARCHIVO_CSV, finales)
        print("CSV actualizado: %s (%d filas)" % (ARCHIVO_CSV, len(finales)))

    if errores:
        print("\nTERMINÓ CON ERRORES:\n  " + "\n  ".join(errores))
        sys.exit(1)
    print("Listo.")


if __name__ == "__main__":
    main()
