import os
import numpy as np
import pandas as pd

# 1. Definición de rutas
BASE_DIR = r"C:\Users\jorge\Desktop\Proyecto_opti"
output_dir = os.path.join(BASE_DIR, "data", "demand")
os.makedirs(output_dir, exist_ok=True)

files = {
    "regulados": os.path.join(BASE_DIR, "demanda_regulados_31_07.xlsx"),
    "pequenas_empresas": os.path.join(
        BASE_DIR, "demanda_pequenas_empresas_31_07.xlsx"
    ),
    "grandes_empresas": os.path.join(
        BASE_DIR, "demanda_grandes_empresas_31_07.xlsx"
    ),
}


def extraer_perfil_24h(file_path):
  """Lee un archivo de demanda del CEN y retorna un arreglo de 24 valores (MW o MWh)

  correspondientes a las 24 horas del día.
  """
  if not os.path.exists(file_path):
    raise FileNotFoundError(f"No se encontró el archivo: {file_path}")

  # Inspeccionar hojas del Excel
  xls = pd.ExcelFile(file_path)
  # Usar la primera hoja activa
  df = pd.read_excel(xls, sheet_name=xls.sheet_names[0])

  # Limpieza de nombres de columnas
  df.columns = [str(c).strip() for c in df.columns]

  # Caso A: Formato horizontal típico del CEN (columnas h1, h2, ... h24 o 1..24)
  # Buscamos columnas numéricas o que comiencen con 'H' o tengan formato de hora
  cols_horas = []
  for col in df.columns:
    # Coincide con '1', '2', ..., '24' o 'h1', 'h2', ..., 'h24'
    c_clean = col.lower().replace("h", "").replace("hora", "").strip()
    if c_clean.isdigit() and 1 <= int(c_clean) <= 24:
      cols_horas.append((int(c_clean), col))
    elif ":" in col:  # Formato '00:00', '01:00', etc.
      try:
        hr = int(col.split(":")[0])
        cols_horas.append((hr + 1, col))
      except ValueError:
        pass

  if len(cols_horas) >= 24:
    # Ordenar de hora 1 a 24
    cols_horas.sort(key=lambda x: x[0])
    selected_cols = [c[1] for c in cols_horas[:24]]

    # Convertir a numérico y sumar la demanda agregada de todas las barras/subestaciones del archivo
    data_numeric = df[selected_cols].apply(pd.to_numeric, errors="coerce")
    perfil = data_numeric.sum(axis=0).values
    return perfil

  # Caso B: Formato vertical (columnas 'Hora'/'Fecha' y 'Demanda'/'Potencia'/'MW')
  col_hora = None
  col_pot = None

  for col in df.columns:
    c_low = col.lower()
    if any(k in c_low for k in ["hora", "periodo", "intervalo", "time"]):
      col_hora = col
    if any(
        k in c_low
        for k in ["demanda", "potencia", "mw", "mwh", "valor", "activa"]
    ):
      col_pot = col

  if col_hora and col_pot:
    df[col_hora] = pd.to_numeric(df[col_hora], errors="coerce")
    df[col_pot] = pd.to_numeric(df[col_pot], errors="coerce").fillna(0.0)
    # Agrupar por hora (1 a 24 o 0 a 23)
    perfil_serie = df.groupby(col_hora)[col_pot].sum()
    if len(perfil_serie) == 24:
      return perfil_serie.values
    elif len(perfil_serie) == 96:  # Intervalos de 15 min (CEN a veces usa 96 bloques)
      # Agrupar de a 4 bloques para obtener 24 horas
      return perfil_serie.groupby(np.arange(len(perfil_serie)) // 4).mean().values

  # Si la estructura tiene encabezados en filas intermedias (skiprows)
  raise ValueError(
      f"No se pudo detectar automáticamente el formato en {os.path.basename(file_path)}. "
      f"Columnas detectadas: {df.columns.tolist()[:10]}"
  )


# 2. Procesar cada archivo
perfiles_mw = {}
perfiles_norm_max = {}
perfiles_norm_mean = {}

for tipo, path in files.items():
  print(f"Procesando {tipo}...")
  p_mw = extraer_perfil_24h(path)
  perfiles_mw[tipo] = p_mw

  # Normalización respecto al pico máximo del día: lambda_t in [0, 1]
  perfiles_norm_max[tipo] = (
      p_mw / np.max(p_mw) if np.max(p_mw) > 0 else np.zeros(24)
  )

  # Normalización respecto a la media diaria (útil si la carga base IEEE es promedio)
  perfiles_norm_mean[tipo] = (
      p_mw / np.mean(p_mw) if np.mean(p_mw) > 0 else np.zeros(24)
  )

# 3. Consolidar en DataFrames
# A) Factores normalizados respecto al pico diario (Max = 1.0)
df_norm_max = pd.DataFrame({
    "periodo_t": range(1, 25),
    "hora": range(24),
    "lambda_regulados": np.round(perfiles_norm_max["regulados"], 4),
    "lambda_pequenas": np.round(perfiles_norm_max["pequenas_empresas"], 4),
    "lambda_grandes": np.round(perfiles_norm_max["grandes_empresas"], 4),
})
output_csv_max = os.path.join(output_dir, "demand_profiles_norm_peak.csv")
df_norm_max.to_csv(output_csv_max, index=False)

# B) Factores normalizados respecto al promedio diario (Mean = 1.0)
df_norm_mean = pd.DataFrame({
    "periodo_t": range(1, 25),
    "hora": range(24),
    "lambda_regulados": np.round(perfiles_norm_mean["regulados"], 4),
    "lambda_pequenas": np.round(perfiles_norm_mean["pequenas_empresas"], 4),
    "lambda_grandes": np.round(perfiles_norm_mean["grandes_empresas"], 4),
})
output_csv_mean = os.path.join(output_dir, "demand_profiles_norm_mean.csv")
df_norm_mean.to_csv(output_csv_mean, index=False)

# C) Valores brutos sumados en MW
df_mw = pd.DataFrame({
    "periodo_t": range(1, 25),
    "hora": range(24),
    "P_MW_regulados": np.round(perfiles_mw["regulados"], 2),
    "P_MW_pequenas": np.round(perfiles_mw["pequenas_empresas"], 2),
    "P_MW_grandes": np.round(perfiles_mw["grandes_empresas"], 2),
})
df_mw.to_csv(os.path.join(output_dir, "demand_raw_aggregated_MW.csv"), index=False)

print("\n" + "=" * 50)
print(f"Perfiles procesados y guardados con éxito en: {output_dir}")
print(f"1. Normalizados respecto al pico: demand_profiles_norm_peak.csv")
print(f"2. Normalizados respecto a la media: demand_profiles_norm_mean.csv")
print("=" * 50)