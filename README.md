# SIBA – Generador de Enfrentamientos por Lotes

Genera imágenes de enfrentamientos deportivos a partir de un listado Excel,
descargando logos automáticamente desde Wikipedia y TheSportsDB.

## Requisitos del sistema

| Software | Versión mínima |
|---|---|
| Python | 3.8 |
| Cairo (para SVG) | cualquier versión reciente |

**Instalar Cairo:**
- **Ubuntu/Debian:** `sudo apt-get install libcairo2`
- **macOS:** `brew install cairo`
- **Windows:** instalar [GTK+ for Windows Runtime](https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases)

## Instalación

```bash
pip install -r requirements.txt
```

## Uso rápido

```bash
python app.py
```

### Flujo de trabajo

1. **Cargar Excel (.xlsx)**  
   Haz clic en *Seleccionar Excel (.xlsx)*.  
   El archivo debe tener exactamente las columnas (mayúsculas, en ese orden):

   | Columna | Descripción |
   |---|---|
   | `EQUIPO A` | Nombre del equipo local |
   | `PAIS EQUIPO A` | País del equipo local |
   | `EQUIPO B` | Nombre del equipo visitante |
   | `PAIS EQUIPO B` | País del equipo visitante |

2. **Configurar el fondo**  
   - *Mismo fondo para todos* → elige una imagen JPG/PNG que se aplicará a todos.  
   - *Fondo por enfrentamiento* → selecciona una fila en la tabla y usa el botón **Elegir Fondo**.

3. **Descargar logos**  
   Haz clic en **🔍 Buscar / Descargar Logos**.  
   La app intenta, en orden:
   1. Caché local (`cache/logos/`)
   2. Wikipedia en inglés (SVG preferido, PNG como respaldo)
   3. Wikipedia en español (misma preferencia)
   4. TheSportsDB (PNG, endpoint público gratuito)

   Criterios de calidad:
   - Raster (PNG/JPG): mínimo **400 × 400 px**
   - SVG: se valida renderizando a 1 024 × 1 024 px

4. **Resolver logos manualmente** (si alguno no se encontró)  
   Selecciona el enfrentamiento en la tabla y haz clic en **🖼 Resolver Logo Manual**.  
   Puedes elegir un archivo SVG, PNG, JPG o JPEG de tu disco.  
   El archivo se copia automáticamente a `cache/logos/manual/`.

5. **Opciones de generación**
   - ☑ *Contorno blanco en logos* + control de grosor
   - ☑ *Mejorar automáticamente imagen de fondo*

6. **Generar imágenes**  
   Haz clic en **▶ GENERAR TODO**.  
   Se crean tres resoluciones por enfrentamiento:

   | Resolución | Uso típico |
   |---|---|
   | 1920 × 1080 px | Full HD |
   | 3840 × 2160 px | 4K / UHD |
   | 480 × 720 px | Redes sociales (vertical) |

7. **Resultados**  
   - Imágenes: `output/YYYYMMDD-HHMMSS/images/`  
   - Reporte Excel: `output/YYYYMMDD-HHMMSS/report.xlsx`

   El reporte tiene tres hojas:
   - **GENERADAS** – imágenes creadas con las rutas de cada resolución.
   - **FALLIDAS** – enfrentamientos que no pudieron generarse y el motivo.
   - **LOGOS** – fuente, formato, estado de calidad y URL de cada logo.

## Estructura del proyecto

```
ENFRENTAMIENTOS_SIBA/
├── app.py              ← aplicación principal (lanzar esto)
├── app_generadora.py   ← generador original (uso individual)
├── generator.py        ← lógica de composición de imágenes
├── logo_fetcher.py     ← descarga automática de logos
├── match_loader.py     ← lectura del Excel
├── normalizer.py       ← normalización de nombres de equipos
├── reporter.py         ← generación del reporte Excel
├── requirements.txt
├── cache/
│   └── logos/
│       ├── wiki/       ← logos descargados de Wikipedia
│       ├── sportsdb/   ← logos descargados de TheSportsDB
│       └── manual/     ← logos seleccionados manualmente
└── output/
    └── YYYYMMDD-HHMMSS/
        ├── images/     ← imágenes generadas
        └── report.xlsx ← reporte de la corrida
```

## Notas

- Los logos se almacenan en caché para evitar descargas repetidas.  
  Para forzar la re-descarga de un equipo, elimina los archivos
  correspondientes en `cache/logos/`.
- Si `cairosvg` no está disponible (sin Cairo instalado), los archivos SVG
  se tratan como válidos sin verificación de resolución.
- TheSportsDB se accede con el endpoint público gratuito (clave `3`).
  Si el servicio no es accesible, la app continúa sin error fatal.
