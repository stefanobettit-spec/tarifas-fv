"""
Actualiza datos/tarifas.csv con los pliegos tarifarios publicados por:
  - CGE (PDF mensual)
  - Grupo Saesa: Frontel y Saesa (ZIP mensual con Excel)

GitHub Actions lo corre solo el día 5 de cada mes (ver .github/workflows/tarifas.yml).
También se puede correr a mano:  python actualizar_tarifas.py

Qué hace, para cada distribuidora:
  1. Lista los pliegos publicados en su sitio.
  2. Compara con los meses que ya están en el CSV.
  3. Descarga y lee solo los meses que faltan (mantiene los últimos MESES_HISTORIA).
  4. Si algo falla, sigue con lo demás y al final termina con error para que GitHub
     te avise por correo. Si un sitio no entrega ningún pliego, también es error.

Opciones (para pruebas con archivos locales):
  --carpeta-cge DIR     pliegos cge_AAAA-MM.pdf/.zip
  --carpeta-saesa DIR   Excel frontel_AAAA-MM[_24T].xlsx y saesa_AAAA-MM[_24T].xlsx
  --forzar              vuelve a leer todos los meses
"""

import argparse
import datetime as dt
import pathlib
import re
import sys

from tarifas import cge, csv_tarifas, saesa

# ------------------------- CONFIGURACIÓN (editable) -------------------------
MESES_HISTORIA = 13                          # meses que se mantienen en el CSV
EMPRESAS_CGE = ["CGE DISTRIBUCIÓN"]          # el PDF de CGE trae también CONAFE, ELECDA, etc.
ARCHIVO_CSV = "datos/tarifas.csv"
# -----------------------------------------------------------------------------


def periodo_minimo(hoy):
    a, m = hoy.year, hoy.month - MESES_HISTORIA + 1
    while m <= 0:
        a, m = a - 1, m + 12
    return "%d-%02d" % (a, m)


# ----------------------------- CGE -----------------------------
def fuentes_cge(carpeta):
    if carpeta:
        return {p.stem.replace("cge_", ""): str(p)
                for p in sorted(pathlib.Path(carpeta).glob("cge_*.*"))
                if p.suffix.lower() in (".pdf", ".zip")}
    return cge.listar_pliegos()


def leer_cge(fuente, periodo):
    pdf = cge.descargar(fuente) if fuente.startswith("http") else \
        cge.abrir_pdf_bytes(pathlib.Path(fuente).read_bytes())
    registros, avisos = cge.extraer(pdf)
    registros = [r for r in registros if r["empresa"] in EMPRESAS_CGE]
    filas = csv_tarifas.a_filas("CGE", periodo, registros)
    comunas = {f["comuna"] for f in filas}
    avisos = [a for a in avisos if any((" %s " % c) in a for c in comunas)]
    return filas, avisos


# ------------------------- Grupo Saesa -------------------------
def fuentes_saesa(carpeta):
    if not carpeta:
        return saesa.listar_pliegos()
    out = {}
    for p in sorted(pathlib.Path(carpeta).glob("*.xlsx")):
        m = re.match(r"(frontel|saesa)_(\d{4}-\d{2})(_24T)?$", p.stem)
        if m:
            d = out.setdefault(m.group(2), {})
            # misma regla que con el ZIP: si hay dos versiones, la (24T) = pliego vigente
            if m.group(1).capitalize() not in d or m.group(3):
                d[m.group(1).capitalize()] = str(p)
    return out


def leer_saesa(fuente, periodo):
    if isinstance(fuente, dict):
        excels = {d: pathlib.Path(r).read_bytes() for d, r in fuente.items()}
    else:
        excels = saesa.excels_del_zip(saesa.descargar(fuente))
    filas, avisos = [], []
    for d in saesa.DISTRIBUIDORAS:
        if d not in excels:
            avisos.append("el ZIP no trae el Excel de %s" % d)
            continue
        f, a = saesa.extraer(excels[d], d, periodo)
        filas += f
        avisos += ["%s: %s" % (d, x) for x in a]
    return filas, avisos


# ------------------------------ Principal ------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--carpeta-cge")
    ap.add_argument("--carpeta-saesa")
    ap.add_argument("--forzar", action="store_true")
    args = ap.parse_args()

    desde = periodo_minimo(dt.date.today())
    existentes = [f for f in csv_tarifas.leer(ARCHIVO_CSV) if f["periodo"] >= desde]
    nuevas, errores = [], []

    fuentes = [("CGE", ["CGE"], lambda: fuentes_cge(args.carpeta_cge), leer_cge),
               ("Grupo Saesa", ["FRONTEL", "SAESA"],
                lambda: fuentes_saesa(args.carpeta_saesa), leer_saesa)]

    for nombre, distribuidoras, listar, leer in fuentes:
        try:
            publicados = {p: u for p, u in listar().items() if p >= desde}
        except Exception as e:
            errores.append("%s: no se pudo leer la página de tarifas (%s)" % (nombre, e))
            print("%s: ERROR al listar pliegos: %s" % (nombre, e))
            continue
        if not publicados:
            errores.append("%s: la página no entregó ningún pliego (¿cambió el sitio?)" % nombre)
            print("%s: ERROR, 0 pliegos encontrados" % nombre)
            continue
        completos = set() if args.forzar else {
            p for p in {f["periodo"] for f in existentes}
            if all(any(f["periodo"] == p and f["distribuidora"] == d for f in existentes)
                   for d in distribuidoras)}
        pendientes = sorted(p for p in publicados if p not in completos)
        print("%s: %d pliegos desde %s · por cargar: %s"
              % (nombre, len(publicados), desde, ", ".join(pendientes) or "ninguno"))

        for periodo in pendientes:
            try:
                filas, avisos = leer(publicados[periodo], periodo)
                if not filas:
                    raise ValueError("no se encontraron filas")
                existentes = [f for f in existentes if not (
                    f["periodo"] == periodo and f["distribuidora"] in distribuidoras)]
                nuevas += filas
                print("  %s: OK, %d filas" % (periodo, len(filas)))
                for a in avisos:
                    print("      aviso:", a)
            except Exception as e:  # un mes con problemas no detiene los demás
                errores.append("%s %s: %s" % (nombre, periodo, e))
                print("  %s: ERROR %s" % (periodo, e))

    if nuevas:
        finales = existentes + nuevas
        csv_tarifas.escribir(ARCHIVO_CSV, finales)
        print("CSV actualizado: %s (%d filas)" % (ARCHIVO_CSV, len(finales)))

    if errores:
        print("\nTERMINÓ CON ERRORES:\n  " + "\n  ".join(errores))
        sys.exit(1)
    print("Listo.")


if __name__ == "__main__":
    main()
