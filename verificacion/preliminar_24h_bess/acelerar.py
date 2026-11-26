"""
verificacion/preliminar_24h_bess/acelerar.py
============================================
*** PRELIMINAR ***  Prueba 1: variantes para acelerar el MIQCP exacto de 24 h (2 x 50 kW de BESS,
exportación <= 4.6 MW). Ninguna cerró el gap con BESS en 10 min; ver README.md de esta carpeta.

Variantes (el nombre combina etiquetas):
    B_cotas         sin BESS + cotas explícitas en los flujos (|P|, |Q| <= v_max * i_max) y en P_S, Q_S
    C_start         con BESS, arranque en la solución óptima sin BESS (PV en 18 y 22)
    C_start_focus   C_start + MIPFocus = 3 (priorizar la cota)
    C_cand          con BESS, candidatas a BESS solo en 18 y 22
    C_cand_start    C_cand + arranque en la solución sin BESS
    (también acepta otras combinaciones de "B_"/"C_" con "cotas", "start", "focus" y "cand")

Uso:
    .venv/bin/python verificacion/preliminar_24h_bess/acelerar.py <variante> [--time-limit 600]
Salida: results/preliminar_24h_bess/acelerar.jsonl
"""
import argparse
import time

import numpy as np

import _comun  # noqa: F401  (agrega la raíz del proyecto a sys.path)
from _comun import BASE_KW, P_S_REF_PU, guardar, sitios_pv_kw
from modelo.misocp_hc_bess import HCConfig, build_model, extract_results, load_inputs

# Solución óptima del caso sin BESS (medir_24h.py, caso B exacto), en p.u. de S_base = 10 MVA
SOL_SIN_BESS = {18: 0.40659, 22: 0.85767}


def correr(var, time_limit):
    kw = dict(BASE_KW, mip_gap=1e-4, p_s_ref_pu=P_S_REF_PU, time_limit=time_limit)
    if var.startswith("B_"):
        kw.update(n_bess_max=0, bess_candidates=[])
    if "cand" in var:
        kw["bess_candidates"] = [18, 22]
    cfg = HCConfig(**kw)
    net, alpha = load_inputs(cfg)
    m, X = build_model(net, alpha, cfg)

    if "cotas" in var:
        # Cotas implícitas: P^2 + Q^2 = v*l <= v_max^2 * i_max^2  =>  |P|, |Q| <= v_max * i_max
        for (j, t), p in X["Pf"].items():
            b = np.sqrt(net.v_max[net.parent[j]] ** 2 * net.i_max[j] ** 2)
            p.LB, p.UB = -b, b
            X["Qf"][j, t].LB, X["Qf"][j, t].UB = -b, b
        for t in X["T"]:
            for d in (X["PS"], X["QS"]):
                d[t].LB, d[t].UB = -cfg.s_sub_max_pu, cfg.s_sub_max_pu
        for j in X["G_pv"]:
            X["Ppv_cap"][j].UB = cfg.p_pv_max_mw / cfg.s_base_mva
    if "start" in var:
        for j in X["G_pv"]:
            X["w"][j].Start = 1.0 if j in SOL_SIN_BESS else 0.0
            X["Ppv_cap"][j].Start = SOL_SIN_BESS.get(j, 0.0) * 0.999
        for j in X["G_b"]:
            X["z"][j].Start = 0.0
    if "focus" in var:
        m.Params.MIPFocus = 3

    t0 = time.time()
    m.optimize()
    out = {"variante": var, "status": m.Status, "t_s": round(time.time() - t0, 1), "nodos": int(m.NodeCount)}
    if m.SolCount:
        r = extract_results(m, X, net, cfg)
        s = r["summary"]
        hc = s["hosting_capacity_PV_MW"] * 1000
        out.update(HC_kW=round(hc, 1), cota_HC_kW=round(m.ObjBound / m.ObjVal * hc, 1),
                   mip_gap=round(s["mip_gap"], 5), brecha_rel=s["conic_gap_rel"],
                   sitios=sitios_pv_kw(r),
                   bess=list(map(int, r["bess_sites"]["bus"])) if len(r["bess_sites"]) else [])
    guardar("acelerar", out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("variante")
    ap.add_argument("--time-limit", type=float, default=600)
    a = ap.parse_args()
    correr(a.variante, a.time_limit)
