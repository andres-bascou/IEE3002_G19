import os
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# 1. Definición de rutas base
BASE_DIR = r"C:\Users\jorge\Desktop\Proyecto_opti"
DIR_PV = os.path.join(BASE_DIR, "data", "pv_profiles")
DIR_DEM = os.path.join(BASE_DIR, "data", "demand")

# 2. Cargar perfiles procesados
# Archivo de demanda normalizada (pico = 1.0)
df_dem_norm = pd.read_csv(os.path.join(DIR_DEM, "demand_profiles_norm_peak.csv"))
# Archivo de demanda agregada bruta en MW
df_dem_mw = pd.read_csv(os.path.join(DIR_DEM, "demand_raw_aggregated_MW.csv"))

# Archivo solar: mes 07 (Julio, correspondiente a la fecha 31_07 del CEN)
path_pv_jul = os.path.join(DIR_PV, "alpha_t_mes_07.csv")
if os.path.exists(path_pv_jul):
  df_pv = pd.read_csv(path_pv_jul)
  alpha_t = df_pv["alpha_t"].values
else:
  # Alternativa: leer matriz consolidada anual
  df_pv_all = pd.read_csv(
      os.path.join(DIR_PV, "alpha_t_mensual_anual.csv"), index_col="t"
  )
  alpha_t = df_pv_all["Julio"].values

horas = df_dem_norm["hora"].values

# 3. Comprobaciones de consistencia técnica
print("=" * 60)
print("REPORTE DE VERIFICACIÓN DE PERFILES (24 HORAS)")
print("=" * 60)

# Verificación de rangos numéricos
for col in ["lambda_regulados", "lambda_pequenas", "lambda_grandes"]:
  val_min = df_dem_norm[col].min()
  val_max = df_dem_norm[col].max()
  peak_hour = df_dem_norm.loc[df_dem_norm[col].idxmax(), "hora"]
  print(
      f"• {col:<20}: Rango [{val_min:.3f}, {val_max:.3f}] | Hora punta:"
      f" {peak_hour:02d}:00 h"
  )

val_pv_max = np.max(alpha_t)
hora_pv_max = horas[np.argmax(alpha_t)]
horas_sol = horas[alpha_t > 0.001]
print(
    f"• Perfil Solar alpha_t: Pico = {val_pv_max:.3f} a las {hora_pv_max:02d}:00"
    f" h | Ventana solar: {horas_sol[0]:02d}:00 a {horas_sol[-1]:02d}:00 h"
)

# Coincidencia crítica: Demanda en hora de máxima radiación solar (desacople valle/pico)
dem_reg_al_mediodia = df_dem_norm.loc[
    df_dem_norm["hora"] == hora_pv_max, "lambda_regulados"
].values[0]
print(
    f"• Factor de carga regulada en hora de máxima inyección ({hora_pv_max:02d}:00):"
    f" {dem_reg_al_mediodia:.2%}"
)
print("=" * 60)

# 4. Creación de Gráficos de Comprobación
fig, axs = plt.subplots(1, 3, figsize=(18, 5), dpi=120)

# Gráfico 1: Factores Normalizados de Demanda (p.u.)
axs[0].plot(
    horas,
    df_dem_norm["lambda_regulados"],
    "o-",
    color="#1f77b4",
    linewidth=2,
    label="Regulados (Residencial)",
)
axs[0].plot(
    horas,
    df_dem_norm["lambda_pequenas"],
    "s--",
    color="#2ca02c",
    linewidth=2,
    label="Pequeña Empresa",
)
axs[0].plot(
    horas,
    df_dem_norm["lambda_grandes"],
    "^--",
    color="#9467bd",
    linewidth=2,
    label="Gran Empresa",
)
axs[0].set_title(
    "Factores de Demanda Normalizados ($\lambda_t$)", fontweight="bold"
)
axs[0].set_xlabel("Hora del Día [h]")
axs[0].set_ylabel("Factor de Carga [p.u.]")
axs[0].set_xticks(range(0, 24, 2))
axs[0].set_ylim(0, 1.05)
axs[0].grid(True, linestyle=":", alpha=0.6)
axs[0].legend(loc="lower right")

# Gráfico 2: Demanda Bruta Agregada del CEN (MW)
axs[1].plot(
    horas,
    df_dem_mw["P_MW_regulados"],
    "o-",
    color="#1f77b4",
    linewidth=2,
    label="Regulados",
)
axs[1].plot(
    horas,
    df_dem_mw["P_MW_pequenas"],
    "s--",
    color="#2ca02c",
    linewidth=2,
    label="Pequeña Empresa",
)
axs[1].plot(
    horas,
    df_dem_mw["P_MW_grandes"],
    "^--",
    color="#9467bd",
    linewidth=2,
    label="Gran Empresa",
)
axs[1].set_title("Demanda Agregada CEN (31 de Julio)", fontweight="bold")
axs[1].set_xlabel("Hora del Día [h]")
axs[1].set_ylabel("Potencia Activa [MW]")
axs[1].set_xticks(range(0, 24, 2))
axs[1].grid(True, linestyle=":", alpha=0.6)
axs[1].legend(loc="best")

# Gráfico 3: Coincidencia Despacho Solar vs. Curva de Regulados (Hosting Capacity Test)
ax3_sol = axs[2]
ax3_dem = ax3_sol.twinx()

# Área solar
ax3_sol.fill_between(
    horas,
    alpha_t,
    color="#ff7f0e",
    alpha=0.35,
    label=r"Disponibilidad Solar $\alpha_t$",
)
p_sol = ax3_sol.plot(
    horas,
    alpha_t,
    "-",
    color="#d62728",
    linewidth=2,
    label=r"Curva Solar $\alpha_t$",
)

# Línea de demanda regulada
p_dem = ax3_dem.plot(
    horas,
    df_dem_norm["lambda_regulados"],
    "o-",
    color="#1f77b4",
    linewidth=2,
    label=r"Demanda Regulados $\lambda_t$",
)

ax3_sol.set_title(
    "Superposición Solar vs. Demanda Residencial", fontweight="bold"
)
ax3_sol.set_xlabel("Hora del Día [h]")
ax3_sol.set_ylabel(
    r"Factor Solar $\alpha_t$ [p.u.]", color="#d62728", fontweight="bold"
)
ax3_dem.set_ylabel(
    r"Factor Demanda $\lambda_t$ [p.u.]", color="#1f77b4", fontweight="bold"
)
ax3_sol.set_xticks(range(0, 24, 2))
ax3_sol.set_ylim(0, 1.05)
ax3_dem.set_ylim(0, 1.05)
ax3_sol.grid(True, linestyle=":", alpha=0.6)

# Leyenda combinada
lineas = p_sol + p_dem
etiquetas = [l.get_label() for l in lineas]
ax3_sol.legend(lineas, etiquetas, loc="upper left")

plt.tight_layout()
plt.savefig(
    os.path.join(BASE_DIR, "comprobacion_perfiles.png"),
    dpi=300,
    bbox_inches="tight",
)
plt.show()
print(
    f"\nGráfico guardado como 'comprobacion_perfiles.png' en: {BASE_DIR}"
)