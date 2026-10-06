import os
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# Rutas
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROFILES_DIR = os.path.join(BASE_DIR, "data", "pv_profiles")
csv_consolidado = os.path.join(PROFILES_DIR, "alpha_t_mensual_anual.csv")

if not os.path.exists(csv_consolidado):
    raise FileNotFoundError(f"No se encontró el archivo consolidado en: {csv_consolidado}")

df_perfiles = pd.read_csv(csv_consolidado, index_col="t")
horas = np.arange(0, 24)  # 0 a 23 h

# -------------------------------------------------------------
# Gráfico 1: Comparativa estacional (Curvas horarias)
# -------------------------------------------------------------
meses_muestra = ["Enero", "Abril", "Julio", "Octubre"]
colores = ["#d95f02", "#7570b3", "#1b9e77", "#e7298a"]

plt.figure(figsize=(10, 5))

for mes, color in zip(meses_muestra, colores):
    if mes in df_perfiles.columns:
        plt.plot(
            horas,
            df_perfiles[mes],
            label=mes,
            color=color,
            linewidth=2.0,
            marker="o",
            markersize=3,
        )

plt.title(r"Perfiles Diarios Típicos de Generación PV ($\alpha_t$)", fontsize=13)
plt.xlabel("Hora del Día [h]", fontsize=11)
plt.ylabel(r"Factor de Generación $\alpha_t$ [p.u.]", fontsize=11)
plt.xlim(0, 23)
plt.ylim(0, 1.05)
plt.xticks(np.arange(0, 24, 2))
plt.grid(True, linestyle="--", alpha=0.6)
plt.legend(frameon=True, loc="upper right")
plt.tight_layout()

fig1_path = os.path.join(PROFILES_DIR, "verificacion_estacional.png")
plt.savefig(fig1_path, dpi=300)
print(f"Gráfico estacional guardado en: {fig1_path}")

# -------------------------------------------------------------
# Gráfico 2: Heatmap 2D (Horas vs Meses)
# -------------------------------------------------------------
plt.figure(figsize=(9, 6))

matriz_pv = df_perfiles.values  # Dimensión: 24 x 12
im = plt.imshow(
    matriz_pv,
    aspect="auto",
    cmap="YlOrRd",
    origin="lower",
    extent=[-0.5, 11.5, -0.5, 23.5],
)

cbar = plt.colorbar(im)
cbar.set_label(r"Factor de Generación $\alpha_t$ [p.u.]", fontsize=10)

plt.title("Distribución Horaria Anual de Generación PV", fontsize=13)
plt.xlabel("Mes", fontsize=11)
plt.ylabel("Hora del Día [h]", fontsize=11)
plt.xticks(ticks=range(12), labels=df_perfiles.columns, rotation=45, ha="right")
plt.yticks(np.arange(0, 24, 2))
plt.tight_layout()

fig2_path = os.path.join(PROFILES_DIR, "verificacion_heatmap.png")
plt.savefig(fig2_path, dpi=300)
print(f"Heatmap anual guardado en: {fig2_path}")

# Mostrar ambas figuras en pantalla
plt.show()