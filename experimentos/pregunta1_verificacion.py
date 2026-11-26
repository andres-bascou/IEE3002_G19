"""
experimentos/pregunta1_verificacion.py
======================================
Verificación del supuesto de la pregunta 1: ¿mover el PV mejora el HC con BESS?

experimentos/pregunta1_bess.py fija el PV en los sitios del óptimo sin BESS y enumera los sitios de
BESS. Aquí se toma la mejor combinación de BESS de cada configuración y se resuelve con el PV libre
en las 32 barras, partiendo de la solución COMPLETA de la enumeración (todas las variables, leída de
results/pregunta1/*.json). Así el incumbente nunca es peor que el HC enumerado, y la cota de Gurobi
dice cuánto podría mejorar como máximo moviendo el PV.

Uso (desde cualquier carpeta, después de experimentos/pregunta1_bess.py):
    python experimentos/pregunta1_verificacion.py [--time-limit 900]
Escribe results/pregunta1_verificacion.json.
"""
import argparse
import json
import os
import sys

# OJO: NO usar rutas absolutas (p.ej. r"C:\Users\..." o "/Users/..."): solo funcionan en un PC.
# Se resuelve la raíz del proyecto relativa a este archivo (<raíz>/<carpeta>/este_script.py).
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # raíz del proyecto
sys.path.insert(0, BASE_DIR)

from experimentos.comun_24h import EXPORTACION, HORAS_SOL, config_24h, flujo_ac_24h, resumen  # noqa: E402
from modelo.misocp_hc_bess import build_model, extract_results, load_inputs  # noqa: E402

P1_JSON = os.path.join(BASE_DIR, "results", "pregunta1_bess.json")
RESULTS_JSON = os.path.join(BASE_DIR, "results", "pregunta1_verificacion.json")
THREADS = int(os.environ.get("HC_THREADS", "0")) or None
OPC_BESS = dict(exact_cone_horas=None, bess_mu_binaries=False, bess_horas_carga=list(HORAS_SOL))


def _arranque(X, sol, cfg, alpha):
    """Fija .Start en todas las variables a partir del JSON completo de una corrida."""
    S = cfg.s_base_mva
    res = sol["results"]
    V = res["voltages_pu"]
    for (j, t), var in X["v"].items():
        var.Start = float(V[str(j)][V["t"].index(t)]) ** 2
    for b in res["branch_flows"]:
        j, t = int(b["to"]), int(b["t"])
        X["Pf"][j, t].Start = b["P_MW"] / S
        X["Qf"][j, t].Start = b["Q_MVAr"] / S
        X["l"][j, t].Start = b["I_pu"] ** 2
    for s_ in res["substation"]:
        X["PS"][int(s_["t"])].Start = s_["P_S_MW"] / S
        X["QS"][int(s_["t"])].Start = s_["Q_S_MVAr"] / S
    cap = {int(p["bus"]): p["P_cap_MW"] / S for p in res["pv_sites"]}
    for j in X["G_pv"]:
        X["w"][j].Start = 1.0 if j in cap else 0.0
        X["Ppv_cap"][j].Start = cap.get(j, 0.0)
        for t in X["T"]:
            X["Ppv"][j, t].Start = float(alpha[t]) * cap.get(j, 0.0)
    bs = {int(b["bus"]): b for b in res["bess_sites"]}
    for j in X["G_b"]:
        b = bs.get(j)
        X["z"][j].Start = 1.0 if b else 0.0
        X["Pb_cap"][j].Start = b["P_cap_MW"] / S if b else 0.0
        X["Eb_cap"][j].Start = b["E_cap_MWh"] / S if b else 0.0
        X["SoC"][j, 0].Start = cfg.kappa_0 * (b["E_cap_MWh"] / S if b else 0.0)
    for o in res["bess_ops"]:
        j, t = int(o["bus"]), int(o["t"])
        if j in X["G_b"]:
            X["Pch"][j, t].Start = o["P_ch_MW"] / S
            X["Pdis"][j, t].Start = o["P_dis_MW"] / S
            X["SoC"][j, t].Start = o["SoC_MWh"] / S


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--time-limit", type=float, default=900.0)
    args = ap.parse_args()
    with open(P1_JSON, encoding="utf-8") as f:
        p1 = json.load(f)
    out = {}
    if os.path.exists(RESULTS_JSON):
        with open(RESULTS_JSON, encoding="utf-8") as f:
            out = json.load(f)
    for k, run in p1["corridas"].items():
        if "archivo" not in run or k in out:
            continue
        combo = [int(j) for j in run["mejor_combinacion"].split("-")]
        cfg = config_24h(run["B_MWh"], p_s_ref=EXPORTACION[run["exportacion"]], tau_h=run["tau_h"],
                         time_limit=args.time_limit, threads=THREADS, pv_candidates=None,
                         bess_candidates=combo, n_bess_max=len(combo), **OPC_BESS)
        net, alpha = load_inputs(cfg)
        m, X = build_model(net, alpha, cfg)
        with open(os.path.join(BASE_DIR, run["archivo"]), encoding="utf-8") as f:
            _arranque(X, json.load(f), cfg, alpha)
        m.optimize()
        r = extract_results(m, X, net, cfg)
        r.update(model=m, network=net, config=cfg, vars=X, alpha=alpha)
        ac = flujo_ac_24h(r)
        s = resumen(r, ac)
        cota = m.ObjBound * cfg.s_base_mva * 1000.0 / float(alpha.sum())
        c = {"HC_enumerado_kW": run["mejor"]["HC_kW"], "HC_pv_libre_kW": s["HC_kW"], "cota_pv_libre_kW": cota,
             "mejora_max_pct": 100.0 * (cota / run["mejor"]["HC_kW"] - 1.0),
             "mejora_encontrada_pct": 100.0 * (s["HC_kW"] / run["mejor"]["HC_kW"] - 1.0),
             "sitios_pv_kW": s["sitios_pv_kW"], "bess": s["bess"], "mip_gap": s["mip_gap"], "status": s["status"],
             "tiempo_s": s["tiempo_s"], "viola_limites_AC": ac["viola_limites_AC"]}
        out[k] = c
        with open(RESULTS_JSON, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2, ensure_ascii=False, default=float)
        print(f"[{k}] enumerado {c['HC_enumerado_kW']:.1f} kW | PV libre {c['HC_pv_libre_kW']:.1f} kW "
              f"({c['mejora_encontrada_pct']:+.2f} %) | cota {cota:.0f} kW (mejora máx {c['mejora_max_pct']:+.2f} %) | "
              f"PV { {int(j): round(p) for j, p in c['sitios_pv_kW'].items()} } | {c['tiempo_s']:.0f} s"
              + ("  ** VIOLA LÍMITES EN AC **" if c["viola_limites_AC"] else ""), flush=True)
    print(f"\nGuardado: {os.path.relpath(RESULTS_JSON, BASE_DIR)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
