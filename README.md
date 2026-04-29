# Procesamiento_Clima

Scripts de procesamiento y graficación de series climáticas e hidrológicas para
estudios de cuenca: precipitación (PP), caudal (Q), temperaturas y ET0, a partir
de datos DGA y de modelos climáticos globales (GCM, CMIP6 / CR2MET).

## Estructura

```
Procesamiento_Clima/
├── Data/                 # Series de entrada (DGA: PP y Q diarios)
├── Resultados/           # Salidas (no versionado)
├── scr/
│   ├── graf_Dga.py                  # Análisis estación por estación (PP o Q)
│   └── annual_plots_cuenca_gcm.py   # Series anuales de GCMs vs referencia
└── README.md
```

## Requisitos

```bash
pip install pandas matplotlib openpyxl
```

Python ≥ 3.10 (usa anotaciones modernas y `tick_labels` de matplotlib ≥ 3.9).

---

## 1) `scr/graf_Dga.py`

Procesa series **diarias DGA** y, por cada estación seleccionada, genera:

- Promedio mensual (mes calendario)
- Serie anual (suma para PP, media para Q)
- Boxplot mensual
- Tabla de estadígrafos mensuales (n, media, σ, min, p25, mediana, p75, max)
- Excel con todas las tablas

### Variables soportadas

| Tipo   | Mensual  | Anual    | Unidad | Patrones de columna / archivo            |
|--------|----------|----------|--------|------------------------------------------|
| `pp`   | suma     | suma     | mm     | `precip`, `pp_`, `pr_`                   |
| `q`    | media    | media    | m³/s   | `caudal`, `discharge`, `flow`, `q_`      |
| `et0`  | suma     | suma     | mm     | `et0`, `eto`, `evapotrans`               |
| `temp` | media    | media    | °C     | `tmean`, `tmax`, `tmin`, `tas_`, `temp`… |

### Uso interactivo (Spyder / consola)

Sin argumentos, el script:

1. Pregunta qué variable procesar (PP, Q, ET0, temperatura).
2. Lista los archivos compatibles encontrados en `Data/` y pide elegir.
3. Lista las estaciones del archivo y pide elegir.

```bash
python scr/graf_Dga.py
```

### Uso no interactivo / CLI

```bash
# Tipo y archivo explícitos
python scr/graf_Dga.py --tipo pp --archivo Data/pp_diarias_historico_5.txt

# Tipo + selección de estaciones
python scr/graf_Dga.py --tipo q --estaciones "COLLIGUAY,PICHIDANGUI"

# Carpeta alternativa de búsqueda
python scr/graf_Dga.py --tipo et0 --data_dir /otra/ruta

# Totalmente automatizado (primer archivo compatible, estaciones predefinidas)
python scr/graf_Dga.py --tipo pp --no_interactivo
```

Selección de estaciones: acepta números, nombres, o mezcla separada por comas.

Salida: `Resultados/DGA/<ESTACION>/...`

---

## 2) `scr/annual_plots_cuenca_gcm.py`

Procesa múltiples CSV de **GCMs** (un archivo por modelo) más una **serie de
referencia** (CR2MET / observada) y, por cada variable detectada (PP, Tmax,
Tmin, Tmean, Tx, Tn, ET0), genera:

- Histórico (referencia) — raw y MA *N* años
- Futuro (GCMs + ensemble + peor escenario) — raw y MA *N* años
- Combinados histórico y futuro (raw + MA superpuestos)
- CSV en formato tidy y wide
- `Resumen_Anual_Todas_Las_Variables.csv`

Cada gráfico se exporta en JPG (600 DPI) y SVG.

### Asignación de archivos a variables

Cada CSV se asigna a **una sola** variable según patrones en el nombre
(`pr_`, `pp_`, `tasmax`, `tasmin`, `tas_`, `_tx_`, `_tn_`, `_et0_`).
Si para una misma variable hay archivos diarios y mensuales, se descartan los
mensuales (los diarios son más precisos).

La serie de referencia se detecta por nombre (`hist`, `obs`, `ref`, `cr2met`, …).

### Uso

```bash
python scr/annual_plots_cuenca_gcm.py \
    --input_dir Data/Quilimari \
    --target Subcuenca_Q01

python scr/annual_plots_cuenca_gcm.py --help
```

Parámetros principales: `--input_dir`, `--target` (columna a extraer),
`--hist_max`, `--future_min`, `--dpi`, `--no_worst`.

Salida: `scr/Resultados/...` (al lado del script).

---

## Notas

- **Formato CR2MET**: el script de GCMs detecta automáticamente cabeceras
  con `#,1,2,…` + `$Columns = ...`.
- **Fechas**: parser flexible con inferencia `dayfirst` por análisis de muestra.
- La carpeta `Resultados/` está en `.gitignore`; las salidas no se versionan.

---

## Autor

**David Poblete** — Universidad de Valparaíso
📧 david.poblete@uv.cl

## Licencia

MIT License

Copyright (c) 2026 David Poblete

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
