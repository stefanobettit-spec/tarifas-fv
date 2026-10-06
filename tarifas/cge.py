"""
Lector de pliegos tarifarios de CGE Distribución.

Qué hace este archivo:
  1. listar_pliegos()  -> busca en la web de CGE los pliegos publicados, mes por mes.
  2. descargar()       -> baja un pliego (PDF, o ZIP con un PDF adentro).
  3. extraer()         -> lee el PDF y devuelve, para cada comuna, todos los cargos
                          de las tarifas BT y AT, más el precio de inyección.

El PDF de CGE trae una fila por comuna/sector/red con 38 números (páginas BT y AT)
o 39 números (páginas de inyección). La posición de cada número dice qué cargo es.
Ese "mapa de posiciones" está en BLOQUES_BT, BLOQUES_AT e INYECCION más abajo.
"""

import io
import re
import unicodedata
import zipfile

import pdfplumber
import requests

URL_PAGINA = ("https://www.cge.cl/informacion-comercial/tarifas-y-procesos-tarifarios/"
              "tarifa-de-suministro/")
EMPRESAS = ("CGE DISTRIBUCIÓN", "CONAFE", "ELECDA", "ELIQSA", "EMELARI", "EMELAT")
MESES = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
         "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11,
         "diciembre": 12}
NAVEGADOR = {"User-Agent": "Mozilla/5.0 (sistema-fv; lectura de tarifas publicas)"}

# ---------------------------------------------------------------------------
# Mapa de posiciones (base 0) dentro de la fila de 38 números.
# Cada entrada: (tarifa, concepto, unidad).  SP = cargo por servicio público.
# ---------------------------------------------------------------------------
_SP = [("SP tramo %d" % i, "$/kWh") for i in range(1, 6)]


def _bloque(tarifas_fijo, con_potencia):
    """Arma la lista de conceptos de un bloque de tarifas."""
    b = [(t, "Cargo fijo", "$/cliente/mes") for t in tarifas_fijo]
    b += [("*", "Transporte", "$/kWh")]
    b += [("*", c, u) for c, u in _SP]
    b += [("*", "Energía", "$/kWh")]
    b += con_potencia
    return b


BLOQUES_BT = (
    # Posiciones 0-14: BT1
    _bloque(["BT1"], [("BT1", "Compras de potencia", "$/kWh")] +
            [("BT1", "Potencia base tramo %d" % i, "$/kWh") for i in range(1, 7)])
    # Posiciones 15-25: BT2 y BT3
    + _bloque(["BT2", "BT3"], [("BT2/BT3", "Potencia presente en punta (PP)", "$/kW/mes"),
                               ("BT2/BT3", "Potencia parcialmente presente en punta (PPP)", "$/kW/mes")])
    # Posiciones 26-37: BT4.1, BT4.2, BT4.3
    + _bloque(["BT4.1", "BT4.2", "BT4.3"], [("BT4", "Demanda máxima suministrada", "$/kW/mes"),
                                           ("BT4", "Demanda máxima en punta", "$/kW/mes")])
)

BLOQUES_AT = (
    # Posiciones 0-14: primer bloque de la página AT (no lo usa el modelo; se guarda igual)
    _bloque(["AT-bloque1"], [("AT-bloque1", "Compras de potencia", "$/kWh")] +
            [("AT-bloque1", "Potencia base tramo %d" % i, "$/kWh") for i in range(1, 7)])
    + _bloque(["AT2", "AT3"], [("AT2/AT3", "Potencia presente en punta (PP)", "$/kW/mes"),
                               ("AT2/AT3", "Potencia parcialmente presente en punta (PPP)", "$/kW/mes")])
    + _bloque(["AT4.1", "AT4.2", "AT4.3"], [("AT4", "Demanda máxima suministrada", "$/kW/mes"),
                                           ("AT4", "Demanda máxima en punta", "$/kW/mes")])
)
assert len(BLOQUES_BT) == 38 and len(BLOQUES_AT) == 38

# En las páginas de inyección solo usamos los dos últimos números.
INYECCION = [("Inyección", "Precio inyección BT", "$/kWh"),
             ("Inyección", "Precio inyección AT", "$/kWh")]

# Rangos razonables: si un valor cae fuera, algo cambió en el PDF y se avisa.
RANGOS = {"Cargo fijo": (300, 5000), "Transporte": (1, 100), "Energía": (50, 400),
          "Precio inyección BT": (20, 300), "Precio inyección AT": (20, 300)}


# ---------------------------------------------------------------------------
# 1. Listar los pliegos publicados
# ---------------------------------------------------------------------------
def listar_pliegos(html=None):
    """Devuelve {"AAAA-MM": url} con los pliegos 'vigentes a partir del 1 de ...'.
    Excluye retroactivos y pliegos de precio traspasable."""
    if html is None:
        html = requests.get(URL_PAGINA, headers=NAVEGADOR, timeout=60).text
    pliegos = {}
    for url, texto in re.findall(r'<a[^>]+href="([^"]+\.(?:pdf|zip))"[^>]*>(.*?)</a>', html,
                                 flags=re.I | re.S):
        texto = re.sub(r"<[^>]+>|\s+", " ", texto)
        if "retroactiv" in texto.lower() or "traspasable" in texto.lower():
            continue
        m = re.search(r"vigentes? a partir del 1 de (\w+) (?:de )?(\d{4})", texto, re.I)
        if m and m.group(1).lower() in MESES:
            periodo = "%s-%02d" % (m.group(2), MESES[m.group(1).lower()])
            pliegos.setdefault(periodo, url)  # la web lista primero el más reciente
    return pliegos


# ---------------------------------------------------------------------------
# 2. Descargar
# ---------------------------------------------------------------------------
def descargar(url):
    """Baja el archivo y devuelve los bytes del PDF (si viene en ZIP, lo abre)."""
    datos = requests.get(url, headers=NAVEGADOR, timeout=120).content
    return abrir_pdf_bytes(datos)


def abrir_pdf_bytes(datos):
    if datos[:2] == b"PK":  # es un ZIP
        with zipfile.ZipFile(io.BytesIO(datos)) as z:
            pdfs = [n for n in z.namelist() if n.lower().endswith(".pdf")]
            if len(pdfs) != 1:
                raise ValueError("El ZIP trae %d PDF, se esperaba 1" % len(pdfs))
            return z.read(pdfs[0])
    return datos


# ---------------------------------------------------------------------------
# 3. Extraer valores del PDF
# ---------------------------------------------------------------------------
def numero_cl(txt):
    """'1.064,51' -> 1064.51"""
    return float(txt.replace(".", "").replace(",", "."))


def _es_numero(txt):
    return re.fullmatch(r"\d{1,3}(\.\d{3})*,\d+", txt) is not None


def _tipo_pagina(texto):
    if "TARIFA BT1" in texto:
        return "BT"
    if "TARIFAS AT2" in texto:
        return "AT"
    if "Inyección Energía" in texto:
        return "INY"
    return None  # páginas de tarifas horarias/residenciales: no se usan


def _filas(pagina):
    """Agrupa las palabras del PDF por línea (misma altura) y las ordena de izquierda a derecha.
    x_tolerance=1 evita que números vecinos se peguen (ej. '17,1711.064,51')."""
    lineas = {}
    for w in pagina.extract_words(x_tolerance=1):
        lineas.setdefault(round(w["top"]), []).append(w)
    for _, ws in sorted(lineas.items()):
        yield [w["text"] for w in sorted(ws, key=lambda w: w["x0"])]


def _separar_encabezado(palabras):
    """Separa 'CGE DISTRIBUCIÓN Temuco STxE-9-A Aéreo' en empresa, comuna, sector y red."""
    texto = " ".join(palabras)
    empresa = next((e for e in EMPRESAS if texto.startswith(e)), None)
    if not empresa:
        return None
    resto = texto[len(empresa):].strip().split(" ")
    # El sector tiene forma STx?-n-X (ej. STxE-9-A, STxD-3-S2)
    i = next((k for k, p in enumerate(resto) if re.fullmatch(r"ST\w*-\d+-\w+", p)), None)
    if i is None:
        return None
    return {"empresa": empresa, "comuna": " ".join(resto[:i]), "sector": resto[i],
            "red": " ".join(resto[i + 1:])}


def extraer(pdf_bytes):
    """Devuelve (registros, avisos).
    registros: lista de dicts con empresa, comuna, sector, red, tarifa, concepto, unidad,
               valor (tal como viene publicado), incluye_iva y valor_neto (sin IVA).
    avisos:    lista de textos con filas que no calzaron o valores fuera de rango."""
    registros, avisos = [], []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for n, pagina in enumerate(pdf.pages, start=1):
            tipo = _tipo_pagina(pagina.extract_text(x_tolerance=1) or "")
            if not tipo:
                continue
            for palabras in _filas(pagina):
                corte = next((k for k, p in enumerate(palabras) if _es_numero(p)), None)
                if corte is None:
                    continue
                enc = _separar_encabezado(palabras[:corte])
                if not enc:
                    continue
                nums = [numero_cl(p) for p in palabras[corte:] if _es_numero(p)]

                if tipo in ("BT", "AT"):
                    if len(nums) != 38:
                        avisos.append("Pág %d: %s %s tiene %d números (se esperaban 38)"
                                      % (n, enc["comuna"], enc["sector"], len(nums)))
                        continue
                    mapa = BLOQUES_BT if tipo == "BT" else BLOQUES_AT
                    pares = zip(mapa, nums)
                else:  # INY: solo los dos últimos
                    if len(nums) < 3:
                        continue
                    pares = zip(INYECCION, nums[-2:])

                for k, ((tarifa, concepto, unidad), valor) in enumerate(pares):
                    if tarifa == "*":  # cargo común del bloque: se asigna al nombre del bloque
                        tarifa = _nombre_bloque(mapa, k)
                    # IVA: todo incluye IVA salvo servicio público e inyección
                    con_iva = not (concepto.startswith("SP ") or tarifa == "Inyección")
                    reg = dict(enc, grupo=tipo, tarifa=tarifa, concepto=concepto,
                               unidad=unidad, valor=valor, incluye_iva=con_iva,
                               valor_neto=round(valor / 1.19, 4) if con_iva else valor)
                    registros.append(reg)
                    lim = RANGOS.get(concepto)
                    if lim and not (lim[0] <= valor <= lim[1]):
                        avisos.append("Pág %d: %s %s %s %s = %s fuera de rango %s"
                                      % (n, enc["comuna"], enc["sector"], tarifa, concepto,
                                         valor, lim))
    if not registros:
        avisos.append("No se encontró ninguna fila: probablemente cambió el formato del PDF")
    return registros, avisos


def _nombre_bloque(mapa, k):
    """Para cargos comunes (transporte, SP, energía) devuelve 'BT2/BT3', 'BT4', etc."""
    # busca hacia atrás el/los cargos fijos del bloque al que pertenece la posición k
    fijos = []
    for j in range(k, -1, -1):
        t, c, _ = mapa[j]
        if c == "Cargo fijo":
            fijos.insert(0, t)
        elif fijos:
            break
    base = {("BT1",): "BT1", ("BT2", "BT3"): "BT2/BT3", ("BT4.1", "BT4.2", "BT4.3"): "BT4",
            ("AT-bloque1",): "AT-bloque1", ("AT2", "AT3"): "AT2/AT3",
            ("AT4.1", "AT4.2", "AT4.3"): "AT4"}
    return base.get(tuple(fijos), "/".join(fijos))


def normalizar(txt):
    """Para comparar comunas sin tildes ni mayúsculas."""
    txt = unicodedata.normalize("NFD", txt).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", txt).strip().lower()
