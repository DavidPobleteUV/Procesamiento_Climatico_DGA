# -*- coding: utf-8 -*-
"""
graf_Dga.py
===========
Procesa series diarias DGA (precipitación o caudal) y genera, por estación:
  - Gráfico promedio mensual (mes calendario)
  - Gráfico totales/medias anuales
  - Boxplot mensual
  - Tabla de estadígrafos mensuales
  - Excel con todas las tablas

Soporta dos tipos de variable:
  - "pp" : precipitación  → mensual = SUMA, anual = SUMA, ylabel "Precipitación [mm]"
  - "q"  : caudal         → mensual = MEDIA, anual = MEDIA, ylabel "Caudal [m³/s]"

Uso:
  python graf_Dga.py --tipo pp
  python graf_Dga.py --tipo q --estaciones "COLLIGUAY,PICHIDANGUI"
  python graf_Dga.py --help
"""

import argparse
import csv
import re
import unicodedata
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

# =========================================================
# CONFIGURACIÓN POR DEFECTO (modificable por CLI)
# =========================================================
SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR_DEFAULT = (SCRIPT_DIR / ".." / "Data").resolve()
OUT_DIR_DEFAULT  = (SCRIPT_DIR / ".." / "Resultados" / "DGA").resolve()

ESTACIONES_PREDEFINIDAS = ["COLLIGUAY"]

ANIO_INICIO_TICKS = 1970
PASO_TICKS_ANUAL  = 5


# =========================================================
# CONFIGURACIÓN POR TIPO DE VARIABLE
# =========================================================
CFG_VARIABLE = {
    "pp": {
        "nombre":        "precipitación",
        "agg_mensual":   "sum",
        "agg_anual":     "sum",
        "ylab_mensual":  "Precipitación mensual acumulada [mm]",
        "ylab_anual":    "Precipitación anual acumulada [mm]",
        "ylab_promedio": "Precipitación mensual promedio [mm]",
        "stub":          "precipitacion",
        "weap_stub":     "pp",
        # Patrones para detectar la columna de valor (en nombres normalizados)
        "col_keys":      ("precip", "pp", "pr"),
        # Patrones para detectar archivos en Data/ (substring del nombre)
        "file_keys":     ("pp_", "_pp", "pr_", "_pr", "precip"),
    },
    "q": {
        "nombre":        "caudal",
        "agg_mensual":   "mean",
        "agg_anual":     "mean",
        "ylab_mensual":  "Caudal medio mensual [m³/s]",
        "ylab_anual":    "Caudal medio anual [m³/s]",
        "ylab_promedio": "Caudal medio mensual promedio [m³/s]",
        "stub":          "caudal",
        "weap_stub":     "q",
        "col_keys":      ("caudal", "discharge", "flow", "q_"),
        "file_keys":     ("caudal", "discharge", "flow", "q_", "_q"),
    },
    "et0": {
        "nombre":        "ET0",
        "agg_mensual":   "sum",
        "agg_anual":     "sum",
        "ylab_mensual":  "ET0 mensual acumulada [mm]",
        "ylab_anual":    "ET0 anual acumulada [mm]",
        "ylab_promedio": "ET0 mensual promedio [mm]",
        "stub":          "et0",
        "weap_stub":     "et0",
        "col_keys":      ("et0", "eto", "evapotrans"),
        "file_keys":     ("et0", "eto", "evapotrans"),
    },
    "temp": {
        "nombre":        "temperatura",
        "agg_mensual":   "mean",
        "agg_anual":     "mean",
        "ylab_mensual":  "Temperatura media mensual [°C]",
        "ylab_anual":    "Temperatura media anual [°C]",
        "ylab_promedio": "Temperatura media mensual promedio [°C]",
        "stub":          "temperatura",
        "weap_stub":     "tav",
        "col_keys":      ("tmean", "tmed", "tas_", "tav", "temp", "tmax",
                          "tmin", "tasmax", "tasmin"),
        "file_keys":     ("temp", "tmean", "tmed", "tas_", "tasmax", "tasmin",
                          "_tx_", "_tn_", "tmax", "tmin", "tav"),
    },
}

NOMBRES_MESES = {
    1: "Ene", 2: "Feb", 3: "Mar",  4: "Abr",  5: "May",  6: "Jun",
    7: "Jul", 8: "Ago", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dic",
}


# =========================================================
# UTILIDADES
# =========================================================
def normalizar_texto(txt):
    if pd.isna(txt):
        return ""
    txt = str(txt).strip().lower()
    txt = unicodedata.normalize("NFKD", txt)
    return "".join(c for c in txt if not unicodedata.combining(c))


def nombre_seguro_archivo(txt):
    txt = str(txt).strip()
    for c in '/\\:*?"<>| ':
        txt = txt.replace(c, "_")
    return txt


def detectar_delimitador(path_txt, n_chars=5000):
    with open(path_txt, "r", encoding="utf-8-sig", errors="ignore") as f:
        muestra = f.read(n_chars)
    try:
        return csv.Sniffer().sniff(muestra, delimiters=";,|\t").delimiter
    except Exception:
        return ";"


def _buscar(columnas, predicado):
    for col in columnas:
        if predicado(normalizar_texto(col)):
            return col
    return None


def buscar_columna_fecha(columnas):
    return _buscar(columnas, lambda c: c == "fecha")


def buscar_columna_valor(columnas, tipo):
    """Busca columna del valor según los patrones de CFG_VARIABLE[tipo]."""
    for clave in CFG_VARIABLE[tipo]["col_keys"]:
        col = _buscar(columnas, lambda c, k=clave: k in c)
        if col:
            return col
    return None


def listar_archivos_compatibles(data_dir, tipo):
    """Devuelve archivos en data_dir cuyo nombre contiene algún file_key del tipo."""
    if not data_dir.exists():
        return []
    keys = CFG_VARIABLE[tipo]["file_keys"]
    archivos = []
    for f in sorted(data_dir.iterdir()):
        if not f.is_file():
            continue
        if f.suffix.lower() not in (".txt", ".csv"):
            continue
        nombre = normalizar_texto(f.name)
        if any(k in nombre for k in keys):
            archivos.append(f)
    return archivos


def preguntar_tipo_variable():
    """Pregunta interactivamente qué variable procesar."""
    opciones = [
        ("pp",   "Precipitación (PP)"),
        ("q",    "Caudal (Q)"),
        ("et0",  "Evapotranspiración de referencia (ET0)"),
        ("temp", "Temperatura"),
    ]
    print("\n¿Qué variable quieres procesar?")
    for i, (_, desc) in enumerate(opciones, 1):
        print(f"  {i}. {desc}")
    while True:
        sel = input("Selección [1-4]: ").strip().lower()
        if sel.isdigit() and 1 <= int(sel) <= len(opciones):
            return opciones[int(sel) - 1][0]
        for k, _ in opciones:
            if sel == k:
                return k
        print("Opción no válida, intenta de nuevo.")


def preguntar_archivo(archivos, data_dir, tipo):
    """Pregunta interactivamente qué archivo usar de la lista detectada."""
    if not archivos:
        raise FileNotFoundError(
            f"No se encontró ningún archivo compatible con tipo '{tipo}' "
            f"en: {data_dir}\n"
            f"Patrones buscados: {CFG_VARIABLE[tipo]['file_keys']}"
        )
    if len(archivos) == 1:
        print(f"\nÚnico archivo compatible detectado: {archivos[0].name}")
        return archivos[0]

    print(f"\nArchivos compatibles encontrados en {data_dir}:")
    for i, f in enumerate(archivos, 1):
        print(f"  {i}. {f.name}")
    while True:
        sel = input(f"Selección [1-{len(archivos)}]: ").strip()
        if sel.isdigit() and 1 <= int(sel) <= len(archivos):
            return archivos[int(sel) - 1]
        print("Opción no válida, intenta de nuevo.")


def buscar_columna_estacion(columnas):
    columnas_norm = {col: normalizar_texto(col) for col in columnas}

    for objetivo in ("nombre estacion", "nombre_estacion", "estacion nombre",
                     "nombre de estacion", "station name", "station_name"):
        for col, c_norm in columnas_norm.items():
            if c_norm == objetivo:
                return col

    for objetivo in ("estacion", "station", "sitio", "punto"):
        for col, c_norm in columnas_norm.items():
            if c_norm == objetivo:
                return col

    for col, c_norm in columnas_norm.items():
        if "nombre" in c_norm and "estacion" in c_norm:
            return col
    for col, c_norm in columnas_norm.items():
        if "estacion" in c_norm and "codigo" not in c_norm:
            return col
    for col, c_norm in columnas_norm.items():
        if "estacion" in c_norm or "station" in c_norm:
            return col
    return None


def inferir_dayfirst(serie_fechas):
    s = serie_fechas.dropna().astype(str).str.strip()
    s = s[s != ""].head(1000)
    patron = re.compile(r"^\s*(\d{1,2})[/-](\d{1,2})[/-](\d{4})\s*$")

    d_mayor = m_mayor = total = 0
    for val in s:
        m = patron.match(val)
        if not m:
            continue
        total += 1
        a, b = int(m.group(1)), int(m.group(2))
        if a > 12 and b <= 12:
            d_mayor += 1
        elif b > 12 and a <= 12:
            m_mayor += 1

    if total == 0 or d_mayor >= m_mayor:
        return True
    return False


def convertir_fechas(serie):
    return pd.to_datetime(serie, errors="coerce", dayfirst=inferir_dayfirst(serie))


# Acepta -, en-dash (–) y em-dash (—) como separador de rango
_RANGO_RE = re.compile(r"^\s*(\d+)\s*[-–—]\s*(\d+)\s*$")


def parsear_seleccion(texto, disponibles, predeterminadas):
    """
    Acepta selección por:
      - número            : "5"
      - rango inclusivo   : "27-40"  o  "27 - 40"
      - nombre            : "COLLIGUAY"
      - mezcla por coma   : "1, 27-40, COLLIGUAY, 42"
    """
    if texto.strip() == "":
        items = list(predeterminadas)
    else:
        items = [x.strip() for x in texto.split(",") if x.strip()]

    mapa = {normalizar_texto(e): e for e in disponibles}
    seleccion, no_encontradas = [], []

    def _agregar_indice(idx, etiqueta):
        if 0 <= idx < len(disponibles):
            est = disponibles[idx]
            if est not in seleccion:
                seleccion.append(est)
        else:
            no_encontradas.append(etiqueta)

    for item in items:
        m = _RANGO_RE.match(str(item))
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            lo, hi = (a, b) if a <= b else (b, a)
            for n in range(lo, hi + 1):
                _agregar_indice(n - 1, str(n))
        elif str(item).isdigit():
            _agregar_indice(int(item) - 1, item)
        else:
            clave = normalizar_texto(item)
            if clave in mapa and mapa[clave] not in seleccion:
                seleccion.append(mapa[clave])
            elif clave not in mapa:
                no_encontradas.append(item)
    return seleccion, no_encontradas


def calcular_ticks_anuales(anios, inicio=1970, paso=5):
    if not anios:
        return []
    anio_max = int(max(anios))
    if anio_max < inicio:
        return [inicio]
    resto = (anio_max - inicio) % paso
    anio_max_tick = anio_max if resto == 0 else anio_max + (paso - resto)
    return list(range(inicio, anio_max_tick + 1, paso))


# =========================================================
# PROCESAMIENTO POR ESTACIÓN
# =========================================================
def procesar_estacion(df_base, col_fecha, col_val, col_est,
                      estacion, carpeta_raiz, tipo, guardar=True):
    cfg = CFG_VARIABLE[tipo]
    nombre_var = cfg["nombre"]
    stub = cfg["stub"]

    df = df_base[
        df_base[col_est].apply(normalizar_texto) == normalizar_texto(estacion)
    ].copy()
    if df.empty:
        raise ValueError(f"No hay datos para la estación '{estacion}'.")

    df["año"]     = df[col_fecha].dt.year
    df["mes"]     = df[col_fecha].dt.month
    df["año_mes"] = df[col_fecha].dt.to_period("M")

    df_mensual = (
        df.groupby("año_mes", as_index=False)
          .agg({col_val: cfg["agg_mensual"], "año": "first", "mes": "first"})
          .rename(columns={col_val: "valor_mensual"})
    )

    promedio_mensual = (
        df_mensual.groupby("mes")["valor_mensual"].mean().reindex(range(1, 13))
    )

    total_anual = df.groupby("año")[col_val].agg(cfg["agg_anual"]).sort_index()

    datos_boxplot = [
        df_mensual.loc[df_mensual["mes"] == m, "valor_mensual"].dropna().values
        for m in range(1, 13)
    ]

    estadigrafos = (
        df_mensual.groupby("mes")["valor_mensual"]
                  .agg(n="count", media="mean", desv_std="std", minimo="min",
                       p25=lambda x: x.quantile(0.25), mediana="median",
                       p75=lambda x: x.quantile(0.75), maximo="max")
                  .reindex(range(1, 13))
    )
    estadigrafos.index = [NOMBRES_MESES[m] for m in estadigrafos.index]
    estadigrafos = estadigrafos.round(2)

    est_archivo = nombre_seguro_archivo(estacion)
    carpeta = carpeta_raiz / est_archivo
    carpeta.mkdir(parents=True, exist_ok=True)

    # G1: promedio mensual
    plt.figure(figsize=(10, 5))
    plt.bar([NOMBRES_MESES[m] for m in promedio_mensual.index], promedio_mensual.values)
    plt.title(f"Promedio mensual de {nombre_var} - {estacion}")
    plt.xlabel("Mes"); plt.ylabel(cfg["ylab_promedio"])
    plt.grid(axis="y", linestyle="--", alpha=0.5); plt.tight_layout()
    if guardar:
        plt.savefig(carpeta / f"promedio_mensual_{stub}_{est_archivo}.png",
                    dpi=300, bbox_inches="tight")
    plt.close()

    # G2: anual
    anios = total_anual.index.astype(int).tolist()
    ticks = calcular_ticks_anuales(anios, ANIO_INICIO_TICKS, PASO_TICKS_ANUAL)
    plt.figure(figsize=(12, 5))
    plt.bar(total_anual.index.astype(int), total_anual.values, width=0.8)
    plt.title(f"{nombre_var.capitalize()} anual - {estacion}")
    plt.xlabel("Año"); plt.ylabel(cfg["ylab_anual"])
    plt.grid(axis="y", linestyle="--", alpha=0.5)
    if ticks:
        plt.xticks(ticks, rotation=45)
        plt.xlim(ticks[0] - 1, ticks[-1] + 1)
    plt.tight_layout()
    if guardar:
        plt.savefig(carpeta / f"anual_{stub}_{est_archivo}.png",
                    dpi=300, bbox_inches="tight")
    plt.close()

    # G3: boxplot
    plt.figure(figsize=(12, 6))
    plt.boxplot(datos_boxplot,
                tick_labels=[NOMBRES_MESES[m] for m in range(1, 13)],
                showfliers=True)
    plt.title(f"Variabilidad mensual de {nombre_var} - {estacion}")
    plt.xlabel("Mes"); plt.ylabel(cfg["ylab_mensual"])
    plt.grid(axis="y", linestyle="--", alpha=0.5); plt.tight_layout()
    if guardar:
        plt.savefig(carpeta / f"boxplot_mensual_{stub}_{est_archivo}.png",
                    dpi=300, bbox_inches="tight")
    plt.close()

    # Tabla
    fig, ax = plt.subplots(figsize=(14, 5))
    ax.axis("off")
    tabla = ax.table(cellText=estadigrafos.values,
                     rowLabels=estadigrafos.index,
                     colLabels=estadigrafos.columns, loc="center")
    tabla.auto_set_font_size(False); tabla.set_fontsize(9); tabla.scale(1, 1.4)
    plt.title(f"Estadígrafos mensuales de {nombre_var} - {estacion}", pad=20)
    plt.tight_layout()
    if guardar:
        plt.savefig(carpeta / f"tabla_estadigrafos_{stub}_{est_archivo}.png",
                    dpi=300, bbox_inches="tight")
    plt.close()

    # Excel
    if guardar:
        xlsx = carpeta / f"estadigrafos_{stub}_{est_archivo}.xlsx"
        with pd.ExcelWriter(xlsx, engine="openpyxl") as w:
            df_mensual.to_excel(w, sheet_name="Serie mensual", index=False)
            promedio_mensual.to_frame(name="promedio_mensual").to_excel(
                w, sheet_name="Promedio mensual")
            total_anual.to_frame(name="anual").to_excel(w, sheet_name="Anual")
            estadigrafos.to_excel(w, sheet_name="Estadigrafos mensuales")
            pd.DataFrame({"estacion": [estacion], "tipo": [tipo]}).to_excel(
                w, sheet_name="Resumen", index=False)

    print(f"OK: {estacion} → {carpeta}")


# =========================================================
# EXPORTACIÓN A FORMATO WEAP / CR2MET
# =========================================================
def exportar_weap(df_base, col_fecha, col_val, col_est,
                  estaciones, out_dir, tipo):
    """
    Genera un único CSV diario en formato WEAP/CR2MET con una columna por
    estación y fechas mm/dd/yyyy. Rango = unión de todas las estaciones.
    Valores faltantes → celda vacía.

    Cabecera (2 líneas):
        #,1,2,...,N
        $Columns = fecha,Estacion1,Estacion2,...
    """
    if not estaciones:
        return

    cfg = CFG_VARIABLE[tipo]

    # Filtrar y construir wide diario
    df = df_base[df_base[col_est].apply(normalizar_texto).isin(
        [normalizar_texto(e) for e in estaciones]
    )].copy()
    df[col_fecha] = pd.to_datetime(df[col_fecha]).dt.normalize()

    # Si hay más de un registro por (estación, día) — promediar para evitar
    # error de pivot. En datos DGA limpios no debería ocurrir.
    df_diario = (
        df.groupby([col_fecha, col_est], as_index=False)[col_val].mean()
    )

    wide = df_diario.pivot(index=col_fecha, columns=col_est, values=col_val)

    # Reindexar al rango total (unión)
    rango = pd.date_range(wide.index.min(), wide.index.max(), freq="D")
    wide = wide.reindex(rango)

    # Ordenar columnas según el orden de selección, limpiar nombres
    estaciones_presentes = [e for e in estaciones if e in wide.columns]
    wide = wide[estaciones_presentes]
    wide.columns = [nombre_seguro_archivo(c) for c in wide.columns]

    # Nombre del archivo
    a1 = wide.index.min().year
    a2 = wide.index.max().year
    nombre = f"DGA_{cfg['weap_stub']}_diaria_{a1}_{a2}.csv"
    ruta = out_dir / nombre

    n = len(wide.columns)
    cabecera1 = "#," + ",".join(str(i) for i in range(1, n + 1))
    cabecera2 = "$Columns = fecha," + ",".join(wide.columns)

    # CR2MET usa mm/dd/yyyy (es el formato que el lector WEAP/CR2MET asume)
    fechas_str = wide.index.strftime("%m/%d/%Y")

    # Escribir manualmente para controlar cabecera y celdas vacías en NaN
    with open(ruta, "w", encoding="utf-8", newline="") as f:
        f.write(cabecera1 + "\n")
        f.write(cabecera2 + "\n")
        for fecha, fila in zip(fechas_str, wide.itertuples(index=False, name=None)):
            valores = ["" if pd.isna(v) else f"{v:g}" for v in fila]
            f.write(fecha + "," + ",".join(valores) + "\n")

    print(f"\nArchivo WEAP: {ruta}")
    print(f"  Estaciones : {n}")
    print(f"  Rango      : {a1}–{a2}  ({len(wide)} días)")


# =========================================================
# MAIN
# =========================================================
def main():
    parser = argparse.ArgumentParser(
        description="Procesa series DGA diarias (PP o Q) y genera gráficos por estación.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--tipo", choices=list(CFG_VARIABLE.keys()), default=None,
                        help="Tipo de variable: pp, q, et0 o temp. "
                             "Si se omite, se pregunta interactivamente.")
    parser.add_argument("--archivo", type=Path, default=None,
                        help="Archivo de entrada. Si se omite, se busca en Data/ "
                             "y se pregunta interactivamente.")
    parser.add_argument("--data_dir", type=Path, default=DATA_DIR_DEFAULT,
                        help="Carpeta donde buscar archivos de entrada.")
    parser.add_argument("--out_dir", type=Path, default=OUT_DIR_DEFAULT,
                        help="Carpeta raíz de salida.")
    parser.add_argument("--no_interactivo", action="store_true",
                        help="Usa estaciones predefinidas sin preguntar.")
    parser.add_argument("--estaciones", default=None,
                        help="Estaciones separadas por coma (ej: 'COLLIGUAY,PICHIDANGUI').")
    args = parser.parse_args()

    # 1) Tipo de variable (CLI o interactivo)
    tipo = args.tipo
    if tipo is None:
        if args.no_interactivo:
            tipo = "pp"
        else:
            tipo = preguntar_tipo_variable()

    # 2) Archivo (CLI explícito → busca en Data/ → interactivo)
    if args.archivo is not None:
        archivo = args.archivo
    else:
        compatibles = listar_archivos_compatibles(args.data_dir, tipo)
        if args.no_interactivo:
            if not compatibles:
                raise FileNotFoundError(
                    f"No se encontró archivo compatible con tipo '{tipo}' en {args.data_dir}"
                )
            archivo = compatibles[0]
            print(f"\n[no_interactivo] Usando: {archivo.name}")
        else:
            archivo = preguntar_archivo(compatibles, args.data_dir, tipo)

    if not archivo.exists():
        raise FileNotFoundError(f"Archivo no encontrado: {archivo}")

    # Subcarpeta por tipo: Resultados/DGA/PP, /Q, /ET0, /TAV
    out_dir = args.out_dir / CFG_VARIABLE[tipo]["weap_stub"].upper()
    out_dir.mkdir(parents=True, exist_ok=True)

    delim = detectar_delimitador(archivo)
    print(f"\nArchivo   : {archivo}")
    print(f"Tipo      : {tipo}")
    print(f"Separador : {repr(delim)}")
    print(f"Salida    : {out_dir}")

    df = pd.read_csv(archivo, sep=delim, encoding="utf-8-sig", engine="python")
    df.columns = df.columns.astype(str).str.strip()

    col_fecha = buscar_columna_fecha(df.columns)
    col_val   = buscar_columna_valor(df.columns, tipo)
    col_est   = ("NOMBRE ESTACION" if "NOMBRE ESTACION" in df.columns
                 else buscar_columna_estacion(df.columns))

    for nombre, col in [("FECHA", col_fecha),
                        (CFG_VARIABLE[tipo]["nombre"].upper(), col_val),
                        ("ESTACION", col_est)]:
        if col is None:
            raise ValueError(
                f"No se encontró columna {nombre}. Disponibles:\n"
                + "\n".join(df.columns.astype(str))
            )

    print(f"Col fecha : {col_fecha}")
    print(f"Col valor : {col_val}")
    print(f"Col estac.: {col_est}")

    df[col_fecha] = convertir_fechas(df[col_fecha])
    df[col_val]   = pd.to_numeric(df[col_val], errors="coerce")
    df[col_est]   = df[col_est].astype(str).str.strip()
    df = df.dropna(subset=[col_fecha, col_val, col_est]).copy()

    estaciones = sorted(df[col_est].unique())
    print(f"\n{len(estaciones)} estaciones disponibles:")
    for i, e in enumerate(estaciones, 1):
        print(f"  {i:>3}. {e}")

    if args.estaciones is not None:
        eleccion = args.estaciones
    elif args.no_interactivo:
        eleccion = ""
    else:
        print(f"\nEscribe estaciones separadas por coma. Acepta:")
        print(f"  - números         : 5")
        print(f"  - rangos          : 27-40")
        print(f"  - nombres         : COLLIGUAY")
        print(f"  - mezcla          : 1, 27-40, COLLIGUAY, 42")
        print(f"ENTER para usar: {', '.join(ESTACIONES_PREDEFINIDAS)}")
        eleccion = input("Selección: ").strip()

    seleccion, no_encontradas = parsear_seleccion(
        eleccion, estaciones, ESTACIONES_PREDEFINIDAS
    )
    if no_encontradas:
        print(f"\nIgnoradas (no encontradas): {no_encontradas}")
    if not seleccion:
        raise ValueError("No se seleccionó ninguna estación válida.")

    print(f"\nProcesando: {seleccion}\n")

    procesadas, fallidas = [], []
    for est in seleccion:
        try:
            procesar_estacion(df, col_fecha, col_val, col_est,
                              est, out_dir, tipo)
            procesadas.append(est)
        except Exception as e:
            print(f"ERROR en '{est}': {e}")
            fallidas.append((est, str(e)))

    # Exportación WEAP: un solo CSV con todas las estaciones procesadas
    if procesadas:
        try:
            exportar_weap(df, col_fecha, col_val, col_est,
                          procesadas, out_dir, tipo)
        except Exception as e:
            print(f"\nERROR generando archivo WEAP: {e}")

    print("\n=========== RESUMEN ===========")
    print(f"Procesadas: {procesadas}")
    if fallidas:
        print(f"Con error : {fallidas}")
    print(f"Salida    : {out_dir}")


if __name__ == "__main__":
    main()
