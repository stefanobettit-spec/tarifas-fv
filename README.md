# Sistema FV – Tarifas automáticas

Descarga cada mes los pliegos tarifarios de **CGE, Frontel y Saesa** y los deja en un CSV que
la plantilla Excel de presupuestos lee con Power Query (igual que la Calculadora FV).

| Distribuidora | Fuente | Historial disponible |
|---|---|---|
| CGE | PDF mensual en cge.cl | desde oct-2025 (últimos 13 meses) |
| Frontel y Saesa | ZIP mensual (Excel) en el sitio del Grupo Saesa | desde jul-2026 (el sitio nuevo solo publica desde ahí) |

## El archivo que usa el Excel

`datos/tarifas.csv` — una fila por **periodo + distribuidora + comuna + sector + red**, una columna por cargo.

| Columnas | Contenido |
|---|---|
| `periodo` | AAAA-MM, vigente desde el día 1 de ese mes |
| `distribuidora` | CGE, FRONTEL o SAESA |
| `empresa`, `comuna`, `sector`, `red` | Identifican la fila del pliego. **CGE** usa sector (ej. boleta "Villarrica Stxe-18-a" → `STxE-18-A`). **Frontel/Saesa** no usan sector: va vacío y se busca por comuna + red (`Aéreo`) |
| `BT1_*` | BT1: fijo, transporte, energía, compras de potencia, potencia base tramos 1–6 |
| `BT2_fijo`, `BT3_fijo`, `BT23_*` | BT2/BT3: transporte, energía, potencia PP y PPP ($/kW/mes) |
| `BT41_fijo`, `BT42_fijo`, `BT43_fijo`, `BT4_*` | BT4.x: transporte, energía, demanda suministrada, demanda en punta |
| `AT2_fijo`, `AT3_fijo`, `AT23_*` | AT2/AT3 (igual que BT2/BT3) |
| `AT41_fijo`, `AT42_fijo`, `AT43_fijo`, `AT4_*` | AT4.x (igual que BT4.x) |
| `SP_t1` … `SP_t5` | Cargo por servicio público por tramo, base + adicional Ley 21.472 (**sin IVA**) |
| `INY_BT`, `INY_AT` | Precio de inyección (**sin IVA**) |

Todos los demás valores van **con IVA**. La plantilla calcula el neto.

**Retroactivos:** se usa siempre el pliego vigente publicado, no el retroactivo
(CGE: se ignoran los "Tarifas Retroactivas…"; Grupo Saesa: si un mes trae versión 24T y 8T, se usa la 24T).

## Cómo se actualiza

- **Automático:** GitHub Actions corre `actualizar_tarifas.py` el **día 5 de cada mes** (13:00 UTC).
  Agrega los meses nuevos que encuentre; si no hay nada nuevo, no cambia nada.
- **A mano:** pestaña **Actions** → **Actualizar tarifas** → **Run workflow**.
- **Si falla:** GitHub te envía un correo. Lo que sí se pudo leer queda guardado igual.
  También falla (a propósito) si un sitio no entrega ningún pliego, para detectar cambios en las páginas.
  Abre la ejecución fallida → "Actualizar tarifas" y busca las líneas `ERROR` o `aviso`.

## Archivos

| Archivo | Para qué sirve |
|---|---|
| `actualizar_tarifas.py` | Programa principal. Bloque **CONFIGURACIÓN** editable |
| `tarifas/cge.py` | Lee la web y los PDF de CGE |
| `tarifas/saesa.py` | Lee la web, los ZIP y los Excel del Grupo Saesa (Frontel y Saesa) |
| `tarifas/csv_tarifas.py` | Arma el CSV y define los nombres de columna |
| `.github/workflows/tarifas.yml` | La tarea programada de GitHub Actions |
| `requirements.txt` | Librerías que instala GitHub |

## Reglas

- Este repositorio es **público**: aquí solo van tarifas públicas y código.
  **Nunca** subir boletas, datos de clientes ni precios de la empresa.
- No cambiar los nombres de columna del CSV sin actualizar la plantilla Excel.
