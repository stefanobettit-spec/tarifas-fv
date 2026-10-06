"""
Lector de pliegos tarifarios del Grupo Saesa (Frontel y Saesa).

Fuente: la página "Tarifas vigentes" del sitio del Grupo Saesa publica un ZIP por mes
("Tarifas de Suministro Reguladas y No Reguladas desde el 01/MM/AAAA") con los pliegos
de las cuatro distribuidoras. Dentro viene un Excel por distribuidora:
"AAAA.MM Suministro Regulado Frontel.xlsx" y "... Saesa.xlsx".

Estructura del Excel (hoja "Pub. PDF"):
  - Filas con "Comunas": encabezado con una columna por comuna y red ("Temuco - Aéreo").
    Cada comuna ocupa DOS columnas: la primera es el valor NETO y la segunda CON IVA.
  - Secciones "Tarifa BT1 ...", "Tarifa BT2 y BT3", "Tarifa BT 4.1, 4.2, 4.3", "Tarifa AT2 y AT3",
    "Tarifa AT 4.1, 4.2, 4.3": cada cargo en una fila, reconocido por su texto.
  - "Valor Energía inyectada ... BT / AT": precio de inyección (solo neto).
  - Notas con los tramos del cargo adicional de servicio público (Ley 21.472).
"""

import io
import re
import zipfile

import openpyxl
import requests

PAGINA = "https://web.gruposaesa.cl/web/frontel/pago-y-boleta/tarifas-vigentes"
NAVEGADOR = {"User-Agent": "Mozilla/5.0 (sistema-fv; lectura de tarifas publicas)"}
DISTRIBUIDORAS = ("Frontel", "Saesa")

# Secciones del Excel que se leen -> prefijo de columna en el CSV
SECCIONES = [(r"^Tarifa BT1\b", "BT1"), (r"^Tarifa BT2 y BT3", "BT23"),
             (r"^Tarifa BT 4\.1", "BT4"), (r"^Tarifa AT2 y AT3", "AT23"),
             (r"^Tarifa AT 4\.1", "AT4")]


def listar_pliegos(html=None):
    """Devuelve {"AAAA-MM": url_zip} con los ZIP mensuales publicados."""
    if html is None:
        html = requests.get(PAGINA, headers=NAVEGADOR, timeout=60).text
    out = {}
    for url, a, m in re.findall(r'href="([^"]*?(\d{4})\.(\d{2})\.zip[^"]*)"', html):
        out.setdefault("%s-%s" % (a, m), url.replace("&amp;", "&"))
    return out


def excels_del_zip(datos_zip):
    """Devuelve {distribuidora: bytes del Excel de suministro regulado}.
    Si un mes trae dos versiones (p. ej. decretos 24T y 8T), usa la que NO es retroactiva:
    la que está en la carpeta marcada con (24T), igual criterio que con CGE (pliego vigente
    publicado, no el retroactivo)."""
    z = zipfile.ZipFile(io.BytesIO(datos_zip))
    out = {}
    for d in DISTRIBUIDORAS:
        nombres = [n for n in z.namelist()
                   if re.search(r"Suministro Regulado %s\.xlsx$" % d, n)]
        if not nombres:
            continue
        nombres.sort(key=lambda n: 0 if "(24T)" in n else 1)  # ver nota arriba
        out[d] = z.read(nombres[0])
    return out


def descargar(url):
    return requests.get(url, headers=NAVEGADOR, timeout=180).content


def _texto(r):
    return next((str(c).strip() for c in r[:3] if isinstance(c, str) and c.strip()), "")


def _concepto(prefijo, lab):
    """Nombre de columna según el texto de la fila, o None si no se usa."""
    l = lab.lower()
    m = re.search(r"cargo fijo mensual (bt|at)(\d)\.?(\d)?", l)
    if m:
        return "%s%s%s_fijo" % (m.group(1).upper(), m.group(2), m.group(3) or "")
    if "cargo fijo mensual" in l:
        return "BT1_fijo" if prefijo == "BT1" else None
    if "servicio público" in l:
        return "SP_t1"
    if "sistema de transmisión" in l:
        return prefijo + "_transporte"
    if l.startswith("cargo por energía"):
        return prefijo + "_energia"
    if "compras de potencia" in l and prefijo == "BT1":
        return "BT1_compras_pot"
    m = re.search(r"factor etr (\d)", l)
    if m and prefijo == "BT1":
        return "BT1_pot_base_t" + m.group(1)
    if "parcialmente presente en punta" in l:
        return prefijo + "_PPP"
    if "presente en punta" in l:
        return prefijo + "_PP"
    if "contratada o suministrada" in l:
        return prefijo + "_dem_sum"
    if "horas de punta" in l:
        return prefijo + "_dem_punta"
    return None


def extraer(datos_xlsx, distribuidora, periodo):
    """Devuelve (filas, avisos). Una fila por comuna/red con los cargos como columnas.
    Cargos con IVA (como CGE), salvo SP_* e INY_* que son sin IVA."""
    ws = openpyxl.load_workbook(io.BytesIO(datos_xlsx), data_only=True, read_only=True)["Pub. PDF"]
    R = [list(r) for r in ws.iter_rows(values_only=True)]
    avisos = []
    enc = next((r for r in R if any(isinstance(c, str) and c.strip() == "Comunas" for c in r)), None)
    if enc is None:
        return [], ["No se encontró la fila 'Comunas': cambió el formato del Excel"]
    comunas = [(j, c.strip()) for j, c in enumerate(enc) if isinstance(c, str) and " - " in c]

    valores = {j: {} for j, _ in comunas}
    adicional_sp = []
    prefijo = None
    for r in R:
        lab = _texto(r)
        if not lab:
            continue
        if lab.startswith("Tarifa"):
            prefijo = next((p for pat, p in SECCIONES if re.search(pat, lab)), None)
            continue
        m = re.search(r"consumo mensual.*?:\s*([\d.,]+)\s*\$/kWh", " ".join(str(c) for c in r if c))
        if m:
            adicional_sp.append(float(m.group(1).replace(".", "").replace(",", ".")))
            continue
        if "inyectada" in lab:
            col = "INY_AT" if re.search(r"\bAT\b", lab) else "INY_BT"
            for j, _ in comunas:
                if isinstance(r[j], (int, float)):
                    valores[j][col] = round(r[j], 4)
            continue
        if not prefijo:
            continue
        col = _concepto(prefijo, lab)
        if not col:
            continue
        for j, _ in comunas:
            neto, con_iva = r[j], r[j + 1] if j + 1 < len(r) else None
            v = neto if col.startswith("SP_") else con_iva
            if isinstance(v, (int, float)):
                valores[j].setdefault(col, round(v, 4))

    # Tramos de servicio público: base + adicional Ley 21.472 (igual que publica CGE)
    if len(adicional_sp) == 4:
        for j, _ in comunas:
            base = valores[j].get("SP_t1")
            if base is not None:
                for k, a in enumerate(adicional_sp, start=2):
                    valores[j]["SP_t%d" % k] = round(base + a, 4)
    else:
        avisos.append("No se encontraron los 4 tramos adicionales de servicio público")

    filas = []
    for j, nombre in comunas:
        comuna, red = [s.strip() for s in nombre.split(" - ", 1)]
        v = valores[j]
        if not v.get("AT4_energia") and not v.get("BT4_energia"):
            avisos.append("%s: sin valores" % nombre)
            continue
        for k, (lo, hi) in {"AT4_energia": (40, 400), "BT4_energia": (40, 400),
                            "INY_AT": (10, 300)}.items():
            if k in v and not lo <= v[k] <= hi:
                avisos.append("%s %s = %s fuera de rango" % (nombre, k, v[k]))
        fila = {"periodo": periodo, "distribuidora": distribuidora.upper(),
                "empresa": distribuidora.upper(), "comuna": comuna, "sector": "", "red": red}
        fila.update(v)
        filas.append(fila)
    if not filas:
        avisos.append("No se encontró ninguna comuna con valores")
    return filas, avisos
