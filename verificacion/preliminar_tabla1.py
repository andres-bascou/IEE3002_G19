"""
verificacion/preliminar_tabla1.py
=================================
*** PRELIMINAR ***  Resultados exploratorios para la Etapa 2 (replicar la Tabla 1 de [4]).
El equipo AÚN NO decide cambiar el modelo del informe al MIQCP exacto ni a la función
objetivo (10) de [4]; este script solo documenta lo que se observa con cada alternativa.

Referencia [4]: J. Blanco-Solano, D. J. Chacón Molina, D. L. Chaustre Cárdenas,
"Enhanced optimization-based PV hosting capacity method for improved planning of real
distribution networks," Electricity, vol. 7, no. 1, art. 12, 2026 (Sec. 4.1 y Tabla 1).
PDF local (no versionado): docs/papers/04_blanco-solano_2026.pdf

Configuración de la Tabla 1 de [4] (Sec. 4.1):
    carga base (T = 1, lambda = 1), PV con factor de potencia unitario (alpha = 1),
    tensiones 0.9-1.1 p.u. (CSV de data/grid), I_max = 300 A en todas las líneas,
    intercambio con la red aguas arriba <= 4.6 MW  =>  P_S >= -0.46 p.u. (exportación),
    sin BESS, sin tope por proyecto PV en [4] (aquí 20 MW por barra, no activo).
    Escenario 1: todas las barras candidatas.  Escenario 2: solo barras 2 y 3.

Modelos comparados (todos construidos con modelo/misocp_hc_bess.py):
    * MIQCP exacto:     la relajación cónica se reemplaza por la igualdad
                        P^2 + Q^2 = v*l  (ec. (15) de [4]); Gurobi NonConvex = 2.
    * MISOCP relajado:  el modelo del informe, P^2 + Q^2 <= v*l.
    Ambos con el objetivo (10) de [4]: max sum P^PV.
    Además, con el objetivo (1) del informe (relajado) se mide el rango de HC que
    alcanza el MISMO valor óptimo de la función objetivo (indeterminación).

Cada solución se valida con un flujo de potencia AC de pandapower (PV como sgen, fp = 1).

Uso (desde cualquier carpeta):
    python verificacion/preliminar_tabla1.py
Escribe results/preliminar_tabla1.json (lo leen los gráficos de presentacion/).
"""
import json
import os
import sys

import gurobipy as gp
import numpy as np
import pandapower as pp
import pandapower.networks as pn
import pandas as pd
from gurobipy import GRB

# OJO: NO usar rutas absolutas (p.ej. r"C:\Users\..." o "/Users/..."): solo funcionan en un PC.
# Se resuelve la raíz del proyecto relativa a este archivo (<raíz>/<carpeta>/este_script.py).
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # raíz del proyecto
sys.path.insert(0, BASE_DIR)

from modelo.misocp_hc_bess import (HCConfig, build_model, build_network,  # noqa: E402
                                   load_grid, resolve_data_dir)

RESULTS_JSON = os.path.join(BASE_DIR, "results", "preliminar_tabla1.json")

S_BASE_KW = 10.0 * 1000.0                      # S_base = 10 MVA, en kW
I_BASE_A = 10.0 / (np.sqrt(3.0) * 12.66) * 1000.0   # I_base = 456.04 A
P_S_REF_PU = -0.46                             # exportación <= 4.6 MW  [4, Sec. 4.1]
P_PV_MAX_MW = 20.0                             # [4] no fija tope por proyecto; 20 MW no es activo
CANDIDATOS_ESC2 = [2, 3]                       # Escenario 2 de [4]

# Valores reportados por [4], Sec. 4.1 y Tabla 1 (pp. 15-16): "Proposed method".
TABLA1_REF = {
    1: {"HC_kW": 9262.0, "sitios_kW": {9: 12.0, 18: 2959.0, 22: 6291.0},
        "export_kW": 4600.0, "Vmax_pu": 1.0934, "Vmin_pu": 0.95709, "Imax_A": 259.0},
    2: {"HC_kW": 8546.0},
}
LIMITES = {"export_kW": 4600.0, "Vmax_pu": 1.10, "Imax_A": 300.0}


def _datos():
    nodes, branches = load_grid(resolve_data_dir())
    plana = pd.DataFrame({c: [1.0] for c in ("lambda_regulados", "lambda_pequenas",
                                             "lambda_grandes")}, index=[1])
    return nodes, branches, plana


def construir(objetivo: str, exacto: bool, candidatos=None):
    """Construye el modelo de la Tabla 1. objetivo: '10' (max sum P^PV) o '1' (informe)."""
    nodes, branches, plana = _datos()
    cfg = HCConfig(T=1, p_pv_max_mw=P_PV_MAX_MW, n_pv_max=32, n_bess_max=0, bess_candidates=[],
                   pv_candidates=candidatos, p_s_ref_pu=P_S_REF_PU, output_flag=0,
                   time_limit=300, mip_gap=1e-4)
    net = build_network(nodes, branches, plana, cfg)
    m, X = build_model(net, pd.Series([1.0], index=[1]), cfg)     # alpha = 1 (carga base)
    if exacto:
        # ec. (15) de [4]: igualdad P^2 + Q^2 = v*l (no convexa) en vez del cono relajado
        for q in [q for q in m.getQConstrs() if q.QCName.startswith("SOC[")]:
            m.remove(q)
        for j in net.nplus:
            m.addQConstr(X["Pf"][j, 1] * X["Pf"][j, 1] + X["Qf"][j, 1] * X["Qf"][j, 1]
                         == X["v"][net.parent[j], 1] * X["l"][j, 1], name=f"BFM_exacto[{j}]")
        m.Params.NonConvex = 2
    if objetivo == "10":
        m.setObjective(gp.quicksum(X["Ppv"][j, 1] for j in X["G_pv"]), GRB.MAXIMIZE)
    return m, X, net


def _resumen(m, X, net) -> dict:
    pv = {int(j): X["Ppv"][j, 1].X * S_BASE_KW for j in X["G_pv"] if X["Ppv"][j, 1].X > 1e-6}
    perd = sum(net.r[j] * X["l"][j, 1].X for j in net.nplus) * S_BASE_KW
    # Pérdidas ficticias: r * (l - (P^2+Q^2)/v_pi), es decir, corriente que no existe físicamente
    fict = sum(net.r[j] * (X["l"][j, 1].X - (X["Pf"][j, 1].X ** 2 + X["Qf"][j, 1].X ** 2)
                           / X["v"][net.parent[j], 1].X) for j in net.nplus) * S_BASE_KW
    return {"status": int(m.Status), "tiempo_s": float(m.Runtime), "HC_kW": sum(pv.values()),
            "sitios_kW": pv, "perdidas_modelo_kW": perd, "perdidas_ficticias_kW": fict,
            "P_S_kW": X["PS"][1].X * S_BASE_KW,
            "Imax_modelo_A": max(np.sqrt(max(X["l"][j, 1].X, 0.0)) for j in net.nplus) * I_BASE_A}


def validar_ac(sitios_kW: dict) -> dict:
    """Flujo AC de pandapower con el PV ubicado según la solución (fp = 1)."""
    net = pn.case33bw()
    net.line = net.line.iloc[:32].copy()
    for j, p_kw in sitios_kW.items():
        pp.create_sgen(net, int(j) - 1, p_mw=p_kw / 1000.0, q_mvar=0.0)
    pp.runpp(net, numba=False, tolerance_mva=1e-9)
    return {"export_kW": -float(net.res_ext_grid.p_mw.iloc[0]) * 1000.0,
            "Vmax_pu": float(net.res_bus.vm_pu.max()), "Vmin_pu": float(net.res_bus.vm_pu.min()),
            "Imax_A": float(net.res_line.i_ka.max()) * 1000.0,
            "perdidas_kW": float(net.res_line.pl_mw.sum()) * 1000.0}


def resolver(objetivo: str, exacto: bool, candidatos=None) -> dict:
    m, X, net = construir(objetivo, exacto, candidatos)
    m.optimize()
    if m.SolCount == 0:
        raise RuntimeError(f"Sin solución (status {m.Status}).")
    r = _resumen(m, X, net)
    r["ac"] = validar_ac(r["sitios_kW"])
    return r


def rango_hc_objetivo1() -> dict:
    """Con el objetivo (1) (relajado): HC mínimo y máximo con el MISMO valor óptimo del objetivo."""
    m, X, net = construir("1", exacto=False)
    m.optimize()
    sol = _resumen(m, X, net)
    ob = m.ObjVal
    m.addConstr(m.getObjective() >= ob - 1e-7, name="obj1_optimo")
    hc_pv = gp.quicksum(X["Ppv"][j, 1] for j in X["G_pv"])
    out = {"HC_solucion_kW": sol["HC_kW"], "objetivo_pu": ob}
    for sentido, tag in ((GRB.MINIMIZE, "HC_min_kW"), (GRB.MAXIMIZE, "HC_max_kW")):
        m.setObjective(hc_pv, sentido)
        m.optimize()
        out[tag] = m.ObjVal * S_BASE_KW
    return out


def ejecutar() -> dict:
    res = {"PRELIMINAR": True, "referencia_4": TABLA1_REF, "limites": LIMITES}
    for esc, cand in ((1, None), (2, CANDIDATOS_ESC2)):
        res[f"escenario_{esc}"] = {"exacto": resolver("10", True, cand),
                                   "relajado": resolver("10", False, cand)}
    res["indeterminacion_obj1"] = rango_hc_objetivo1()
    return res


def main() -> int:
    print("=" * 78)
    print("*** PRELIMINAR *** Tabla 1 de [4] (IEEE 33-bus, carga base, sin BESS)")
    print("El equipo aún no decide adoptar el MIQCP exacto ni el objetivo (10).")
    print("=" * 78)
    res = ejecutar()
    for esc in (1, 2):
        ref = TABLA1_REF[esc]["HC_kW"]
        print(f"\nEscenario {esc}: HC reportado por [4] = {ref:.0f} kW")
        for k, nombre in (("exacto", "MIQCP exacto"), ("relajado", "MISOCP relajado")):
            r = res[f"escenario_{esc}"][k]
            ac = r["ac"]
            print(f"  {nombre:<16} HC = {r['HC_kW']:7.0f} kW ({100 * (r['HC_kW'] / ref - 1):+5.1f} %)  "
                  f"sitios = { {j: round(p) for j, p in r['sitios_kW'].items() if p >= 1} }")
            print(f"  {'':<16} pérdidas modelo = {r['perdidas_modelo_kW']:.0f} kW "
                  f"(ficticias {r['perdidas_ficticias_kW']:.0f} kW), t = {r['tiempo_s']:.1f} s")
            print(f"  {'':<16} AC pandapower: exportación = {ac['export_kW']:.0f} kW (límite 4600), "
                  f"Vmax = {ac['Vmax_pu']:.4f} (límite 1.10), Imax = {ac['Imax_A']:.0f} A (límite 300)")
    ind = res["indeterminacion_obj1"]
    print(f"\nObjetivo (1), relajado: mismo óptimo con HC entre {ind['HC_min_kW']:.0f} y "
          f"{ind['HC_max_kW']:.0f} kW (la solución entregada tiene {ind['HC_solucion_kW']:.0f} kW).")

    os.makedirs(os.path.dirname(RESULTS_JSON), exist_ok=True)
    with open(RESULTS_JSON, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=2, ensure_ascii=False, default=float)
    print(f"\nGuardado: {os.path.relpath(RESULTS_JSON, BASE_DIR)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
