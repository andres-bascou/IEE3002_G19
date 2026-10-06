"""Generador de datos de la red de distribución IEEE 33-bus (Baran & Wu, 1989).

Extrae la red desde pandapower (case33bw), aplica las bases de potencia y tensión,
resuelve el mapeo radial de árbol (padre pi(j) e hijos C(j)) y exporta los archivos
consolidados en 'data/grid/'.
"""

import os
import numpy as np
import pandas as pd
import pandapower as pp
import pandapower.networks as pn

# 1. Rutas del proyecto
BASE_DIR = os.path.dirname(os.path.abspath(__file__)) if "__file__" in locals() else os.getcwd()
OUTPUT_DIR = os.path.join(BASE_DIR, "data", "grid")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 2. Cargar instancia estándar de pandapower
net = pn.case33bw()

# 3. Bases del sistema y constantes
S_BASE = float(net.sn_mva)               # 10.0 MVA
V_BASE = float(net.bus.vn_kv.iloc[0])    # 12.66 kV (línea-línea)
Z_BASE = (V_BASE ** 2) / S_BASE          # 16.02756 Ohm
I_BASE = S_BASE / (np.sqrt(3) * V_BASE)  # 0.4558 kA = 455.8 A

# Capacidad térmica de conductores según benchmark (Blanco-Solano et al., 2026)
I_MAX_A = 300.0                          # Amperes
I_MAX_PU = (I_MAX_A / 1000.0) / I_BASE   # ~0.6582 p.u.

# Límites de tensión en nodos
V_MIN_PU = 0.90
V_MAX_PU = 1.10
V_SLACK_PU = 1.00

print("=" * 60)
print(f"Bases del Sistema: S_base = {S_BASE} MVA | V_base = {V_BASE} kV")
print(f"Z_base = {Z_BASE:.4f} Ohm | I_base = {I_BASE*1000:.2f} A | I_max = {I_MAX_PU:.4f} p.u.")
print("=" * 60)

# 4. Procesamiento de ramas (solo las 32 líneas radiales estructurales)
# Se ignoran explícitamente los índices 32 al 36 (tie-lines) para asegurar topología de árbol
lines = net.line.iloc[:32].copy().reset_index(drop=True)

df_ramas = pd.DataFrame({
    "line_id": lines.index + 1,
    "i": lines.from_bus.astype(int) + 1,  # 1-based (Nodo 1 = Subestación)
    "j": lines.to_bus.astype(int) + 1,
    "r_pu": (lines.r_ohm_per_km * lines.length_km) / Z_BASE,
    "x_pu": (lines.x_ohm_per_km * lines.length_km) / Z_BASE,
    "length_km": lines.length_km,
    "i_max_pu": I_MAX_PU,
})

# Verificación matemática estricta de topología de árbol
N_BUSES = len(net.bus)
assert len(df_ramas) == N_BUSES - 1, f"Error topológico crítico: Se esperaban {N_BUSES - 1} ramas, hay {len(df_ramas)}. Hay lazos presentes."

# 5. Procesamiento de barras (nodos) y cargas base
loads_dict_p = dict(zip(net.load.bus + 1, net.load.p_mw))
loads_dict_q = dict(zip(net.load.bus + 1, net.load.q_mvar))

df_nodos = pd.DataFrame({
    "bus_id": range(1, N_BUSES + 1),
    "tipo": ["slack" if b == 1 else "load" for b in range(1, N_BUSES + 1)],
    "v_min_pu": [V_SLACK_PU if b == 1 else V_MIN_PU for b in range(1, N_BUSES + 1)],
    "v_max_pu": [V_SLACK_PU if b == 1 else V_MAX_PU for b in range(1, N_BUSES + 1)],
    "P0_MW": [loads_dict_p.get(b, 0.0) for b in range(1, N_BUSES + 1)],
    "Q0_MVAR": [loads_dict_q.get(b, 0.0) for b in range(1, N_BUSES + 1)],
})

# Conversión a p.u.
df_nodos["P0_pu"] = df_nodos["P0_MW"] / S_BASE
df_nodos["Q0_pu"] = df_nodos["Q0_MVAR"] / S_BASE

# 6. Asignación de tipo de cliente para el acoplamiento con perfiles CEN
tipos_cliente = []
for b in df_nodos["bus_id"]:
    if b == 1:
        tipos_cliente.append("none")
    elif 19 <= b <= 22:
        tipos_cliente.append("pequenas")
    elif b in [24, 25, 30, 31, 32]:
        tipos_cliente.append("grandes")
    else:
        tipos_cliente.append("regulados")

df_nodos["customer_type"] = tipos_cliente

# 7. Exportar archivos estructurados
path_ramas = os.path.join(OUTPUT_DIR, "ieee33_branches.csv")
path_nodos = os.path.join(OUTPUT_DIR, "ieee33_nodes.csv")

df_ramas.to_csv(path_ramas, index=False)
df_nodos.to_csv(path_nodos, index=False)

print(f"Ramas guardadas en: {path_ramas} ({len(df_ramas)} filas)")
print(f"Nodos y cargas base guardados en: {path_nodos} ({len(df_nodos)} filas)")

# Resumen de validación rápida
total_p = df_nodos["P0_MW"].sum()
total_q = df_nodos["Q0_MVAR"].sum()
print(f"\nDemanda total base de la red: {total_p:.3f} MW | {total_q:.3f} MVAr")
print("Estructura de red generada y lista para el modelo de optimización radial.")