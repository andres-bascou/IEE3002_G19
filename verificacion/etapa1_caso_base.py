"""
verificacion/etapa1_caso_base.py
================================
Etapa 1 del plan de implementación (Informe de Avance, Sec. III): replicación
del caso base SIN PV ni BESS, en un solo período (T = 1).

Se comparan tres soluciones de la red radial IEEE 33-bus (Baran & Wu, 1989):

  1. Referencia: flujo de potencia AC de pandapower (case33bw, 32 líneas radiales,
     Newton-Raphson, tolerancia 1e-10 MVA).
  2. SOCP independiente: escrito directamente desde las ecuaciones del informe
     (2)-(11) con la relajación cónica en la forma de norma euclidiana (7),
     usando los CSV de data/grid/ (no reutiliza código de modelo/).
  3. Modelo de producción: modelo/misocp_hc_bess.py (build_network + build_model)
     con demanda plana lambda = 1. Es el código que usarán las etapas 2 y 3, así
     que es la verificación que más importa. Se evalúan dos variantes:
       a) SOCP puro: pv_candidates = bess_candidates = []  (sin variables binarias)
       b) MISOCP: n_pv_max = n_bess_max = 0  (las binarias existen y quedan en 0)
     y se muestra, solo como información, (b) con las tolerancias POR DEFECTO de
     Gurobi, para dejar a la vista la pérdida de precisión.

Criterios de aceptación: la prueba física es la comparación con pandapower.
La brecha cónica se evalúa en forma RELATIVA, (v_pi*l - P^2 - Q^2)/(v_pi*l),
porque el umbral absoluto (28) <= 1e-4 p.u.^2 es demasiado laxo en esta red:
hay ramas con P^2+Q^2 ~ 5e-5 p.u.^2, donde duplicar l (corriente +41 %) aún
"cumpliría" (28). La brecha absoluta se reporta como información.

Sin PV ni BESS, la función objetivo (1) max sum_t [sum P^PV - c_deg sum P^dis
- sum r*l] dt se reduce a  min sum r*l  (minimizar pérdidas Joule).

Uso (desde cualquier carpeta):
    python3.10 verificacion/etapa1_caso_base.py

Nota de entorno: si matplotlib está compilado con NumPy 1.x, pandapower imprime
avisos de NumPy al importarse; son inofensivos para este script.
"""
import os
import sys
from collections import defaultdict, deque

import gurobipy as gp
import numpy as np
import pandapower as pp
import pandapower.networks as pn
import pandas as pd
from gurobipy import GRB

# OJO: NO usar rutas absolutas (p.ej. r"C:\Users\..." o "/Users/..."): solo funcionan en un PC.
# Se resuelve la raíz del proyecto relativa a este archivo (<raíz>/<carpeta>/este_script.py).
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # raíz del proyecto
DATA_DIR = os.path.join(BASE_DIR, "data")
sys.path.insert(0, BASE_DIR)

from modelo.misocp_hc_bess import (HCConfig, build_model, build_network,  # noqa: E402
                                   extract_results)

# -----------------------------------------------------------------------------
# Bases del sistema (case33bw) y parámetros de red
# -----------------------------------------------------------------------------
S_BASE = 10.0                                  # [MVA]
V_BASE = 12.66                                 # [kV] línea-línea
Z_BASE = V_BASE ** 2 / S_BASE                  # [Ohm]
I_BASE_KA = S_BASE / (np.sqrt(3.0) * V_BASE)   # [kA] (trifásico, V línea-línea)
V_SLACK = 1.0                                  # [p.u.] eq. (10)
S_SUB_MAX_PU = 1.0                             # [p.u.] eq. (11), igual a HCConfig.s_sub_max_pu
P_S_REF_PU = None                              # eq. (12): None = sin límite (igual que HCConfig)

# Tolerancias de solver: barrera muy ajustada para que la comparación no quede
# limitada por la precisión numérica del solver.
SOLVER_PARAMS = dict(BarQCPConvTol=1e-10, BarConvTol=1e-10,
                     FeasibilityTol=1e-9, OptimalityTol=1e-9, MIPGap=0.0)

# Tolerancias de aceptación (PASS/FAIL)
TOL_V_PU = 1e-4          # |dV| máximo por barra [p.u.]
TOL_I_REL = 1e-4         # |dI|/I máximo por rama [-] (relativo: las ramas finales llevan solo ~3.6 A)
TOL_LOSS_REL = 1e-3      # error relativo en pérdidas totales (0.1 %)
TOL_PQ_S_REL_PERD = 1e-3      # |dP_S|, |dQ_S| <= 0.1 % de las pérdidas de referencia (~0.2 kW)
TOL_GAP_REL = 1e-4       # brecha cónica relativa: l sobreestima |I|^2 en <= 0.01 % (|I| en <= 0.005 %),
                         # coherente con TOL_I_REL. Un umbral más fino solo mediría la convergencia
                         # de la barrera, no la física.
TOL_GAP_ABS_INFORME = 1e-4   # criterio (28) del informe [p.u.^2], solo informativo


# =============================================================================
# 1. REFERENCIA: flujo de potencia AC con pandapower
# =============================================================================
def referencia_pandapower() -> dict:
    net = pn.case33bw()
    net.line = net.line.iloc[:32].copy()       # quitar las 5 tie-lines (red radial)

    # El BFM no modela admitancia shunt de líneas ni cargas dependientes de la tensión:
    # se verifica explícitamente que case33bw no las tenga.
    L = net.line
    assert (L.c_nf_per_km == 0).all() and (L.g_us_per_km == 0).all(), \
        "Las líneas tienen admitancia shunt: el BFM sin shunt no aplica."
    assert (L.parallel == 1).all() and (L.df == 1).all(), "Líneas en paralelo o con df != 1."
    zip_cols = [c for c in net.load.columns if c.startswith("const_")]
    assert (net.load[zip_cols] == 0).all().all() and (net.load.scaling == 1).all(), \
        "Cargas no PQ constantes o escaladas."
    assert len(net.shunt) == len(net.trafo) == len(net.sgen) == len(net.gen) == 0, \
        "Elementos no modelados (shunt/trafo/sgen/gen) presentes."
    assert np.isclose(net.sn_mva, S_BASE) and np.allclose(net.bus.vn_kv, V_BASE)
    assert np.isclose(net.ext_grid.vm_pu.iloc[0], V_SLACK)

    pp.runpp(net, numba=False, tolerance_mva=1e-10)

    slack = int(net.ext_grid.bus.iloc[0])
    # Orientación aguas abajo (BFS desde la subestación) para comparar flujos emisor->receptor
    adj = defaultdict(list)
    for k, ln in net.line.iterrows():
        adj[int(ln.from_bus)].append((int(ln.to_bus), k))
        adj[int(ln.to_bus)].append((int(ln.from_bus), k))
    parent, line_of, seen, q = {}, {}, {slack}, deque([slack])
    while q:
        u = q.popleft()
        for w, k in adj[u]:
            if w not in seen:
                seen.add(w); parent[w] = u; line_of[w] = k; q.append(w)

    rl = net.res_line
    ramas = []
    for j, k in line_of.items():
        desde_from = int(net.line.at[k, "from_bus"]) == parent[j]
        ramas.append({
            "j": j + 1, "i": parent[j] + 1,   # numeración 1-based
            "P_MW": rl.at[k, "p_from_mw"] if desde_from else rl.at[k, "p_to_mw"],
            "Q_MVAr": rl.at[k, "q_from_mvar"] if desde_from else rl.at[k, "q_to_mvar"],
            "I_A": rl.at[k, "i_ka"] * 1000.0,
        })
    ramas = pd.DataFrame(ramas).set_index("j").sort_index()

    # Consistencia de datos: los r_pu/x_pu de data/grid/ deben coincidir con pandapower
    br = pd.read_csv(os.path.join(DATA_DIR, "grid", "ieee33_branches.csv"))
    r_pp = (L.r_ohm_per_km * L.length_km / Z_BASE).values
    x_pp = (L.x_ohm_per_km * L.length_km / Z_BASE).values
    err_rx = max(np.abs(br.r_pu.values - r_pp).max(), np.abs(br.x_pu.values - x_pp).max())

    return {
        "V": pd.Series(net.res_bus.vm_pu.values, index=net.bus.index + 1),
        "ramas": ramas,
        "perdidas_kW": rl.pl_mw.sum() * 1000.0,
        "P_S_MW": float(net.res_ext_grid.p_mw.iloc[0]),
        "Q_S_MVAr": float(net.res_ext_grid.q_mvar.iloc[0]),
        "gap": np.nan, "gap_rel": np.nan,
        "err_rx_csv": err_rx,
    }


# =============================================================================
# 2. SOCP INDEPENDIENTE (ecuaciones del informe, T = 1, sin PV/BESS)
# =============================================================================
def socp_independiente() -> dict:
    nodos = pd.read_csv(os.path.join(DATA_DIR, "grid", "ieee33_nodes.csv")).set_index("bus_id")
    ramas = pd.read_csv(os.path.join(DATA_DIR, "grid", "ieee33_branches.csv"))
    N = list(nodos.index)
    s = int(nodos.index[nodos.tipo == "slack"][0])

    # Orientación aguas abajo: padre pi(j) e hijos C(j) por BFS desde la subestación
    adj = defaultdict(list)
    for k, b in ramas.iterrows():
        adj[int(b.i)].append((int(b.j), k)); adj[int(b.j)].append((int(b.i), k))
    pi, rama_de, C, seen, q = {}, {}, defaultdict(list), {s}, deque([s])
    while q:
        u = q.popleft()
        for w, k in adj[u]:
            if w not in seen:
                seen.add(w); pi[w] = u; rama_de[w] = k; C[u].append(w); q.append(w)
    assert len(seen) == len(N) and len(ramas) == len(N) - 1, "La red no es un árbol."
    Np = [j for j in N if j != s]                                  # N+
    r = {j: float(ramas.at[rama_de[j], "r_pu"]) for j in Np}
    x = {j: float(ramas.at[rama_de[j], "x_pu"]) for j in Np}
    imax = {j: float(ramas.at[rama_de[j], "i_max_pu"]) for j in Np}
    PL = nodos.P0_pu.to_dict()                                     # lambda = 1
    QL = nodos.Q0_pu.to_dict()

    m = gp.Model("etapa1_socp_independiente")
    m.Params.OutputFlag = 0
    for k, val in SOLVER_PARAMS.items():
        if k != "MIPGap":
            setattr(m.Params, k, val)

    # (8) y (10): V_min^2 <= v_j <= V_max^2 ; v_1 = V_slack^2
    v = m.addVars(N, name="v", lb={j: nodos.at[j, "v_min_pu"] ** 2 for j in N},
                  ub={j: nodos.at[j, "v_max_pu"] ** 2 for j in N})
    v[s].LB = v[s].UB = V_SLACK ** 2
    # (9): 0 <= l <= (I_max)^2
    l = m.addVars(Np, name="l", lb=0.0, ub={j: imax[j] ** 2 for j in Np})
    P = m.addVars(Np, lb=-GRB.INFINITY, name="P")
    Q = m.addVars(Np, lb=-GRB.INFINITY, name="Q")
    PS = m.addVar(lb=-GRB.INFINITY, name="PS")
    QS = m.addVar(lb=-GRB.INFINITY, name="QS")

    for j in Np:
        # (2) y (4): balances nodales del BFM (sin PV ni BESS)
        m.addConstr(P[j] - r[j] * l[j] == PL[j] + gp.quicksum(P[k] for k in C[j]), name=f"Pbal[{j}]")
        m.addConstr(Q[j] - x[j] * l[j] == QL[j] + gp.quicksum(Q[k] for k in C[j]), name=f"Qbal[{j}]")
        # (6): caída de tensión
        m.addConstr(v[j] == v[pi[j]] - 2 * (r[j] * P[j] + x[j] * Q[j])
                    + (r[j] ** 2 + x[j] ** 2) * l[j], name=f"Vdrop[{j}]")
        # (7): || (2P, 2Q, v_pi - l) ||_2 <= v_pi + l   (cono de segundo orden estándar)
        a = m.addVar(lb=-GRB.INFINITY, name=f"a[{j}]")
        b = m.addVar(lb=0.0, name=f"b[{j}]")
        m.addConstr(a == v[pi[j]] - l[j]); m.addConstr(b == v[pi[j]] + l[j])
        m.addQConstr(4 * P[j] * P[j] + 4 * Q[j] * Q[j] + a * a <= b * b, name=f"SOC[{j}]")
    # (3) y (5): balance en la subestación
    m.addConstr(PS == PL[s] + gp.quicksum(P[k] for k in C[s]), name="PS")
    m.addConstr(QS == QL[s] + gp.quicksum(Q[k] for k in C[s]), name="QS")
    # (11) capacidad del transformador y (12) exportación neta
    m.addQConstr(PS * PS + QS * QS <= S_SUB_MAX_PU ** 2, name="Ssub")
    if P_S_REF_PU is not None:
        m.addConstr(PS >= P_S_REF_PU, name="Prev")

    # (1) sin PV ni BESS  <=>  min sum r*l
    m.setObjective(gp.quicksum(r[j] * l[j] for j in Np), GRB.MINIMIZE)
    m.optimize()
    if m.Status != GRB.OPTIMAL:
        raise RuntimeError(f"SOCP independiente no óptimo (status {m.Status}).")

    gap = {j: v[pi[j]].X * l[j].X - (P[j].X ** 2 + Q[j].X ** 2) for j in Np}   # (28)
    return {
        "V": pd.Series({j: np.sqrt(v[j].X) for j in N}).sort_index(),
        "ramas": pd.DataFrame({"i": pi, "P_MW": {j: P[j].X * S_BASE for j in Np},
                               "Q_MVAr": {j: Q[j].X * S_BASE for j in Np},
                               "I_A": {j: np.sqrt(max(l[j].X, 0.0)) * I_BASE_KA * 1000 for j in Np}}
                              ).sort_index(),
        "perdidas_kW": m.ObjVal * S_BASE * 1000.0,
        "P_S_MW": PS.X * S_BASE, "Q_S_MVAr": QS.X * S_BASE,
        "gap": max(abs(g) for g in gap.values()),
        "gap_rel": max(abs(gap[j]) / (v[pi[j]].X * l[j].X) for j in Np),
    }


# =============================================================================
# 3. MODELO DE PRODUCCIÓN: modelo/misocp_hc_bess.py
# =============================================================================
def modelo_produccion(sin_binarias: bool = True, ajustar_tolerancias: bool = True) -> dict:
    """sin_binarias=True: candidatos vacíos (SOCP puro). False: n_pv_max = n_bess_max = 0 (MISOCP)."""
    nodos = pd.read_csv(os.path.join(DATA_DIR, "grid", "ieee33_nodes.csv"))
    ramas = pd.read_csv(os.path.join(DATA_DIR, "grid", "ieee33_branches.csv"))
    # Demanda plana: lambda = 1 para todos los tipos de cliente (cargas base del caso)
    demanda = pd.DataFrame({"lambda_regulados": [1.0], "lambda_pequenas": [1.0],
                            "lambda_grandes": [1.0]}, index=[1])
    extra = dict(pv_candidates=[], bess_candidates=[]) if sin_binarias else {}
    cfg = HCConfig(T=1, n_pv_max=0, n_bess_max=0, time_limit=None, output_flag=0, **extra)
    net = build_network(nodos, ramas, demanda, cfg)
    alpha = pd.Series([0.0], index=[1])        # sin recurso solar (irrelevante con n_pv_max = 0)
    m, X = build_model(net, alpha, cfg)
    if ajustar_tolerancias:
        for k, val in SOLVER_PARAMS.items():
            setattr(m.Params, k, val)
    m.optimize()
    if m.SolCount == 0:
        raise RuntimeError(f"Modelo de producción sin solución (status {m.Status}).")
    res = extract_results(m, X, net, cfg)

    bf = res["branch_flows"].set_index("to").sort_index()
    gap_rel = max(res["conic_gap_map"][j, 1] / (X["v"][net.parent[j], 1].X * X["l"][j, 1].X)
                  for j in net.nplus)
    return {
        "V": res["voltages"].loc[1].sort_index(),
        "ramas": bf.rename(columns={"from": "i"})[["i", "P_MW", "Q_MVAr", "I_A"]],
        "perdidas_kW": res["summary"]["losses_MWh"] * 1000.0,   # T = 1, dt = 1 h => MWh == MW
        "P_S_MW": float(res["substation"]["P_S_MW"].iloc[0]),
        "Q_S_MVAr": float(res["substation"]["Q_S_MVAr"].iloc[0]),
        "gap": res["summary"]["conic_gap_pu2"], "gap_rel": gap_rel,
        "status": m.Status, "es_mip": bool(m.IsMIP),
    }


# =============================================================================
# 4. COMPARACIÓN Y REPORTE
# =============================================================================
def comparar(ref: dict, sol: dict, nombre: str) -> bool:
    dV = (sol["V"] - ref["V"]).abs()
    assert (sol["ramas"]["i"] == ref["ramas"]["i"]).all(), "Orientación de ramas distinta."
    dI = (sol["ramas"]["I_A"] - ref["ramas"]["I_A"]).abs()
    dI_rel = dI / ref["ramas"]["I_A"]
    dP = (sol["ramas"]["P_MW"] - ref["ramas"]["P_MW"]).abs()
    dQ = (sol["ramas"]["Q_MVAr"] - ref["ramas"]["Q_MVAr"]).abs()
    e_loss = abs(sol["perdidas_kW"] - ref["perdidas_kW"]) / ref["perdidas_kW"]
    dPS = abs(sol["P_S_MW"] - ref["P_S_MW"])
    dQS = abs(sol["Q_S_MVAr"] - ref["Q_S_MVAr"])
    tol_pq = TOL_PQ_S_REL_PERD * ref["perdidas_kW"] / 1000.0          # [MW]

    criterios = [
        (f"max |dV| [p.u.]  (barra {dV.idxmax()})", dV.max(), TOL_V_PU),
        (f"max |dI|/I [-]   (rama -> {dI_rel.idxmax()})", dI_rel.max(), TOL_I_REL),
        ("error rel. pérdidas [-]", e_loss, TOL_LOSS_REL),
        ("|dP_S| [MW]", dPS, tol_pq),
        ("|dQ_S| [MVAr]", dQS, tol_pq),
        ("brecha cónica relativa [-]", sol["gap_rel"], TOL_GAP_REL),
    ]
    print(f"\n--- {nombre} vs pandapower ---")
    ok_total = True
    for txt, val, tol in criterios:
        ok = bool(val <= tol)
        ok_total &= ok
        print(f"  {txt:<38} {val:12.3e}   tol {tol:9.1e}   {'PASS' if ok else 'FAIL'}")
    print(f"  (info) max |dI| = {dI.max():.3e} A, max |dP_rama| = {dP.max():.3e} MW, "
          f"max |dQ_rama| = {dQ.max():.3e} MVAr")
    print(f"  (info) brecha absoluta (28) = {sol['gap']:.3e} p.u.^2 "
          f"({'cumple' if sol['gap'] <= TOL_GAP_ABS_INFORME else 'no cumple'} el umbral 1e-4 del informe)")
    print(f"  RESULTADO: {'PASS' if ok_total else 'FAIL'}")
    return ok_total


def main() -> int:
    print("=" * 78)
    print("ETAPA 1: caso base IEEE 33-bus sin PV ni BESS (T = 1) — SOCP vs flujo AC")
    print("=" * 78)
    ref = referencia_pandapower()
    ind = socp_independiente()
    prod = modelo_produccion(sin_binarias=True)                       # (a) SOCP puro
    prod_mip = modelo_produccion(sin_binarias=False)                  # (b) MISOCP, n = 0
    prod_def = modelo_produccion(sin_binarias=False, ajustar_tolerancias=False)  # (b) por defecto

    print(f"Consistencia data/grid vs pandapower: max |d r_pu|, |d x_pu| = {ref['err_rx_csv']:.2e}")
    for nombre, d in [("(a) candidatos vacíos", prod), ("(b) n_pv_max = n_bess_max = 0", prod_mip)]:
        print(f"Producción {nombre}: status Gurobi {d['status']}, "
              f"{'MISOCP (binarias fijadas a 0 por presupuesto)' if d['es_mip'] else 'SOCP continuo'}")

    # Resumen global
    filas = []
    for nombre, d in [("pandapower (AC)", ref), ("SOCP independiente", ind),
                      ("Producción (a) SOCP", prod), ("Producción (b) MISOCP", prod_mip),
                      ("(b) tol. por defecto [info]", prod_def)]:
        filas.append({"solución": nombre, "V_min [p.u.]": d["V"].min(), "barra V_min": int(d["V"].idxmin()),
                      "pérdidas [kW]": d["perdidas_kW"], "P_S [MW]": d["P_S_MW"],
                      "Q_S [MVAr]": d["Q_S_MVAr"], "I_cabecera [A]": d["ramas"]["I_A"].iloc[0],
                      "max|dI|/I": ((d["ramas"]["I_A"] - ref["ramas"]["I_A"]).abs()
                                    / ref["ramas"]["I_A"]).max(),
                      "brecha abs (28)": d["gap"], "brecha rel": d["gap_rel"]})
    print("\nResumen global:")
    print(pd.DataFrame(filas).set_index("solución").to_string(
        float_format=lambda z: f"{z:.6f}" if abs(z) >= 1e-3 or z == 0 else f"{z:.2e}"))

    # Tabla por barra
    tb = pd.DataFrame({"V_pp": ref["V"], "V_socp": ind["V"], "V_prod": prod["V"]})
    tb["dV_socp"] = tb.V_socp - tb.V_pp
    tb["dV_prod"] = tb.V_prod - tb.V_pp
    tb.index.name = "barra"
    print("\nTensiones por barra [p.u.]:")
    print(tb.to_string(float_format=lambda z: f"{z: .6f}" if abs(z) > 1e-3 else f"{z: .2e}"))

    # Tabla por rama
    tr = pd.DataFrame({"i": ref["ramas"]["i"], "I_pp": ref["ramas"]["I_A"],
                       "I_socp": ind["ramas"]["I_A"], "I_prod": prod["ramas"]["I_A"],
                       "P_pp_MW": ref["ramas"]["P_MW"], "Q_pp_MVAr": ref["ramas"]["Q_MVAr"]})
    tr["dI_socp"] = tr.I_socp - tr.I_pp
    tr["dI_prod"] = tr.I_prod - tr.I_pp
    tr.index.name = "j"
    print("\nRamas (pi(j) -> j): corriente [A] y flujo emisor de pandapower:")
    print(tr.to_string(float_format=lambda z: f"{z: .4f}" if abs(z) > 1e-3 else f"{z: .2e}"))

    ok1 = comparar(ref, ind, "SOCP independiente")
    ok2 = comparar(ref, prod, "Producción (a): SOCP puro, candidatos vacíos")
    ok3 = comparar(ref, prod_mip, "Producción (b): MISOCP con n_pv_max = n_bess_max = 0")
    print("\n(info) Producción (b) con tolerancias por defecto de Gurobi: "
          f"max|dV| = {(prod_def['V'] - ref['V']).abs().max():.1e} p.u., "
          f"brecha relativa = {prod_def['gap_rel']:.1e}, brecha absoluta = {prod_def['gap']:.1e} p.u.^2.")
    print("       Cumple (28) del informe, pero la corriente en ramas finales difiere ~"
          f"{100 * ((prod_def['ramas']['I_A'] - ref['ramas']['I_A']).abs() / ref['ramas']['I_A']).max():.1f} %: "
          "para las etapas 2-3 conviene ajustar tolerancias y usar la brecha relativa.")
    ok = ok1 and ok2 and ok3
    print("\n" + "=" * 78)
    print(f"ETAPA 1: {'PASS' if ok else 'FAIL'}  (independiente: {'PASS' if ok1 else 'FAIL'}, "
          f"producción (a): {'PASS' if ok2 else 'FAIL'}, producción (b): {'PASS' if ok3 else 'FAIL'})")
    print("=" * 78)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
