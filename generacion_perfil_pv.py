import os
import numpy as np
import pandas as pd

# 1. Rutas
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
csv_path = os.path.join(BASE_DIR, "DHC_PV_MX1701.csv")

if not os.path.exists(csv_path):
    raise FileNotFoundError(f"No se encontró el archivo en: {csv_path}")

# 2. Carga directa saltando el bloque de metadatos (línea 54 es el encabezado)
print("Cargando serie horaria...")
df = pd.read_csv(csv_path, skiprows=54, low_memory=False)

# Limpiar nombres de columnas
df.columns = [c.strip() for c in df.columns]
print(f"Filas totales cargadas: {len(df)}")
print(f"Columnas detectadas: {df.columns.tolist()[:6]}")

# 3. Procesamiento temporal
# El formato de fecha es 'YYYY-MM-DD HH:MM:SS'
df["Fecha/Hora"] = pd.to_datetime(df["Fecha/Hora"])
df["mes"] = df["Fecha/Hora"].dt.month
df["hora"] = df["Fecha/Hora"].dt.hour

# 4. Asegurar formato numérico en la columna 'pv'
# La capacidad instalada base en el archivo es de 1 kW (P_nom = 1.0)
P_nom_kw = 1.0
df["pv"] = pd.to_numeric(df["pv"], errors="coerce").fillna(0.0)

# 5. Directorio de salida
output_dir = os.path.join(BASE_DIR, "data", "pv_profiles")
os.makedirs(output_dir, exist_ok=True)

meses = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
]

resumen_mensual = pd.DataFrame(index=range(1, 25))

# 6. Agregación horaria promedio multianual por mes (perfil representativo)
for m in range(1, 13):
    sub_df = df[df["mes"] == m]
    
    # Media de generación horaria a través de todos los años del dataset
    perfil_h = sub_df.groupby("hora")["pv"].mean()
    perfil_h = perfil_h.reindex(range(24), fill_value=0.0)
    
    # Normalización en p.u. acotada a [0, 1]
    alpha_t = np.clip(perfil_h.values / P_nom_kw, 0.0, 1.0)
    
    # Guardar en matriz anual consolidada
    resumen_mensual[meses[m - 1]] = np.round(alpha_t, 4)
    
    # Guardar perfil individual del mes (t=1..24, hora=0..23)
    df_mes = pd.DataFrame({
        "periodo_t": range(1, 25),
        "hora": range(24),
        "alpha_t": np.round(alpha_t, 4)
    })
    df_mes.to_csv(os.path.join(output_dir, f"alpha_t_mes_{m:02d}.csv"), index=False)

# Guardar matriz consolidada (24 filas x 12 meses)
resumen_mensual.index.name = "t"
resumen_mensual.to_csv(os.path.join(output_dir, "alpha_t_mensual_anual.csv"))

print(f"Perfiles PV generados exitosamente en: '{output_dir}'.")