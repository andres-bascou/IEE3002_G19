"""
verificacion/preliminar_24h_bess/medir_24h.py
=============================================
*** PRELIMINAR ***  Prueba 0: cuánto tarda el modelo de 24 h, exacto y relajado.

Casos (julio, PV hasta 20 MW en cualquier barra):
    A_sinBESS_sinExport  sin BESS, sin límite de exportación         (time limit 300 s)
    B_sinBESS_export46   sin BESS, exportación <= 4.6 MW              (time limit 300 s)
    C_conBESS_export46   2 x 50 kW / 100 kWh, exportación <= 4.6 MW   (time limit 600 s)

Uso:
    .venv/bin/python verificacion/preliminar_24h_bess/medir_24h.py [--casos A_...,B_...] [--modelos exacto,relajado]
Por defecto corre los 6 casos (~17 min). Salida: results/preliminar_24h_bess/medir_24h.jsonl
"""
import argparse
import time

import _comun  # noqa: F401  (agrega la raíz del proyecto a sys.path)
from _comun import BASE_KW, P_S_REF_PU, guardar, sitios_pv_kw
from modelo.misocp_hc_bess import HCConfig, run_hc_bess

CASOS = {
    "A_sinBESS_sinExport": dict(n_bess_max=0, bess_candidates=[], p_s_ref_pu=None, time_limit=300),
    "B_sinBESS_export46":  dict(n_bess_max=0, bess_candidates=[], p_s_ref_pu=P_S_REF_PU, time_limit=300),
    "C_conBESS_export46":  dict(n_bess_max=2, p_s_ref_pu=P_S_REF_PU, time_limit=600),
}


def correr(caso, modelo):
    cfg = HCConfig(**BASE_KW, mip_gap=1e-4, exact_cone=(modelo == "exacto"), **CASOS[caso])
    t0 = time.time()
    r = run_hc_bess(cfg, save=False)
    m, s = r["model"], r["summary"]
    out = {"caso": caso, "modelo": modelo, "status": m.Status, "t_s": round(time.time() - t0, 1),
           "vars": m.NumVars, "bin": m.NumBinVars, "qconstr": m.NumQConstrs}
    if m.SolCount:
        hc = s["hosting_capacity_PV_MW"] * 1000
        out.update(HC_kW=round(hc, 1),
                   cota_HC_kW=round(m.ObjBound / m.ObjVal * hc, 1) if m.ObjVal else None,
                   mip_gap=s["mip_gap"], brecha_rel=s["conic_gap_rel"],
                   perd_ficticias_MWh=round(s["fictitious_losses_MWh"], 3),
                   sitios=sitios_pv_kw(r),
                   bess={int(b): round(p * 1000, 1) for b, p in zip(r["bess_sites"]["bus"], r["bess_sites"]["P_cap_MW"])}
                   if len(r["bess_sites"]) else {},
                   PS_min_kW=round(r["substation"]["P_S_MW"].min() * 1000, 1),
                   Vmax=round(float(r["voltages"].max().max()), 4),
                   Imax_A=round(float(r["branch_flows"]["I_A"].max()), 1))
    guardar("medir_24h", out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--casos", default=",".join(CASOS))
    ap.add_argument("--modelos", default="relajado,exacto")
    a = ap.parse_args()
    for modelo in a.modelos.split(","):
        for caso in a.casos.split(","):
            correr(caso, modelo)
