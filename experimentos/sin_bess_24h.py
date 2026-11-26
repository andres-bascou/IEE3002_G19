"""
experimentos/sin_bess_24h.py
============================
HC del modelo de 24 h SIN BESS resolviendo solo las horas críticas.

Sin BESS nada acopla las horas: la capacidad P_cap es la misma, pero cada hora tiene sus propias
restricciones. Por eso el HC de 24 h es el de las horas que limitan, y el modelo con un
subconjunto H de horas es una relajación del de 24 h (tiene menos restricciones). Se parte de la
hora con más sol, se resuelve el modelo exacto con H, y se valida la solución con un flujo AC de
pandapower en las 24 horas. Si alguna hora viola un límite, se agrega a H y se vuelve a resolver.
Cuando el flujo AC no viola nada, la solución es factible en 24 h y, por ser óptima para la
relajación, es el HC óptimo de 24 h. Toma segundos en vez de minutos.

Lo usan los experimentos de las preguntas 2, 3 y 4 sin BESS.
"""
import os
import sys
from dataclasses import replace

import numpy as np
import pandas as pd
import pandapower as pp
import pandapower.networks as pn

# OJO: NO usar rutas absolutas (p.ej. r"C:\Users\..." o "/Users/..."): solo funcionan en un PC.
# Se resuelve la raíz del proyecto relativa a este archivo (<raíz>/<carpeta>/este_script.py).
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # raíz del proyecto
sys.path.insert(0, BASE_DIR)

from experimentos.comun_24h import LIMITES, TOL_ACTIVO, config_24h  # noqa: E402,F401
from modelo.misocp_hc_bess import (HCConfig, build_model, build_network,  # noqa: E402
                                   extract_results, load_demand_profiles, load_grid,
                                   load_pv_profile, resolve_data_dir)


def _datos(cfg24: HCConfig):
    data_dir = resolve_data_dir(cfg24.data_dir)
    nodes, branches = load_grid(data_dir)
    dem = load_demand_profiles(data_dir, cfg24.demand_basis, 24)
    alpha = load_pv_profile(data_dir, 24, cfg24.month, cfg24.alpha_file)
    return nodes, branches, dem, alpha


def ac_24h_pv(sitios_kW: dict, cfg24: HCConfig) -> dict:
    """Flujo AC en las 24 horas con PV (sin BESS). Devuelve el resumen por hora y los peores valores."""
    nodes, branches, dem, alpha = _datos(cfg24)
    net_m = build_network(nodes, branches, dem, replace(cfg24, T=24))
    S = cfg24.s_base_mva
    tan_phi = float(np.tan(np.arccos(cfg24.pv_pf))) if cfg24.pv_pf < 1.0 else 0.0
    con_lim = cfg24.p_s_ref_pu is not None
    lim_exp_kW = -cfg24.p_s_ref_pu * S * 1000.0 if con_lim else float("inf")   # límite de exportación de cfg24
    horas = []
    for t in range(1, 25):
        net = pn.case33bw()
        net.line = net.line.iloc[:32].copy()             # red radial, sin tie-lines
        for idx, b in net.load.bus.items():
            j = int(b) + 1
            net.load.at[idx, "p_mw"] = net_m.PL[j, t] * S
            net.load.at[idx, "q_mvar"] = net_m.QL[j, t] * S
        for j, p_kw in sitios_kW.items():
            p = float(alpha[t]) * p_kw / 1000.0
            if p > 0:
                pp.create_sgen(net, int(j) - 1, p_mw=p, q_mvar=-tan_phi * p)
        pp.runpp(net, numba=False, tolerance_mva=1e-9)
        h = {"t": t, "export_kW": -float(net.res_ext_grid.p_mw.iloc[0]) * 1000.0,
             "Vmax_pu": float(net.res_bus.vm_pu.max()), "Vmin_pu": float(net.res_bus.vm_pu.min()),
             "Imax_A": float(net.res_line.i_ka.max()) * 1000.0,
             "perdidas_kW": float(net.res_line.pl_mw.sum()) * 1000.0}
        h["viola"] = bool(h["Vmax_pu"] > LIMITES["Vmax_pu"] + 1e-4 or h["Vmin_pu"] < LIMITES["Vmin_pu"] - 1e-4
                          or h["Imax_A"] > LIMITES["Imax_A"] + 0.5
                          or (con_lim and h["export_kW"] > lim_exp_kW + 1.0))
        h["activos"] = [k for k, ok in (
            ("exportación", con_lim and h["export_kW"] >= lim_exp_kW - TOL_ACTIVO["export_kW"]),
            ("V_max", h["Vmax_pu"] >= LIMITES["Vmax_pu"] - TOL_ACTIVO["Vmax_pu"]),
            ("I_max", h["Imax_A"] >= LIMITES["Imax_A"] - TOL_ACTIVO["Imax_A"])) if ok]
        horas.append(h)
    return {"horas": horas,
            "peor": {"export_kW": max(h["export_kW"] for h in horas), "Vmax_pu": max(h["Vmax_pu"] for h in horas),
                     "Vmin_pu": min(h["Vmin_pu"] for h in horas), "Imax_A": max(h["Imax_A"] for h in horas)},
            "limites_activos": sorted({a for h in horas for a in h["activos"]}),
            "horas_activas": [h["t"] - 1 for h in horas if h["activos"]],
            "viola_limites_AC": any(h["viola"] for h in horas)}


def resolver_sin_bess(cfg24: HCConfig, uniforme: bool = False, max_iter: int = 6) -> dict:
    """HC óptimo de 24 h sin BESS (ver docstring del módulo). cfg24: configuración de 24 h
    (p.ej. config_24h(0.0, ...)); se usan sus límites, PV, fp y opciones de solver.
    uniforme=True: PV en todas las barras candidatas con la misma capacidad."""
    nodes, branches, dem, alpha = _datos(cfg24)
    H = [int(alpha.idxmax())]
    t_total = 0.0
    for it in range(max_iter + 1):
        k = len(H)
        cfg = replace(cfg24, T=k, n_bess_max=0, bess_candidates=[], exact_cone_horas=None,
                      bess_mu_binaries=False, bess_mu_horas=None, bess_horas_carga=None, e_b_budget_mwh=None)
        d = dem.loc[H].reset_index(drop=True)
        d.index = range(1, k + 1)
        a = pd.Series(alpha.loc[H].to_numpy(), index=range(1, k + 1), name="alpha")
        net = build_network(nodes, branches, d, cfg)
        m, X = build_model(net, a, cfg)
        if uniforme:
            G = X["G_pv"]
            for j in G:
                X["w"][j].LB = 1.0
            for j in G[1:]:
                m.addConstr(X["Ppv_cap"][j] == X["Ppv_cap"][G[0]], name=f"uniforme[{j}]")
        m.optimize()
        t_total += m.Runtime
        r = extract_results(m, X, net, cfg)
        s = r["summary"]
        if not s.get("solution"):
            return {"solucion": False, "status": int(s["status"]), "horas_modelo": [h - 1 for h in H]}
        sitios = {int(b): p * 1000.0 for b, p in zip(r["pv_sites"]["bus"], r["pv_sites"]["P_cap_MW"])
                  if p * 1000.0 >= 1.0}
        ac = ac_24h_pv(sitios, cfg24)
        nuevas = [h["t"] for h in ac["horas"] if h["viola"] and h["t"] not in H]
        if not nuevas or it == max_iter:
            break
        H += nuevas
    energia = float(alpha.sum()) * cfg24.dt          # [h] equivalentes: E_PV = HC * sum(alpha)
    return {"solucion": True, "HC_kW": s["hosting_capacity_PV_MW"] * 1000.0, "n_sitios": len(sitios),
            "sitios_kW": sitios, "status": int(s["status"]), "mip_gap": float(s["mip_gap"]),
            "cota_HC_kW": m.ObjBound * cfg.s_base_mva * 1000.0 / float(a.sum()) if m.IsMIP else None,
            "tiempo_s": t_total, "horas_modelo": [h - 1 for h in H], "brecha_rel": float(s["conic_gap_rel"]),
            "certificado_AC": not ac["viola_limites_AC"], "limites_activos": ac["limites_activos"],
            "horas_activas": ac["horas_activas"], "ac_peor": ac["peor"],
            "energia_PV_MWh": s["hosting_capacity_PV_MW"] * energia,
            "perdidas_24h_kWh": sum(h["perdidas_kW"] for h in ac["horas"])}


if __name__ == "__main__":
    # Prueba: julio sin BESS con límite de exportación (el modelo completo de 24 h da 12 642 kW).
    r = resolver_sin_bess(config_24h(0.0, p_s_ref=-0.46, threads=2))
    print({k: r[k] for k in ("HC_kW", "sitios_kW", "mip_gap", "tiempo_s", "horas_modelo", "certificado_AC",
                             "limites_activos", "horas_activas")})
