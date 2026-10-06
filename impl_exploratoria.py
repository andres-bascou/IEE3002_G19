"""
Exploración de la instancia IEEE 33-bus para el modelo de Hosting Capacity + BESS.

Fuente de los datos:
  M. E. Baran and F. F. Wu, "Network reconfiguration in distribution systems
  for loss reduction and load balancing," IEEE Trans. Power Delivery, vol. 4,
  no. 2, pp. 1401-1407, Apr. 1989, doi: 10.1109/61.25627.
  Cargada desde pandapower (pandapower.networks.case33bw), que reproduce el
  caso case33bw de MATPOWER. Es la misma red usada como benchmark en
  Blanco-Solano et al. (2026), Sec. 4.1.

Requisitos:  pip install pandapower
"""
import pandas as pd
import pandapower as pp
import pandapower.networks as pn

net = pn.case33bw()

# --- Bases del sistema -------------------------------------------------------
S_BASE = net.sn_mva                      # 10 MVA
V_BASE = net.bus.vn_kv.iloc[0]           # 12.66 kV (línea-línea)
Z_BASE = V_BASE**2 / S_BASE              # ohm
I_BASE = S_BASE / (3**0.5 * V_BASE)      # kA
print(f"S_base = {S_BASE} MVA | V_base = {V_BASE} kV | Z_base = {Z_BASE:.3f} ohm")

# --- Ramas: solo las en servicio forman el árbol radial ----------------------
# case33bw trae 37 líneas: 32 en servicio + 5 de enlace (tie lines) abiertas,
# que existen para estudios de reconfiguración. Para nuestro modelo se ignoran.
lines = net.line[net.line.in_service].copy()
print(f"Líneas: {len(net.line)} totales, {len(lines)} en servicio")

# Numeración del informe: barra pandapower 0 -> nodo 1 (subestación)
ramas = pd.DataFrame({
    "i": lines.from_bus + 1,
    "j": lines.to_bus + 1,
    "r_pu": lines.r_ohm_per_km * lines.length_km / Z_BASE,
    "x_pu": lines.x_ohm_per_km * lines.length_km / Z_BASE,
}).reset_index(drop=True)

# --- Cargas P^L_j, Q^L_j en p.u. (valores base, sin perfil horario) ----------
cargas = pd.DataFrame({
    "j": net.load.bus + 1,
    "PL_pu": net.load.p_mw / S_BASE,
    "QL_pu": net.load.q_mvar / S_BASE,
})
print(f"Demanda total: {net.load.p_mw.sum():.3f} MW, {net.load.q_mvar.sum():.3f} MVAr")

# --- Estructura de árbol: padre pi(j) e hijos C(j) ---------------------------
N = len(net.bus)
assert len(ramas) == N - 1, "No es radial: |S_br| != |N| - 1"
padre = dict(zip(ramas.j, ramas.i))
assert len(padre) == N - 1, "Alguna barra tiene más de un padre"
hijos = {n: ramas.j[ramas.i == n].tolist() for n in range(1, N + 1)}
print("Hijos de la subestación (nodo 1):", hijos[1])
print("Nodos con más de un hijo (inicio de laterales):",
      {n: c for n, c in hijos.items() if len(c) > 1})

# --- Datos que la instancia NO trae y hay que suponer -------------------------
# max_i_ka = 99999 en pandapower significa "sin límite". El paper usa 300 A.
print(f"max_i_ka en la instancia: {lines.max_i_ka.unique()}  -> definir I_max")
I_MAX_A = 300
print(f"I_max = {I_MAX_A} A = {I_MAX_A / 1000 / I_BASE:.3f} p.u.")

# --- Caso base: flujo AC sin PV (referencia para validar el modelo) ----------
pp.runpp(net)
vm = net.res_bus.vm_pu
print(f"\nCaso base sin PV:")
print(f"  V min = {vm.min():.4f} p.u. en nodo {vm.idxmin() + 1}")
print(f"  Pérdidas = {net.res_line.pl_mw.sum() * 1000:.1f} kW")
print(f"  Importación subestación = {net.res_ext_grid.p_mw.iloc[0]:.3f} MW")

# --- Exportar tablas para la implementación ----------------------------------
ramas.to_csv("ieee33_ramas.csv", index=False)
cargas.to_csv("ieee33_cargas.csv", index=False)
print("\nGuardado: ieee33_ramas.csv, ieee33_cargas.csv")
print(ramas.head()) 