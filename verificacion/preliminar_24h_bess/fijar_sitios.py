"""
verificacion/preliminar_24h_bess/fijar_sitios.py
================================================
*** PRELIMINAR ***  Prueba 4: PV solo en las barras 18 y 22 (las del óptimo sin BESS) y BESS solo en un
par de barras, con las binarias mu originales (modelo exacto, sin reformular). Cada solución es factible
para el modelo completo, así que da una cota inferior del HC con BESS.

Es el prototipo de la cota inferior de experimentos/pregunta1_bess_cotas.py, que la generaliza (sitios
de PV calculados, varios tamaños de BESS y flujo AC). Usar ese script para resultados oficiales.

Uso:
    .venv/bin/python verificacion/preliminar_24h_bess/fijar_sitios.py [32,33 21,22 ...] [--time-limit 600]
Salida: results/preliminar_24h_bess/fijar_sitios.jsonl
"""
import argparse
import time

import _comun  # noqa: F401  (agrega la raíz del proyecto a sys.path)
from _comun import BASE_KW, P_S_REF_PU, guardar, simultaneas, sitios_pv_kw
from modelo.misocp_hc_bess import HCConfig, run_hc_bess

PARES_DEFECTO = ["32,33", "18,22", "17,18", "21,22"]


def correr(bess, time_limit):
    cfg = HCConfig(**BASE_KW, mip_gap=1e-5, p_s_ref_pu=P_S_REF_PU, time_limit=time_limit,
                   pv_candidates=[18, 22], bess_candidates=bess)
    t0 = time.time()
    r = run_hc_bess(cfg, save=False)
    m, s, X = r["model"], r["summary"], r["vars"]
    out = {"bess_candidatas": bess, "status": m.Status, "t_s": round(time.time() - t0, 1),
           "binarias": m.NumBinVars}
    if m.SolCount:
        out.update(HC_kW=round(s["hosting_capacity_PV_MW"] * 1000, 2), mip_gap=s["mip_gap"],
                   brecha_rel=s["conic_gap_rel"],
                   sitios=sitios_pv_kw(r),
                   bess={int(b): round(p * 1000, 1) for b, p in zip(r["bess_sites"]["bus"], r["bess_sites"]["P_cap_MW"])}
                   if len(r["bess_sites"]) else {},
                   horas_simultaneas=len(simultaneas(X, cfg)),
                   PS_min_kW=round(r["substation"]["P_S_MW"].min() * 1000, 1),
                   Vmax=round(float(r["voltages"].max().max()), 4))
    guardar("fijar_sitios", out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pares", nargs="*", default=PARES_DEFECTO, help="pares de barras para la BESS, p.ej. 32,33")
    ap.add_argument("--time-limit", type=float, default=600)
    a = ap.parse_args()
    for par in a.pares:
        correr([int(b) for b in par.split(",")], a.time_limit)
