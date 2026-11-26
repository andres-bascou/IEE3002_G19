"""
verificacion/etapa2_tabla1.py
=============================
ETAPA 2: replicar la Tabla 1 de [4] (IEEE 33-bus, solo PV) con el modelo de producción.

Referencia [4]: J. Blanco-Solano, D. J. Chacón Molina, D. L. Chaustre Cárdenas,
"Enhanced optimization-based PV hosting capacity method for improved planning of real
distribution networks," Electricity, vol. 7, no. 1, art. 12, 2026 (Sec. 4.1 y Tabla 1).
PDF local (no versionado): docs/papers/04_blanco-solano_2026.pdf

Decisiones del equipo aplicadas (valores por defecto de modelo/misocp_hc_bess.py):
    modelo exacto (P^2 + Q^2 = v*l, Gurobi NonConvex = 2), objetivo max sum P^PV (ec. (10)
    de [4]), sin vertimiento, tensiones 0.9-1.1 p.u.

Configuración de la Tabla 1 (modelo.misocp_hc_bess.config_tabla1): carga base (T = 1,
lambda = alpha = 1), PV con fp = 1, I_max = 300 A, exportación <= 4.6 MW, sin BESS.
    Escenario 1: todas las barras candidatas.   Escenario 2: solo las barras 2 y 3.

Cada solución se valida con un flujo de potencia AC de pandapower (PV como sgen, fp = 1):
debe respetar los límites reales y reproducir las tensiones del modelo.

Uso (desde cualquier carpeta):
    python verificacion/etapa2_tabla1.py               # ambos escenarios
    python verificacion/etapa2_tabla1.py --escenario 2 # solo uno
Escribe results/etapa2_tabla1.json (resumen) y results/etapa2_tabla1_esc<k>.json
(resultado completo del modelo, graficable con modelo/grafico_resultados.py).
Termina con código 0 si todos los escenarios ejecutados dan PASS.
"""
import argparse
import json
import os
import sys

import numpy as np
import pandapower as pp
import pandapower.networks as pn

# OJO: NO usar rutas absolutas (p.ej. r"C:\Users\..." o "/Users/..."): solo funcionan en un PC.
# Se resuelve la raíz del proyecto relativa a este archivo (<raíz>/<carpeta>/este_script.py).
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # raíz del proyecto
sys.path.insert(0, BASE_DIR)

from modelo.misocp_hc_bess import config_tabla1, run_hc_bess  # noqa: E402

RESULTS_JSON = os.path.join(BASE_DIR, "results", "etapa2_tabla1.json")

# Valores reportados por [4], Sec. 4.1 y Tabla 1 (pp. 15-16): "Proposed method".
TABLA1_REF = {
    1: {"HC_kW": 9262.0, "sitios_kW": {9: 12.0, 18: 2959.0, 22: 6291.0}},
    2: {"HC_kW": 8546.0, "sitios_kW": None},
}
LIMITES = {"export_kW": 4600.0, "Vmin_pu": 0.90, "Vmax_pu": 1.10, "Imax_A": 300.0}

# Criterios de PASS
TOL_HC_REL = 5e-3        # |HC - HC_[4]| / HC_[4] <= 0.5 %
TOL_GAP_REL = 1e-4       # brecha cónica relativa (modelo exacto)
TOL_MIP_GAP = 1e-4       # optimalidad global del MIQCP
TOL_V_AC = 1e-4          # |V_modelo - V_AC| máximo [p.u.]
TOL_EXPORT_KW = 1.0      # holgura numérica sobre los límites en el flujo AC
TOL_V_LIM = 1e-4         # [p.u.]
TOL_I_LIM_A = 0.5        # [A]


def flujo_ac(sitios_kW: dict) -> dict:
    """Flujo AC de pandapower con el PV ubicado según la solución (fp = 1)."""
    net = pn.case33bw()
    net.line = net.line.iloc[:32].copy()             # red radial, sin tie-lines
    for j, p_kw in sitios_kW.items():
        pp.create_sgen(net, int(j) - 1, p_mw=p_kw / 1000.0, q_mvar=0.0)
    pp.runpp(net, numba=False, tolerance_mva=1e-9)
    V = {int(b) + 1: float(v) for b, v in net.res_bus.vm_pu.items()}   # barras 1-based
    return {"export_kW": -float(net.res_ext_grid.p_mw.iloc[0]) * 1000.0,
            "Vmax_pu": max(V.values()), "Vmin_pu": min(V.values()),
            "Imax_A": float(net.res_line.i_ka.max()) * 1000.0,
            "perdidas_kW": float(net.res_line.pl_mw.sum()) * 1000.0, "V": V}


def resolver_escenario(esc: int) -> dict:
    res = run_hc_bess(config_tabla1(esc), filename=f"etapa2_tabla1_esc{esc}")
    s = res["summary"]
    if not s.get("solution"):
        raise RuntimeError(f"Escenario {esc} sin solución (status {s['status']}).")
    sitios = {int(b): p * 1000.0 for b, p in zip(res["pv_sites"]["bus"], res["pv_sites"]["P_cap_MW"])
              if p * 1000.0 >= 1e-3}
    V_mod = res["voltages"].loc[1]
    ac = flujo_ac(sitios)
    dV = max(abs(float(V_mod[j]) - ac["V"][j]) for j in ac["V"])
    return {
        "status": int(s["status"]), "mip_gap": float(s["mip_gap"]), "tiempo_s": float(s["runtime_s"]),
        "HC_kW": s["hosting_capacity_PV_MW"] * 1000.0, "sitios_kW": sitios,
        "P_S_kW": float(res["substation"]["P_S_MW"].iloc[0]) * 1000.0,
        "perdidas_modelo_kW": s["losses_MWh"] * 1000.0,
        "brecha_rel": float(s["conic_gap_rel"]), "brecha_abs_pu2": float(s["conic_gap_pu2"]),
        "Vmax_modelo_pu": float(V_mod.max()), "Imax_modelo_A": float(res["branch_flows"]["I_A"].max()),
        "max_dV_modelo_vs_ac": dV,
        "ac": {k: v for k, v in ac.items() if k != "V"},
        "archivo": os.path.relpath(str(res["results_path"]), BASE_DIR),
    }


def evaluar(esc: int, r: dict) -> bool:
    ref = TABLA1_REF[esc]["HC_kW"]
    ac = r["ac"]
    criterios = [
        ("error HC vs [4] [-]", abs(r["HC_kW"] / ref - 1.0), TOL_HC_REL),
        ("MIP gap (optimalidad global) [-]", r["mip_gap"], TOL_MIP_GAP),
        ("brecha cónica relativa [-]", r["brecha_rel"], TOL_GAP_REL),
        ("max |V_modelo - V_AC| [p.u.]", r["max_dV_modelo_vs_ac"], TOL_V_AC),
        ("AC: exportación - 4600 [kW]", ac["export_kW"] - LIMITES["export_kW"], TOL_EXPORT_KW),
        ("AC: Vmax - 1.10 [p.u.]", ac["Vmax_pu"] - LIMITES["Vmax_pu"], TOL_V_LIM),
        ("AC: 0.90 - Vmin [p.u.]", LIMITES["Vmin_pu"] - ac["Vmin_pu"], TOL_V_LIM),
        ("AC: Imax - 300 [A]", ac["Imax_A"] - LIMITES["Imax_A"], TOL_I_LIM_A),
    ]
    print(f"\n--- Escenario {esc}: HC = {r['HC_kW']:.1f} kW  vs  [4] = {ref:.0f} kW "
          f"({100 * (r['HC_kW'] / ref - 1):+.2f} %) ---")
    print(f"  sitios [kW]: { {j: round(p, 1) for j, p in r['sitios_kW'].items()} }")
    if TABLA1_REF[esc]["sitios_kW"]:
        print(f"  sitios [4]:  {TABLA1_REF[esc]['sitios_kW']}")
    ok_total = r["status"] == 2
    print(f"  status Gurobi {r['status']} ({'óptimo' if ok_total else 'NO óptimo'}), t = {r['tiempo_s']:.2f} s")
    for txt, val, tol in criterios:
        ok = bool(val <= tol)
        ok_total &= ok
        print(f"  {txt:<36} {val:12.3e}   tol {tol:9.1e}   {'PASS' if ok else 'FAIL'}")
    print(f"  (info) AC: exportación = {ac['export_kW']:.1f} kW, Vmax = {ac['Vmax_pu']:.4f}, "
          f"Vmin = {ac['Vmin_pu']:.4f}, Imax = {ac['Imax_A']:.1f} A, pérdidas = {ac['perdidas_kW']:.1f} kW "
          f"(modelo {r['perdidas_modelo_kW']:.1f} kW)")
    print(f"  (info) resultado completo: {r['archivo']}")
    print(f"  RESULTADO: {'PASS' if ok_total else 'FAIL'}")
    return ok_total


def main() -> int:
    ap = argparse.ArgumentParser(description="Etapa 2: Tabla 1 de [4] con el modelo exacto.")
    ap.add_argument("--escenario", type=int, choices=(1, 2), action="append",
                    help="escenario a resolver (se puede repetir); por defecto, ambos")
    escenarios = ap.parse_args().escenario or [1, 2]

    print("=" * 78)
    print("ETAPA 2: Tabla 1 de [4] (IEEE 33-bus, carga base, solo PV) con el MIQCP exacto")
    print("=" * 78)
    salida = {"referencia_4": TABLA1_REF, "limites": LIMITES}
    oks = {}
    for esc in escenarios:
        r = resolver_escenario(esc)
        oks[esc] = evaluar(esc, r)
        r["PASS"] = oks[esc]
        salida[f"escenario_{esc}"] = r

    # Conserva escenarios de corridas anteriores que no se volvieron a resolver
    if os.path.exists(RESULTS_JSON) and len(escenarios) < 2:
        with open(RESULTS_JSON, encoding="utf-8") as f:
            previo = json.load(f)
        for k, v in previo.items():
            salida.setdefault(k, v)
    os.makedirs(os.path.dirname(RESULTS_JSON), exist_ok=True)
    with open(RESULTS_JSON, "w", encoding="utf-8") as f:
        json.dump(salida, f, indent=2, ensure_ascii=False, default=float)

    ok = all(oks.values())
    print("\n" + "=" * 78)
    print(f"ETAPA 2: {'PASS' if ok else 'FAIL'}  ("
          + ", ".join(f"escenario {e}: {'PASS' if v else 'FAIL'}" for e, v in oks.items()) + ")")
    print(f"Guardado: {os.path.relpath(RESULTS_JSON, BASE_DIR)}")
    print("=" * 78)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
