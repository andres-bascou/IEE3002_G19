"""
verificacion/preliminar_24h_bess/una_binaria.py
===============================================
*** PRELIMINAR ***  Prueba 3: reformulación de la exclusión carga/descarga de la BESS
(2 x 50 kW / 100 kWh, exportación <= 4.6 MW).

  * Una binaria delta[j,t] por batería y hora: P_ch <= delta * P_max, P_dis <= (1 - delta) * P_max
    (equivale a mu_ch + mu_dis <= z, porque P_ch, P_dis <= P_cap <= z * P_max).
  * Solo en las horas con sol (alpha_t > 0); de noche no hay PV que disipar.

El modelo resultante (416 binarias en vez de 1600) relaja al original solo en las horas de noche. Si la
solución no cargara y descargara a la vez en ninguna hora, también sería óptima para el original.
Resultado: no cerró el gap (6.5 % a los 20 min) y la solución carga y descarga a la vez de noche.

Uso:
    .venv/bin/python verificacion/preliminar_24h_bess/una_binaria.py [--time-limit 1200]
Salida: results/preliminar_24h_bess/una_binaria.jsonl
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
    m.update()

    # Quitar las restricciones con mu_ch / mu_dis y las propias mu
    for c in m.getConstrs():
        if c.ConstrName.startswith(("Pch_mu[", "Pdis_mu[", "Excl[")):
            m.remove(c)
    for d in (X["mu_ch"], X["mu_dis"]):
        for var in d.values():
            m.remove(var)

    P_max = cfg.p_b_max_mw / cfg.s_base_mva
    sol = [t for t in X["T"] if alpha[t] > 0]
    delta = m.addVars(X["G_b"], sol, vtype=GRB.BINARY, name="delta")
    for j in X["G_b"]:
        for t in sol:
            m.addConstr(X["Pch"][j, t] <= delta[j, t] * P_max, name=f"Pch_d[{j},{t}]")
            m.addConstr(X["Pdis"][j, t] <= (1 - delta[j, t]) * P_max, name=f"Pdis_d[{j},{t}]")
    m.update()
    print(f"horas con sol: {len(sol)} ({sol[0]}..{sol[-1]}), binarias: {m.NumBinVars} (antes 1600)", flush=True)

    t0 = time.time()
    m.optimize()
    out = {"status": m.Status, "t_s": round(time.time() - t0, 1), "nodos": int(m.NodeCount)}
    if m.SolCount:
        r = extract_results(m, X, net, cfg)
        s = r["summary"]
        S = cfg.s_base_mva * 1000.0                          # p.u. -> kW
        hc = s["hosting_capacity_PV_MW"] * 1000
        simult = simultaneas(X, cfg)
        despacho = {int(j): [[round(X["Pch"][j, t].X * S, 1), round(X["Pdis"][j, t].X * S, 1),
                              round(X["SoC"][j, t].X * S, 1)] for t in X["T"]]
                    for j in X["G_b"] if X["z"][j].X >= 0.5}
        out.update(HC_kW=round(hc, 2), cota_HC_kW=round(m.ObjBound / m.ObjVal * hc, 2),
                   mip_gap=s["mip_gap"], brecha_rel=s["conic_gap_rel"],
                   sitios=sitios_pv_kw(r),
                   bess={int(b): [round(p * 1000, 1), round(e * 1000, 1)] for b, p, e in
                         zip(r["bess_sites"]["bus"], r["bess_sites"]["P_cap_MW"], r["bess_sites"]["E_cap_MWh"])}
                   if len(r["bess_sites"]) else {},
                   horas_simultaneas=len(simult), simultaneas=simult,
                   despacho_ch_dis_soc_kW=despacho)
    guardar("una_binaria", out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--time-limit", type=float, default=1200)
    correr(ap.parse_args().time_limit)
