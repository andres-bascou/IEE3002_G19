"""
verificacion/preliminar_24h_bess/sin_mu.py
==========================================
*** PRELIMINAR ***  Prueba 2: modelo de 24 h con BESS (2 x 50 kW / 100 kWh, exportación <= 4.6 MW)
con las binarias mu_ch / mu_dis relajadas a [0, 1] (64 binarias en vez de 1600).

Es una relajación del modelo original, así que su cota (ObjBound) es una cota superior válida del HC.
Si la solución no cargara y descargara a la vez, también sería óptima para el original. No es así: la
BESS carga y descarga a la vez a mediodía y disipa energía (carga ficticia). De aquí salió la cota
superior de experimentos/pregunta1_bess_cotas.py.

Uso:
    .venv/bin/python verificacion/preliminar_24h_bess/sin_mu.py [--time-limit 1200]
Salida: results/preliminar_24h_bess/sin_mu.jsonl
"""
import argparse
import time

from gurobipy import GRB

import _comun  # noqa: F401  (agrega la raíz del proyecto a sys.path)
from _comun import BASE_KW, P_S_REF_PU, guardar, simultaneas, sitios_pv_kw
from modelo.misocp_hc_bess import HCConfig, build_model, extract_results, load_inputs


def correr(time_limit):
    cfg = HCConfig(**BASE_KW, mip_gap=1e-4, p_s_ref_pu=P_S_REF_PU, time_limit=time_limit)
    net, alpha = load_inputs(cfg)
    m, X = build_model(net, alpha, cfg)
    for d in (X["mu_ch"], X["mu_dis"]):
        for var in d.values():
            var.VType = GRB.CONTINUOUS
    m.update()
    print(f"binarias: {m.NumBinVars} (antes 1600), cuadráticas: {m.NumQConstrs}", flush=True)

    t0 = time.time()
    m.optimize()
    out = {"status": m.Status, "t_s": round(time.time() - t0, 1), "nodos": int(m.NodeCount)}
    if m.SolCount:
        r = extract_results(m, X, net, cfg)
        s = r["summary"]
        S = cfg.s_base_mva * 1000.0                          # p.u. -> kW
        hc = s["hosting_capacity_PV_MW"] * 1000
        simult = simultaneas(X, cfg)
        # Energía disipada por la batería: lo que entra menos lo que sale menos el cambio de energía
        disip = 0.0
        for j in X["G_b"]:
            if X["z"][j].X >= 0.5:
                ent = sum(X["Pch"][j, t].X for t in X["T"]) * S
                sal = sum(X["Pdis"][j, t].X for t in X["T"]) * S
                dsoc = (X["SoC"][j, cfg.T].X - X["SoC"][j, 0].X) * S
                disip += ent - sal - dsoc
        out.update(HC_kW=round(hc, 1), cota_HC_kW=round(m.ObjBound / m.ObjVal * hc, 1),
                   mip_gap=s["mip_gap"], brecha_rel=s["conic_gap_rel"],
                   sitios=sitios_pv_kw(r),
                   bess=[int(b) for b in r["bess_sites"]["bus"]] if len(r["bess_sites"]) else [],
                   horas_simultaneas=len(simult), simultaneas=simult,
                   energia_disipada_kWh=round(disip, 2))
    guardar("sin_mu", out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--time-limit", type=float, default=1200)
    correr(ap.parse_args().time_limit)
