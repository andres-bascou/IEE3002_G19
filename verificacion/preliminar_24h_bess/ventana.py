"""
verificacion/preliminar_24h_bess/ventana.py
===========================================
*** PRELIMINAR ***  Prueba 5: cota superior por ventana de horas, con energía de la BESS.

Solo se modelan las horas de la ventana W (p.ej. 13-15), con la dinámica del estado de carga, pero con
el SoC inicial libre en [kappa_min, kappa_max] * E y sin SoC final. Cualquier solución de 24 h,
restringida a W, es factible para este problema, así que HC* <= HC_W. A diferencia de la cota horaria
de experimentos/pregunta1_bess_cotas.py, sí considera el límite de energía de la BESS.

Resultado: con las binarias mu el solver no cierra el gap en 5-20 min y la cota queda peor que la
horaria (ver README.md de esta carpeta). Se descartó.

Uso:
    .venv/bin/python verificacion/preliminar_24h_bess/ventana.py <P_MW por BESS> <t1-t2> [<t1-t2> ...] [--time-limit 300]
Salida: results/preliminar_24h_bess/ventana.jsonl
"""
import argparse
import dataclasses

import pandas as pd

import _comun  # noqa: F401  (agrega la raíz del proyecto a sys.path)
from _comun import BASE_KW, P_S_REF_PU, guardar
from modelo.misocp_hc_bess import HCConfig, build_model, load_inputs


def correr(p_mw, ventana, time_limit):
    cfg = HCConfig(**BASE_KW, mip_gap=1e-5, p_s_ref_pu=P_S_REF_PU, time_limit=time_limit,
                   p_b_max_mw=p_mw, e_b_max_mwh=2 * p_mw)
    net, alpha = load_inputs(cfg)
    a, b = map(int, ventana.split("-"))
    W = list(range(a, b + 1))
    net1 = dataclasses.replace(net, PL={(j, k + 1): net.PL[j, t] for j in net.nodes for k, t in enumerate(W)},
                               QL={(j, k + 1): net.QL[j, t] for j in net.nodes for k, t in enumerate(W)})
    a1 = pd.Series([alpha[t] for t in W], index=range(1, len(W) + 1), name="alpha")
    cfg1 = dataclasses.replace(cfg, T=len(W))
    m, X = build_model(net1, a1, cfg1)
    m.update()
    for c in m.getConstrs():                                  # SoC inicial libre, sin SoC final
        if c.ConstrName.startswith(("SoC0[", "SoCT[")):
            m.remove(c)
    m.optimize()
    S = cfg.s_base_mva * 1000.0
    den = float(a1.sum()) * cfg.dt
    out = {"P_MW": p_mw, "ventana": ventana, "status": m.Status, "t_s": round(m.Runtime, 1),
           "cota_HC_kW": round(m.ObjBound / den * S, 1)}
    if m.SolCount:
        out["HC_solucion_kW"] = round(m.ObjVal / den * S, 1)
    guardar("ventana", out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("p_mw", type=float)
    ap.add_argument("ventanas", nargs="+")
    ap.add_argument("--time-limit", type=float, default=300)
    a = ap.parse_args()
    for w in a.ventanas:
        correr(a.p_mw, w, a.time_limit)
