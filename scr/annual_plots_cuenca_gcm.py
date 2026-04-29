"""
annual_plots_cuenca_gcm.py
==========================
Procesa y grafica series climáticas anuales a partir de múltiples archivos CSV
de modelos GCM (General Circulation Models).

Por cada variable genera CUATRO gráficos:
  1. {stub}_historico       — solo serie observada/referencia, años <= HISTORICAL_YEAR_MAX
  2. {stub}_futuro          — GCMs proyectados, años >= FUTURE_YEAR_MIN
  3. {stub}_historico_MA3   — igual que (1) con media móvil 3 años
  4. {stub}_futuro_MA3      — igual que (2) con media móvil 3 años

Cada gráfico se exporta en JPG (raster) y SVG (vectorial).
Los resultados se guardan siempre en la carpeta donde reside este script.

Dependencias:
    pip install pandas matplotlib

Uso básico:
    python annual_plots_cuenca_gcm.py --input_dir /ruta/a/los/datos

Todos los parámetros:
    python annual_plots_cuenca_gcm.py --help
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

import matplotlib.lines as mlines
import matplotlib.pyplot as plt
import pandas as pd

# ─────────────────────────────────────────────
# Directorio del script → carpeta de salida fija
# ─────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent

# ─────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Cortes temporales (modificables por CLI)
# ─────────────────────────────────────────────
HISTORICAL_YEAR_MAX: int = 2025   # años <= este valor → gráfico histórico
FUTURE_YEAR_MIN: int     = 2025   # años >= este valor → gráfico futuro
ROLLING_WINDOW: int      = 5      # ventana de media móvil en años


# ─────────────────────────────────────────────
# Dataclasses de configuración
# ─────────────────────────────────────────────
@dataclass
class PlotConfig:
    """Parámetros globales de salida y estética."""
    output_folder: str = "Resultados"
    save_dpi: int = 600
    fig_width: float = 11.0
    fig_height: float = 7.0


@dataclass
class VariableSpec:
    """
    Especificación de una variable climática.

    Atributos
    ---------
    key             : identificador interno único
    patterns        : lista de substrings alternativos para identificar archivos.
                      Un archivo hace match si su stem contiene CUALQUIERA de ellos.
    summary_fun     : 'sum' para precipitación, 'mean' para temperaturas
    variable_name   : nombre descriptivo del valor
    title           : título base del gráfico
    ylab            : etiqueta del eje Y
    file_stub       : prefijo de los archivos de salida
    highlight_worst : si True, resalta el GCM con el valor más extremo
    worst_direction : 'min' → el más seco/frío; 'max' → el más cálido/húmedo
    """
    key: str
    patterns: list[str]           # uno o más substrings alternativos
    summary_fun: Literal["sum", "mean"]
    variable_name: str
    title: str
    ylab: str
    file_stub: str
    highlight_worst: bool = False
    worst_direction: Literal["min", "max"] = "min"
    var_type: Literal["precip", "temp"] = "temp"  # controla estilo de gráfico


# ─────────────────────────────────────────────
# Especificaciones de variables
# ─────────────────────────────────────────────
# Notas de diseño:
#   • summary_fun="sum"  → precipitación (acumular en el año)
#   • summary_fun="mean" → temperatura   (promediar en el año)
#   • Los patrones son substrings del stem del nombre de archivo.
#   • Cada CSV es asignado a UNA SOLA variable (primer match en orden de lista).
#     Esto evita que un archivo aparezca en gráficos de distinto tipo.
VARIABLE_SPECS: list[VariableSpec] = [
    # ── Precipitación ────────────────────────────────────────────────────────
    # Patrón "pr_" (con guión bajo) evita capturar archivos cuyo nombre
    # contenga "pr" como subcadena de otra palabra (ej. "proyectado", "taspr").
    VariableSpec(
        key="pr",
        patterns=["pr_"],
        summary_fun="sum",
        variable_name="PP_mm",
        title="Precipitación anual",
        ylab="Precipitación [mm]",
        file_stub="Precipitacion_Anual",
        highlight_worst=True,
        worst_direction="min",
        var_type="precip",
    ),
    # Patrón alternativo para archivos nombrados con "pp" en lugar de "pr"
    VariableSpec(
        key="pp",
        patterns=["pp_"],
        summary_fun="sum",
        variable_name="PP_mm",
        title="Precipitación anual (PP)",
        ylab="Precipitación [mm]",
        file_stub="PP_Anual",
        highlight_worst=True,
        worst_direction="min",
        var_type="precip",
    ),
    # ── Temperaturas (convención CMIP6: tas / tasmax / tasmin) ───────────────
    # "tasmax" antes de "tas_" para que los archivos de máxima no sean
    # capturados por el spec de temperatura media.
    VariableSpec(
        key="tmax",
        patterns=["tasmax"],       # CMIP6: tasmax_*  (antes era "tmax")
        summary_fun="mean",
        variable_name="Tmax",
        title="Temperatura máxima media anual",
        ylab="T max [°C]",
        file_stub="Mean_Annual_Max_Temperature",
    ),
    VariableSpec(
        key="tmin",
        patterns=["tasmin"],       # CMIP6: tasmin_*  (antes era "tmin")
        summary_fun="mean",
        variable_name="Tmin",
        title="Temperatura mínima media anual",
        ylab="T min [°C]",
        file_stub="Mean_Annual_Min_Temperature",
    ),
    VariableSpec(
        key="tmean",
        patterns=["tas_", "tasmed", "tav"],  # CMIP6: tas_* + tasmed_* + CR2MET tav_*
        summary_fun="mean",
        variable_name="Tmean",
        title="Temperatura media anual",
        ylab="T media [°C]",
        file_stub="Mean_Annual_Mean_Temperature",
    ),
    # ── Variables opcionales (activa si tus archivos las contienen) ──────────
    VariableSpec(
        key="tx",
        patterns=["_tx_"],         # guión bajo en ambos lados: evita match con "tasmax"
        summary_fun="mean",
        variable_name="Tx",
        title="Tx media anual",
        ylab="Tx [°C]",
        file_stub="Tx_Anual",
    ),
    VariableSpec(
        key="tn",
        patterns=["_tn_"],
        summary_fun="mean",
        variable_name="Tn",
        title="Tn media anual",
        ylab="Tn [°C]",
        file_stub="Tn_Anual",
    ),
    # ── ET0 CR2Met──────────
    VariableSpec(
        key="et0",
        patterns=["_et0_"],         # guión bajo en ambos lados: evita match con "tasmax"
        summary_fun="sum",
        variable_name="ET0",
        title="ET0 anual acumulada",
        ylab="ET0 acumulada [mm]",
        file_stub="ET0_Anual",
    ),
]


def _validate_specs(specs: list[VariableSpec]) -> None:
    """Advierte en tiempo de carga si hay keys o file_stubs duplicados."""
    seen_keys: set[str] = set()
    seen_stubs: set[str] = set()
    for s in specs:
        if s.key in seen_keys:
            log.warning("VariableSpec key duplicado: '%s'.", s.key)
        if s.file_stub in seen_stubs:
            log.warning("VariableSpec file_stub duplicado: '%s'.", s.file_stub)
        seen_keys.add(s.key)
        seen_stubs.add(s.file_stub)


_validate_specs(VARIABLE_SPECS)

# ─────────────────────────────────────────────
# Patrón para detectar series de referencia/histórica
# ─────────────────────────────────────────────
REFERENCE_PATTERN = r"hist|histor|obs|observ|ref|reference|base|baseline|control|cr2met|cr2"

# ─────────────────────────────────────────────
# Paleta y estilos visuales
# ─────────────────────────────────────────────
SERIES_STYLE: dict[str, dict] = {
    "GCMs individuales":      {"color": "#AAAAAA", "lw": 0.8,  "alpha": 0.80, "zorder": 1},
    "Histórico / referencia": {"color": "#2166AC", "lw": 1.6,  "alpha": 1.0,  "zorder": 3},
    "Promedio GCMs":          {"color": "#1A1A1A", "lw": 1.9,  "alpha": 1.0,  "zorder": 4},
    "Peor escenario":         {"color": "#D73027", "lw": 1.5,  "alpha": 1.0,  "zorder": 5},
    # estilos para gráficos combinados (raw + MA3)
    "Barra PP":               {"color": "#5B9BD5", "alpha": 0.75, "zorder": 2},
    "MA3 PP":                 {"color": "#1F3F6E", "lw": 2.0,  "alpha": 1.0,  "zorder": 3},
    "MA3 Temp":               {"color": "#8B0000", "lw": 2.0,  "alpha": 1.0,  "zorder": 3},
    "MA3 GCMs ensemble":      {"color": "#1A1A1A", "lw": 2.2,  "alpha": 1.0,  "zorder": 4},
}


# ═══════════════════════════════════════════════
# I/O DE ARCHIVOS
# ═══════════════════════════════════════════════

def find_csv_files(base_dir: Path) -> list[Path]:
    """Retorna todos los CSV en el directorio base (no recursivo, orden alfabético)."""
    return sorted(base_dir.glob("*.csv"))


def assign_files_exclusively(
    all_files: list[Path],
    specs: list[VariableSpec],
) -> dict[str, list[Path]]:
    """
    Asigna cada CSV a como máximo UNA variable: primer spec que haga match gana.
    Esto garantiza que ningún archivo aparezca en gráficos de distintas variables.

    Retorna {spec.key: [lista de archivos asignados]}.
    """
    assigned: dict[str, list[Path]] = {s.key: [] for s in specs}
    claimed: set[Path] = set()

    for spec in specs:
        pats = [p.lower() for p in spec.patterns]
        matched: list[Path] = []
        for f in all_files:
            stem = f.stem.lower()
            if f not in claimed and any(p in stem for p in pats):
                matched.append(f)

        # Si hay mezcla de archivos diarios y mensuales para la misma variable,
        # descartar los mensuales: los diarios son más precisos y el promedio
        # anual calculado desde datos mensuales no coincidirá exactamente.
        daily   = [f for f in matched if "diaria" in f.stem.lower()]
        monthly = [f for f in matched if "mensual" in f.stem.lower()]
        if daily and monthly:
            log.info(
                "  [%s] Archivos diarios y mensuales detectados. "
                "Se usarán solo los diarios: %s — descartados: %s",
                spec.key,
                [f.name for f in daily],
                [f.name for f in monthly],
            )
            matched = [f for f in matched if f not in monthly]

        for f in matched:
            assigned[spec.key].append(f)
            claimed.add(f)

    unassigned = [f for f in all_files if f not in claimed]
    if unassigned:
        log.warning(
            "Archivos sin variable asignada (se ignoran): %s",
            [f.name for f in unassigned],
        )
    return assigned


def _detect_cr2met_header(file: Path) -> tuple[int, list[str] | None]:
    """
    Detecta el formato de cabecera CR2MET:
      línea 0: #,1,2,3,4,...
      línea 1: $Columns = fecha,col1,col2,...
      línea 2+: datos
    Retorna (filas_a_saltar, nombres_de_columna | None).
    Si no detecta el formato especial retorna (0, None).
    """
    try:
        with open(file, encoding="utf-8", errors="replace") as fh:
            line0 = fh.readline()
            line1 = fh.readline()
        if line0.startswith("#") and line1.startswith("$Columns"):
            col_str = line1.split("=", 1)[1].strip()
            cols = [c.strip() for c in col_str.split(",")]
            return 2, cols
    except Exception:
        pass
    return 0, None


def safe_read_csv(file: Path) -> pd.DataFrame | None:
    """
    Lee un CSV con manejo de errores.
    Detecta automáticamente el formato CR2MET (cabecera con # y $Columns).
    Retorna None (+ warning) ante cualquier error.
    """
    try:
        skip, cols = _detect_cr2met_header(file)
        if skip > 0 and cols:
            df = pd.read_csv(file, skiprows=skip, header=None, names=cols)
        else:
            df = pd.read_csv(file)
        if df.shape[1] < 2:
            log.warning("'%s' tiene menos de 2 columnas. Se omite.", file.name)
            return None
        return df
    except Exception as exc:
        log.warning("No se pudo leer '%s': %s. Se omite.", file.name, exc)
        return None


# ═══════════════════════════════════════════════
# PARSEO DE FECHAS
# ═══════════════════════════════════════════════

_DATE_FORMATS = [
    "%m/%d/%Y", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d",
]


def parse_date_flexible(series: pd.Series) -> pd.Series:
    """
    Parsea fechas intentando primero inferencia automática de pandas y luego
    formatos explícitos sobre los valores que resultaron NaT.
    """
    result = pd.to_datetime(series, errors="coerce")

    if result.isna().any():
        raw = series.astype(str).str.strip()
        for fmt in _DATE_FORMATS:
            if not result.isna().any():
                break
            mask_na = result.isna()
            parsed = pd.to_datetime(raw[mask_na], format=fmt, errors="coerce")
            result = result.copy()
            result[mask_na] = parsed

    if result.isna().all():
        raise ValueError(
            "No se pudo interpretar ninguna fecha. "
            f"Muestra: {series.dropna().head(3).tolist()}"
        )
    return result


# ═══════════════════════════════════════════════
# PROCESAMIENTO DE DATOS
# ═══════════════════════════════════════════════

def summarise_annual_file(
    file: Path,
    target_col: str,
    summary_fun: Literal["sum", "mean"],
    variable_name: str,
) -> pd.DataFrame | None:
    """
    Lee un CSV y calcula el resumen anual (sum o mean) de la columna objetivo.
    Retorna None si el archivo es inválido o falta la columna.
    """
    df = safe_read_csv(file)
    if df is None:
        return None

    df.columns = ["Date"] + list(df.columns[1:])

    try:
        df["Date"] = parse_date_flexible(df["Date"])
    except ValueError as exc:
        log.warning("'%s': %s. Se omite.", file.name, exc)
        return None

    if target_col not in df.columns:
        log.warning(
            "Columna '%s' no encontrada en '%s'. Columnas disponibles: %s. Se omite.",
            target_col, file.name, list(df.columns[1:]),
        )
        return None

    df["year"] = df["Date"].dt.year.dropna().astype(int)
    agg = (
        df.dropna(subset=["year"])
          .groupby("year")[target_col]
          .agg(summary_fun)
          .reset_index()
          .rename(columns={target_col: "value"})
    )
    agg["model"]       = file.stem
    agg["source_file"] = file.name
    agg["variable"]    = variable_name
    return agg


def summarise_annual_set(
    files: list[Path],
    target_col: str,
    summary_fun: Literal["sum", "mean"],
    variable_name: str,
) -> pd.DataFrame:
    """Procesa un conjunto de CSVs y consolida los resúmenes anuales."""
    frames = [
        summarise_annual_file(f, target_col, summary_fun, variable_name)
        for f in files
    ]
    frames = [f for f in frames if f is not None]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


# ═══════════════════════════════════════════════
# ROLES, ENSEMBLE Y PEOR ESCENARIO
# ═══════════════════════════════════════════════

def assign_model_roles(df: pd.DataFrame) -> pd.DataFrame:
    """
    Asigna 'reference' a modelos cuyo nombre coincide con REFERENCE_PATTERN;
    el resto recibe 'gcm'. Emite warning si no hay ninguna referencia.
    """
    df = df.copy()
    models = df["model"].unique()
    is_ref = (
        pd.Series(models, dtype=str)
          .str.contains(REFERENCE_PATTERN, case=False, regex=True, na=False)
    )
    ref_models = set(pd.Series(models)[is_ref.values])

    if ref_models:
        log.info("  Serie(s) de referencia: %s", sorted(ref_models))
    else:
        log.warning(
            "  Sin serie de referencia detectada. Todos los modelos → 'gcm'. "
            "Nombra la serie histórica con: hist, obs, ref, baseline, etc."
        )

    df["role"] = df["model"].apply(
        lambda m: "reference" if m in ref_models else "gcm"
    )
    return df


def compute_ensemble_mean(df: pd.DataFrame) -> pd.DataFrame:
    """Promedio anual del ensemble sobre los GCMs (excluye referencia y ensemble)."""
    gcm_df = df[df["role"] == "gcm"]
    if gcm_df.empty:
        return pd.DataFrame()

    ens = (
        gcm_df.groupby(["year", "variable"])["value"]
              .mean()
              .reset_index()
    )
    ens["model"]       = "Promedio GCMs"
    ens["source_file"] = pd.NA
    ens["role"]        = "ensemble"
    return ens


def compute_worst_model(
    df: pd.DataFrame,
    direction: Literal["min", "max"] = "min",
) -> str | None:
    """GCM con el promedio más bajo ('min') o más alto ('max') entre todos los años."""
    gcm_df = df[df["role"] == "gcm"]
    if gcm_df.empty:
        return None
    scores = gcm_df.groupby("model")["value"].mean().dropna()
    if scores.empty:
        return None
    return scores.idxmin() if direction == "min" else scores.idxmax()


# ═══════════════════════════════════════════════
# MEDIA MÓVIL
# ═══════════════════════════════════════════════

def apply_rolling_mean(df: pd.DataFrame, window: int = ROLLING_WINDOW) -> pd.DataFrame:
    """
    Aplica media móvil centrada de `window` años por modelo.
    Requiere al menos 2 puntos en la ventana (min_periods=2).
    """
    if df.empty:
        return df

    result = df.copy().sort_values(["model", "year"])
    result["value"] = (
        result.groupby("model")["value"]
              .transform(
                  lambda x: x.rolling(window=window, min_periods=2, center=True).mean()
              )
    )
    return result


# ═══════════════════════════════════════════════
# NÚCLEO DE DIBUJO
# ═══════════════════════════════════════════════

def _draw_series(
    ax: plt.Axes,
    df: pd.DataFrame,
    spec: VariableSpec,
    mode: Literal["historical", "future"],
) -> list[mlines.Line2D]:
    """
    Dibuja las series sobre `ax`:
      - 'historical': solo la serie de referencia/observada
      - 'future'    : GCMs individuales + (opcional) peor escenario + ensemble

    Retorna los handles para construir la leyenda.
    """
    handles: list[mlines.Line2D] = []

    if mode == "historical":
        ref_df = df[df["role"] == "reference"]
        if ref_df.empty:
            return handles
        if spec.var_type == "precip":
            # ── Precipitación histórica: barras ──────────────────────
            st = SERIES_STYLE["Barra PP"]
            for _, grp in ref_df.groupby("model"):
                ax.bar(grp["year"], grp["value"],
                       color=st["color"], alpha=st["alpha"],
                       zorder=st["zorder"], width=0.8)
            handles.append(
                mlines.Line2D([], [], color=st["color"], lw=6,
                              alpha=st["alpha"], label="Precipitación observada")
            )
        else:
            # ── Temperatura histórica: línea continua ─────────────────
            st = SERIES_STYLE["Histórico / referencia"]
            for _, grp in ref_df.groupby("model"):
                ax.plot(grp["year"], grp["value"],
                        color=st["color"], lw=st["lw"],
                        alpha=st["alpha"], zorder=st["zorder"])
            handles.append(
                mlines.Line2D([], [], color=st["color"], lw=st["lw"],
                              label="Observado / referencia")
            )

    else:  # future
        gcm_df = df[df["role"] == "gcm"]
        ens_df = df[df["role"] == "ensemble"]

        # GCMs individuales
        if not gcm_df.empty:
            st = SERIES_STYLE["GCMs individuales"]
            first = True
            for _, grp in gcm_df.groupby("model"):
                ax.plot(grp["year"], grp["value"],
                        color=st["color"], lw=st["lw"],
                        alpha=st["alpha"], zorder=st["zorder"])
                if first:
                    handles.append(
                        mlines.Line2D([], [], color=st["color"], lw=st["lw"],
                                      alpha=st["alpha"], label="GCMs individuales")
                    )
                    first = False

        # Peor escenario
        if spec.highlight_worst and not gcm_df.empty:
            worst = compute_worst_model(df, direction=spec.worst_direction)
            if worst:
                st = SERIES_STYLE["Peor escenario"]
                wdf = df[df["model"] == worst]
                ax.plot(wdf["year"], wdf["value"],
                        color=st["color"], lw=st["lw"],
                        alpha=st["alpha"], zorder=st["zorder"])
                handles.append(
                    mlines.Line2D([], [], color=st["color"], lw=st["lw"],
                                  label=f"Peor escenario ({worst})")
                )

        # Ensemble
        if not ens_df.empty:
            st = SERIES_STYLE["Promedio GCMs"]
            ax.plot(ens_df["year"], ens_df["value"],
                    color=st["color"], lw=st["lw"],
                    alpha=st["alpha"], zorder=st["zorder"])
            handles.append(
                mlines.Line2D([], [], color=st["color"], lw=st["lw"],
                              label="Promedio GCMs")
            )

    return handles



def _draw_combined_historical(
    ax: plt.Axes,
    df_raw: pd.DataFrame,
    df_ma3: pd.DataFrame,
    spec: "VariableSpec",
) -> list[mlines.Line2D]:
    """
    Superpone la serie raw y la MA3 histórica en el mismo eje.
      - Precipitación : barras (raw) + línea segmentada (MA3)
      - Temperatura   : línea continua (raw) + línea segmentada (MA3)
    """
    handles: list[mlines.Line2D] = []

    ref_raw = df_raw[df_raw["role"] == "reference"]
    ref_ma3 = df_ma3[df_ma3["role"] == "reference"]

    if ref_raw.empty:
        return handles

    if spec.var_type == "precip":
        # barras crudas
        st_bar = SERIES_STYLE["Barra PP"]
        for _, grp in ref_raw.groupby("model"):
            ax.bar(grp["year"], grp["value"],
                   color=st_bar["color"], alpha=st_bar["alpha"],
                   zorder=st_bar["zorder"], width=0.8)
        handles.append(
            mlines.Line2D([], [], color=st_bar["color"], lw=6,
                          alpha=st_bar["alpha"], label="PP anual observada")
        )
        # MA3 como línea segmentada
        if not ref_ma3.empty:
            st_ma = SERIES_STYLE["MA3 PP"]
            for _, grp in ref_ma3.groupby("model"):
                ax.plot(grp["year"], grp["value"],
                        color=st_ma["color"], lw=st_ma["lw"],
                        linestyle="--", alpha=st_ma["alpha"], zorder=st_ma["zorder"])
            handles.append(
                mlines.Line2D([], [], color=st_ma["color"], lw=st_ma["lw"],
                              linestyle="--", label=f"MA {ROLLING_WINDOW} años")
            )
    else:
        # línea continua cruda
        st_ref = SERIES_STYLE["Histórico / referencia"]
        for _, grp in ref_raw.groupby("model"):
            ax.plot(grp["year"], grp["value"],
                    color=st_ref["color"], lw=st_ref["lw"],
                    alpha=st_ref["alpha"], zorder=st_ref["zorder"])
        handles.append(
            mlines.Line2D([], [], color=st_ref["color"], lw=st_ref["lw"],
                          label="Observado")
        )
        # MA3 como línea segmentada
        if not ref_ma3.empty:
            st_ma = SERIES_STYLE["MA3 Temp"]
            for _, grp in ref_ma3.groupby("model"):
                ax.plot(grp["year"], grp["value"],
                        color=st_ma["color"], lw=st_ma["lw"],
                        linestyle="--", alpha=st_ma["alpha"], zorder=st_ma["zorder"])
            handles.append(
                mlines.Line2D([], [], color=st_ma["color"], lw=st_ma["lw"],
                              linestyle="--", label=f"MA {ROLLING_WINDOW} años")
            )

    return handles


def _draw_combined_future(
    ax: plt.Axes,
    df_raw: pd.DataFrame,
    df_ma3_ens: pd.DataFrame,
    spec: "VariableSpec",
) -> list[mlines.Line2D]:
    """
    Superpone GCMs individuales (raw) y el ensemble MA3 en el mismo eje.
    Aplica el mismo estilo de línea/barra según var_type.
    """
    handles: list[mlines.Line2D] = []

    gcm_raw = df_raw[df_raw["role"] == "gcm"]
    ens_ma3 = df_ma3_ens[df_ma3_ens["role"] == "ensemble"]

    if gcm_raw.empty:
        return handles

    if spec.var_type == "precip":
        # GCMs como barras agrupadas (apiladas visualmente por transparencia)
        st_bar = SERIES_STYLE["Barra PP"]
        first = True
        for _, grp in gcm_raw.groupby("model"):
            ax.bar(grp["year"], grp["value"],
                   color=st_bar["color"], alpha=0.25,
                   zorder=1, width=0.8)
            if first:
                handles.append(
                    mlines.Line2D([], [], color=st_bar["color"], lw=6,
                                  alpha=0.5, label="GCMs individuales")
                )
                first = False
    else:
        st_gcm = SERIES_STYLE["GCMs individuales"]
        first = True
        for _, grp in gcm_raw.groupby("model"):
            ax.plot(grp["year"], grp["value"],
                    color=st_gcm["color"], lw=st_gcm["lw"],
                    alpha=st_gcm["alpha"], zorder=st_gcm["zorder"])
            if first:
                handles.append(
                    mlines.Line2D([], [], color=st_gcm["color"], lw=st_gcm["lw"],
                                  alpha=st_gcm["alpha"], label="GCMs individuales")
                )
                first = False

    # Ensemble MA3 como línea segmentada (igual para ambos tipos)
    if not ens_ma3.empty:
        st_ma = SERIES_STYLE["MA3 GCMs ensemble"]
        for _, grp in ens_ma3.groupby("model"):
            ax.plot(grp["year"], grp["value"],
                    color=st_ma["color"], lw=st_ma["lw"],
                    linestyle="--", alpha=st_ma["alpha"], zorder=st_ma["zorder"])
        handles.append(
            mlines.Line2D([], [], color=st_ma["color"], lw=st_ma["lw"],
                          linestyle="--",
                          label=f"Promedio GCMs MA{ROLLING_WINDOW}")
        )

    # Peor escenario raw (si aplica)
    if spec.highlight_worst:
        worst = compute_worst_model(df_raw, direction=spec.worst_direction)
        if worst:
            st_w = SERIES_STYLE["Peor escenario"]
            wdf = df_raw[df_raw["model"] == worst]
            ax.plot(wdf["year"], wdf["value"],
                    color=st_w["color"], lw=st_w["lw"],
                    alpha=st_w["alpha"], zorder=st_w["zorder"])
            handles.append(
                mlines.Line2D([], [], color=st_w["color"], lw=st_w["lw"],
                              label=f"Peor escenario ({worst})")
            )

    return handles

def _style_and_save(
    fig: plt.Figure,
    ax: plt.Axes,
    handles: list[mlines.Line2D],
    title: str,
    ylab: str,
    base_path: Path,
    dpi: int,
) -> None:
    """Aplica estética, guarda JPG + SVG y cierra la figura."""
    ax.set_title(title, fontsize=14, fontweight="bold", pad=12)
    ax.set_xlabel("Año", fontsize=12)
    ax.set_ylabel(ylab, fontsize=12)
    if handles:
        ax.legend(handles=handles, loc="upper center",
                  bbox_to_anchor=(0.5, 1.0),
                  ncol=len(handles), frameon=True, fontsize=10)
    ax.grid(True, linestyle="--", linewidth=0.4, alpha=0.5)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    fig.tight_layout()

    fig.savefig(base_path.with_suffix(".jpg"), dpi=dpi,
                bbox_inches="tight", facecolor="white")
    fig.savefig(base_path.with_suffix(".svg"), format="svg",
                bbox_inches="tight", facecolor="white")
    plt.close(fig)
    log.info("    → %s (.jpg / .svg)", base_path.name)


# ═══════════════════════════════════════════════
# GRÁFICOS PÚBLICOS
# ═══════════════════════════════════════════════

def make_historical_plot(
    df: pd.DataFrame,
    spec: VariableSpec,
    out_dir: Path,
    cfg: PlotConfig,
    smoothed: bool = False,
) -> None:
    """
    Gráfico histórico: SOLO la serie de referencia/observada, años <= HISTORICAL_YEAR_MAX.
    Si smoothed=True aplica media móvil de ROLLING_WINDOW años.
    """
    sub = df[df["year"] <= HISTORICAL_YEAR_MAX].copy()
    sub = sub[sub["role"] == "reference"]

    if sub.empty:
        log.warning("  [%s] Sin datos de referencia histórica (<= %d). Se omite.",
                    spec.key, HISTORICAL_YEAR_MAX)
        return

    if smoothed:
        sub = apply_rolling_mean(sub)

    suffix       = "_MA3" if smoothed else ""
    title_suffix = f" — MA {ROLLING_WINDOW} años" if smoothed else ""

    fig, ax = plt.subplots(figsize=(cfg.fig_width, cfg.fig_height))
    handles = _draw_series(ax, sub, spec, mode="historical")
    _style_and_save(
        fig, ax, handles,
        title=f"{spec.title} — Histórico{title_suffix}",
        ylab=spec.ylab,
        base_path=out_dir / f"{spec.file_stub}_historico{suffix}",
        dpi=cfg.save_dpi,
    )


def make_future_plot(
    df: pd.DataFrame,
    spec: VariableSpec,
    out_dir: Path,
    cfg: PlotConfig,
    smoothed: bool = False,
) -> None:
    """
    Gráfico futuro: GCMs + ensemble + (opcional) peor escenario, años >= FUTURE_YEAR_MIN.
    Si smoothed=True aplica media móvil de ROLLING_WINDOW años.
    La serie de referencia NO aparece en este gráfico.
    """
    sub = df[(df["year"] >= FUTURE_YEAR_MIN) & (df["role"] == "gcm")].copy()

    if sub.empty:
        log.warning("  [%s] Sin GCMs en período futuro (>= %d). Se omite.",
                    spec.key, FUTURE_YEAR_MIN)
        return

    if smoothed:
        sub = apply_rolling_mean(sub)

    # Recalcular ensemble sobre los datos ya filtrados y (si aplica) suavizados
    ens = compute_ensemble_mean(sub)
    if smoothed and not ens.empty:
        ens = apply_rolling_mean(ens)

    combined = pd.concat(
        [sub, ens] if not ens.empty else [sub],
        ignore_index=True,
    )

    suffix       = "_MA3" if smoothed else ""
    title_suffix = f" — MA {ROLLING_WINDOW} años" if smoothed else ""

    fig, ax = plt.subplots(figsize=(cfg.fig_width, cfg.fig_height))
    handles = _draw_series(ax, combined, spec, mode="future")
    _style_and_save(
        fig, ax, handles,
        title=f"{spec.title} — GCMs futuros{title_suffix}",
        ylab=spec.ylab,
        base_path=out_dir / f"{spec.file_stub}_futuro{suffix}",
        dpi=cfg.save_dpi,
    )


def make_combined_historical_plot(
    df: pd.DataFrame,
    spec: "VariableSpec",
    out_dir: Path,
    cfg: PlotConfig,
) -> None:
    """
    Gráfico histórico combinado: serie raw + MA3 superpuestos.
      Precip → barras (raw) + línea segmentada (MA3)
      Temp   → línea continua (raw) + línea segmentada (MA3)
    """
    sub_raw = df[(df["year"] <= HISTORICAL_YEAR_MAX) & (df["role"] == "reference")].copy()
    if sub_raw.empty:
        log.warning("  [%s] Sin referencia histórica para gráfico combinado. Se omite.", spec.key)
        return

    sub_ma3 = apply_rolling_mean(sub_raw)

    fig, ax = plt.subplots(figsize=(cfg.fig_width, cfg.fig_height))
    handles = _draw_combined_historical(ax, sub_raw, sub_ma3, spec)
    _style_and_save(
        fig, ax, handles,
        title=f"{spec.title} — Histórico + MA{ROLLING_WINDOW}",
        ylab=spec.ylab,
        base_path=out_dir / f"{spec.file_stub}_historico_combinado",
        dpi=cfg.save_dpi,
    )


def make_combined_future_plot(
    df: pd.DataFrame,
    spec: "VariableSpec",
    out_dir: Path,
    cfg: PlotConfig,
) -> None:
    """
    Gráfico futuro combinado: GCMs raw + MA3 del ensemble superpuestos.
    """
    sub_raw = df[(df["year"] >= FUTURE_YEAR_MIN) & (df["role"] == "gcm")].copy()
    if sub_raw.empty:
        log.warning("  [%s] Sin GCMs futuros para gráfico combinado. Se omite.", spec.key)
        return

    ens_raw = compute_ensemble_mean(sub_raw)
    ens_ma3 = apply_rolling_mean(ens_raw) if not ens_raw.empty else pd.DataFrame()
    if not ens_ma3.empty:
        ens_ma3["role"] = "ensemble"

    fig, ax = plt.subplots(figsize=(cfg.fig_width, cfg.fig_height))
    handles = _draw_combined_future(ax, sub_raw, ens_ma3, spec)
    _style_and_save(
        fig, ax, handles,
        title=f"{spec.title} — GCMs futuros + MA{ROLLING_WINDOW}",
        ylab=spec.ylab,
        base_path=out_dir / f"{spec.file_stub}_futuro_combinado",
        dpi=cfg.save_dpi,
    )


# ═══════════════════════════════════════════════
# EXPORTACIÓN DE TABLAS
# ═══════════════════════════════════════════════

def export_tables(df: pd.DataFrame, file_stub: str, out_dir: Path) -> None:
    """Exporta formato tidy y wide (pivot) del resumen anual completo."""
    df.to_csv(out_dir / f"{file_stub}_annual_tidy.csv", index=False)

    wide = (
        df[["year", "model", "value"]]
          .drop_duplicates()
          .pivot(index="year", columns="model", values="value")
          .sort_index()
          .reset_index()
    )
    wide.columns.name = None
    wide.to_csv(out_dir / f"{file_stub}_annual_wide.csv", index=False)
    log.info("  Tablas: %s_annual_tidy.csv / _wide.csv", file_stub)


# ═══════════════════════════════════════════════
# FLUJO PRINCIPAL
# ═══════════════════════════════════════════════

def run(
    input_dir: Path,
    target_col: str,
    cfg: PlotConfig,
    specs: list[VariableSpec] | None = None,
) -> None:
    """
    Orquesta lectura, procesamiento, graficación y exportación.
    La carpeta de salida se crea SIEMPRE junto al script (SCRIPT_DIR).
    """
    if specs is None:
        specs = VARIABLE_SPECS

    out_dir = SCRIPT_DIR / cfg.output_folder
    out_dir.mkdir(parents=True, exist_ok=True)

    all_csv = find_csv_files(input_dir)
    if not all_csv:
        raise FileNotFoundError(f"No se encontraron archivos CSV en: {input_dir}")

    log.info("Directorio datos  : %s", input_dir)
    log.info("Directorio salida : %s", out_dir)
    log.info("Archivos CSV      : %d", len(all_csv))
    log.info("Columna objetivo  : %s", target_col)
    log.info("Período histórico : años <= %d", HISTORICAL_YEAR_MAX)
    log.info("Período futuro    : años >= %d", FUTURE_YEAR_MIN)
    log.info("─" * 55)

    # Asignación exclusiva: cada CSV → una sola variable
    file_assignment = assign_files_exclusively(all_csv, specs)

    all_results: dict[str, pd.DataFrame] = {}

    for spec in specs:
        matched = file_assignment[spec.key]

        if not matched:
            log.warning("[%s] Sin archivos para patrones %s. Se omite.",
                        spec.key, spec.patterns)
            continue

        log.info("[%s] %d archivo(s): %s",
                 spec.key, len(matched), [f.name for f in matched])

        df_var = summarise_annual_set(
            files=matched,
            target_col=target_col,
            summary_fun=spec.summary_fun,
            variable_name=spec.variable_name,
        )

        if df_var.empty:
            log.warning("[%s] Sin datos generados. Se omite.", spec.key)
            continue

        df_var = assign_model_roles(df_var)
        export_tables(df_var, spec.file_stub, out_dir)

        # ── 6 gráficos por variable ──────────────────────────────────
        log.info("  Gráficos:")
        make_historical_plot        (df_var, spec, out_dir, cfg, smoothed=False)
        make_historical_plot        (df_var, spec, out_dir, cfg, smoothed=True)
        make_combined_historical_plot(df_var, spec, out_dir, cfg)
        make_future_plot            (df_var, spec, out_dir, cfg, smoothed=False)
        make_future_plot            (df_var, spec, out_dir, cfg, smoothed=True)
        make_combined_future_plot   (df_var, spec, out_dir, cfg)

        all_results[spec.key] = df_var
        log.info("─" * 55)

    # Resumen combinado de todas las variables
    if all_results:
        combined = pd.concat(
            [d.assign(series_key=k) for k, d in all_results.items()],
            ignore_index=True,
        )
        combined.to_csv(
            out_dir / "Resumen_Anual_Todas_Las_Variables.csv", index=False
        )
        log.info("Proceso completado. Resultados en: %s", out_dir)
    else:
        log.warning(
            "No se generaron resultados. "
            "Revisa los patrones en VARIABLE_SPECS y el directorio de entrada."
        )


# ═══════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Genera gráficos anuales de variables climáticas desde CSVs de GCMs.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--input_dir", type=Path, default=Path("."),
                   help="Directorio con los archivos CSV de entrada.")
    p.add_argument("--target", default="Subcuenca_Q01",
                   help="Nombre de la columna a extraer de cada CSV.")
    p.add_argument("--output_folder", default="Resultados",
                   help="Subcarpeta de salida (creada junto al script).")
    p.add_argument("--dpi", type=int, default=600,
                   help="Resolución en DPI para los JPG.")
    p.add_argument("--hist_max", type=int, default=HISTORICAL_YEAR_MAX,
                   help="Año máximo del período histórico (inclusive).")
    p.add_argument("--future_min", type=int, default=FUTURE_YEAR_MIN,
                   help="Año mínimo del período futuro (inclusive).")
    p.add_argument("--no_worst", action="store_true",
                   help="Desactiva el resaltado del peor escenario.")
    return p


def main() -> None:
    global HISTORICAL_YEAR_MAX, FUTURE_YEAR_MIN

    args = _build_parser().parse_args()

    HISTORICAL_YEAR_MAX = args.hist_max
    FUTURE_YEAR_MIN     = args.future_min

    cfg = PlotConfig(output_folder=args.output_folder, save_dpi=args.dpi)

    specs = VARIABLE_SPECS
    if args.no_worst:
        specs = [replace(s, highlight_worst=False) for s in specs]

    run(
        input_dir=args.input_dir.resolve(),
        target_col=args.target,
        cfg=cfg,
        specs=specs,
    )


if __name__ == "__main__":
    main()
