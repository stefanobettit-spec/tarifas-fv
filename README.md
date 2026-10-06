# Sistema FV – Tarifas automáticas

Descarga cada mes los pliegos tarifarios de CGE y los deja en un CSV que la plantilla
Excel de presupuestos lee con Power Query (igual que la Calculadora FV).

**Estado:** CGE listo (últimos 13 meses) · Frontel y Saesa pendientes.

## El archivo que usa el Excel

`datos/tarifas_cge.csv` — una fila por **periodo + comuna + sector + red**, una columna por cargo.

| Columnas | Contenido |
|---|---|
| `periodo` | AAAA-MM, vigente desde el día 1 de ese mes |
| `distribuidora`, `empresa`, `comuna`, `sector`, `red` | Identifican la fila del pliego (el sector sale de la boleta, ej. "Villarrica Stxe-18-a" → `STxE-18-A`) |
| `BT1_*` | BT1: fijo, transporte, energía, compras de potencia, potencia base tramos 1–6 |
| `BT2_fijo`, `BT3_fijo`, `BT23_*` | BT2/BT3: transporte, energía, potencia PP y PPP ($/kW/mes) |
| `BT41_fijo`, `BT42_fijo`, `BT43_fijo`, `BT4_*` | BT4.x: transporte, energía, demanda suministrada, demanda en punta |
| `AT2_fijo`, `AT3_fijo`, `AT23_*` | AT2/AT3 (igual que BT2/BT3) |
| `AT41_fijo`, `AT42_fijo`, `AT43_fijo`, `AT4_*` | AT4.x (igual que BT4.x) |
| `SP_t1` … `SP_t5` | Cargo por servicio público por tramo (**sin IVA**) |
| `INY_BT`, `INY_AT` | Precio de inyección (**sin IVA**) |

Todos los demás valores van **con IVA**, tal como los publica CGE. La plantilla calcula el neto.

## Cómo se actualiza

- **Automático:** GitHub Actions corre `actualizar_tarifas.py` el **día 5 de cada mes** (13:00 UTC).
  Si hay un pliego nuevo lo agrega al CSV; si no, no cambia nada.
- **A mano:** pestaña **Actions** → **Actualizar tarifas** → **Run workflow**.
- **Si falla:** GitHub te envía un correo. Los meses que sí se pudieron leer quedan guardados igual.
  Revisa el registro (clic en la ejecución fallida → "Actualizar tarifas") y busca las líneas `ERROR` o `aviso`.

## Archivos

| Archivo | Para qué sirve |
|---|---|
| `actualizar_tarifas.py` | Programa principal. Bloque **CONFIGURACIÓN** editable (meses de historia, empresas) |
| `tarifas/cge.py` | Lee la web y los PDF de CGE. Contiene el mapa de qué número es cada cargo |
| `tarifas/csv_tarifas.py` | Arma el CSV y define los nombres de columna |
| `.github/workflows/tarifas.yml` | La tarea programada de GitHub Actions |
| `requirements.txt` | Librerías que instala GitHub |

## Reglas

- Este repositorio es **público**: aquí solo van tarifas públicas y código.
  **Nunca** subir boletas, datos de clientes ni precios de la empresa.
- No cambiar los nombres de columna del CSV sin actualizar la plantilla Excel.
