# ENFRENTAMIENTOS_SIBA
Genera imágenes para enfrentamientos deportivos

---

## Descripción

Aplicación de escritorio (Tkinter) que lee un Excel con enfrentamientos de fútbol, descarga los logos de los equipos automáticamente desde Wikipedia/Wikimedia (preferentemente en SVG) o TheSportsDB como fallback, y genera imágenes de enfrentamientos en tres resoluciones usando un fondo personalizado. Al finalizar genera un reporte Excel con el detalle de resultados.

### Resoluciones generadas
| Resolución | Orientación |
|---|---|
| 1920×1080 | Landscape HD |
| 3840×2160 | Landscape 4K |
| 480×720 | Portrait / Story |

---

## Estructura del proyecto

```
ENFRENTAMIENTOS_SIBA/
  app.py              # Interfaz Tkinter (punto de entrada)
  generator.py        # Lógica de composición de imágenes
  logo_fetcher.py     # Descarga y caché de logos
  match_loader.py     # Lectura del Excel de enfrentamientos
  normalizer.py       # Normalización de nombres de equipos
  reporter.py         # Generación de reporte Excel/CSV
  requirements.txt    # Dependencias Python
  cache/
    logos/            # Caché de logos descargados
      wiki/
      sportsdb/
      manual/
  output/             # Imágenes y reportes generados (se crea al generar)
    YYYYMMDD-HHMMSS/
      images/
      report.xlsx
      report.csv
  assets/
    fonts/            # Fuentes opcionales (Roboto-BlackItalic.ttf, etc.)
```

---

## Requisitos

- Python 3.10 o superior
- Las dependencias listadas en `requirements.txt`
- **Cairo** (para renderizado de SVG):
  - **Windows**: instala [GTK for Windows Runtime](https://github.com/nicowillis/gtk-for-windows) o usa `pip install cairosvg` que incluye binarios.
  - **macOS**: `brew install cairo`
  - **Linux**: `sudo apt install libcairo2`

---

## Instalación

```bash
# 1. Clonar el repositorio
git clone https://github.com/EleNanoAsterix/ENFRENTAMIENTOS_SIBA.git
cd ENFRENTAMIENTOS_SIBA

# 2. Crear entorno virtual (recomendado)
python -m venv .venv
source .venv/bin/activate     # Linux/macOS
.venv\Scripts\activate        # Windows

# 3. Instalar dependencias
pip install -r requirements.txt
```

---

## Uso

```bash
python app.py
```

### Flujo paso a paso

1. **Cargar Excel** — Haz clic en *"📂 Cargar Excel (.xlsx)"* y selecciona tu archivo.  
   El Excel debe tener al menos las columnas:
   ```
   EQUIPO A | PAIS EQUIPO A | EQUIPO B | PAIS EQUIPO B
   ```
   Los encabezados se detectan de forma flexible (sin distinción de mayúsculas ni espacios extra).

2. **Configurar fondo**:
   - *"Mismo fondo para todos"* → elige una imagen que se usará en todos los enfrentamientos.
   - *"Fondo por enfrentamiento"* → selecciona la fila en la tabla y usa *"🖼 Asignar fondo a fila seleccionada"*.

3. **Descargar logos** — Haz clic en *"🔍 Buscar/Descargar logos"*.  
   La app intentará (en orden):
   1. Wikipedia/Wikimedia (SVG preferido)
   2. TheSportsDB (PNG, clave pública gratuita)
   Si ya existen en caché (`cache/logos/`), los reutiliza.

4. **Resolver manualmente** — Si algún logo quedó como `NOT_FOUND` o `LOW_QUALITY`, selecciona la fila y haz clic en *"✏️ Resolver logos manualmente"* para seleccionar un archivo local.

5. **Generar imágenes** — Haz clic en *"▶ Generar imágenes"*.  
   Los resultados se guardan en `output/YYYYMMDD-HHMMSS/images/`.

6. **Ver reporte** — Haz clic en *"📊 Ver / Abrir reporte"* para abrir `report.xlsx` con:
   - **GENERADAS**: enfrentamientos exitosos y rutas de salida.
   - **FALLIDAS**: errores y motivos.
   - **LOGOS**: detalle de fuente, formato y calidad de cada logo.

### Opciones avanzadas

| Opción | Descripción |
|---|---|
| Contorno blanco en logos | Agrega un contorno blanco alrededor de los escudos |
| Grosor del contorno | Número de píxeles del contorno (escala relativa a 1920px) |
| Auto-mejorar fondo | Ajusta contraste y saturación del fondo automáticamente |

---

## Formato del Excel de entrada

| EQUIPO A | PAIS EQUIPO A | EQUIPO B | PAIS EQUIPO B |
|---|---|---|---|
| River Plate | Argentina | Boca Juniors | Argentina |
| Real Madrid | España | Barcelona | España |
| Bayern Munich | Alemania | Borussia Dortmund | Alemania |

> **Nota**: la columna país es opcional pero mejora la búsqueda de logos.

---

## Caché de logos

Los logos descargados se guardan en `cache/logos/<fuente>/<pais>/<equipo>.<ext>`.  
Junto a cada logo se guarda un archivo `.json` con metadatos (fuente, URL de origen, tamaño validado).

Para forzar la re-descarga de logos, elimina las carpetas dentro de `cache/logos/`.

---

## Solución de problemas

| Problema | Solución |
|---|---|
| `ModuleNotFoundError: cairosvg` | `pip install cairosvg` y asegura que Cairo esté instalado en el sistema |
| Logos con `LOW_QUALITY` | Usa *"Resolver logos manualmente"* para proveer un archivo de mayor resolución |
| Error al abrir Excel | Verifica que el archivo sea `.xlsx` y no esté abierto en otro programa |
| Sin logos encontrados | Prueba normalizando el nombre del equipo en el Excel (sin puntos, sin sufijos raros) |

---

## Licencia

MIT
