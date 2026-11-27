"""
experimentos/pregunta4_relajacion.py
====================================
Pregunta de investigación 4: ¿qué error comete la relajación cónica (MISOCP) frente al modelo
original (MIQCP exacto)?

Para cada caso se resuelven los dos modelos con el mismo objetivo (max sum P^PV, sin vertimiento):
    * exacto:   P^2 + Q^2 = v*l   (exact_cone=True, NonConvex=2)
    * relajado: P^2 + Q^2 <= v*l  (exact_cone=False), con tolerancias de barrera ajustadas
                (BarQCPConvTol = BarConvTol = 1e-10) para que la brecha medida no sea ruido numérico.
y la solución relajada se evalúa en un flujo AC de pandapower: se instala el PV que eligió el
relajado y se mide si la red real cumple los límites (exportación, tensión, corriente).

Casos:
    tabla1_esc{1,2}_{con,sin}: Tabla 1 de [4] (carga base, T = 1), con y sin el límite de 4.6 MW.
    24h_{con,sin}:             julio, 24 h, sin BESS, con y sin el límite de 4.6 MW.
    24h_bess005 (opcional, --bess): julio, 24 h, 2 BESS de 50 kW en 32 y 33. El exacto no se
                                    resuelve: se usa el óptimo demostrado de la pregunta 1.

Métricas: HC de cada modelo y su error relativo; pérdidas y pérdidas ficticias del relajado
(r * (l - (P^2+Q^2)/v), corriente que no existe físicamente); brecha cónica relativa máxima y
número de ramas con brecha > 1e-4; y, en el flujo AC de la solución relajada, exportación,
V_max, I_max y error de tensión frente al modelo.

Uso (desde cualquier carpeta):
    python experimentos/pregunta4_relajacion.py [--bess]
Escribe results/pregunta4_relajacion.json.
"""
import argparse
import json
import os
import sys
import time

# OJO: NO usar rutas absolutas (p.ej. r"C:\Users\..." o "/Users/..."): solo funcionan en un PC.
# Se resuelve la raíz del proyecto relativa a este archivo (<raíz>/<carpeta>/este_script.py).
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # raíz del proyecto
sys.path.insert(0, BASE_DIR)

from experimentos.pregunta1_bess_cotas import LIM, cfg_base, flujo_ac_24h  # noqa: E402
from modelo.misocp_hc_bess import config_tabla1, run_hc_bess  # noqa: E402
from verificacion.etapa2_tabla1 import flujo_ac  # noqa: E402

RESULTS_JSON = os.path.join(BASE_DIR, "results", "pregunta4_relajacion.json")
THREADS = int(os.environ.get("HC_THREADS", "0")) or None
TOL_BARRERA = {"BarQCPConvTol": 1e-10, "BarConvTol": 1e-10}
HC_P1_BESS005 = 12818.25       # óptimo demostrado de la pregunta 1 (2 x 50 kW, julio)


def _casos(bess: bool):
    casos = {}
    for esc in (1, 2):
        for tag, ps in (("con", -0.46), ("sin", None)):
            casos[f"tabla1_esc{esc}_{tag}"] = (
                f"Tabla 1 de [4], escenario {esc}, {'con' if ps else 'sin'} límite de exportación",
                lambda exacto, esc=esc, ps=ps, tl=300: config_tabla1(
                    esc, p_s_ref_pu=ps, exact_cone=exacto, threads=THREADS, time_limit=tl,
                    gurobi_params={} if exacto else TOL_BARRERA))
    for tag, ps in (("con", -0.46), ("sin", None)):
        casos[f"24h_{tag}"] = (
            f"Julio, 24 h, sin BESS, {'con' if ps else 'sin'} límite de exportación",
            lambda exacto, ps=ps: cfg_base(7, p_s_ref_pu=ps, n_bess_max=0, bess_candidates=[],
                                           mip_gap=1e-4, exact_cone=exacto, threads=THREADS,
                                           time_limit=600, gurobi_params={} if exacto else TOL_BARRERA))
    if bess:
        casos["24h_bess005"] = (
            "Julio, 24 h, 2 BESS de 50 kW en 32 y 33 (exacto: óptimo de la pregunta 1)",
            lambda exacto: cfg_base(7, p_b_max_mw=0.05, e_b_max_mwh=0.1, bess_candidates=[32, 33],
                                    mip_gap=1e-4, exact_cone=exacto, threads=THREADS, time_limit=900,
                                    gurobi_params={} if exacto else TOL_BARRERA))
    return casos


def _resumen(res) -> dict:
    s = res["summary"]
    T = res["config"].T
    out = {"status": int(s["status"]), "mip_gap": float(s["mip_gap"]), "tiempo_s": float(s["runtime_s"]),
           "HC_kW": s["hosting_capacity_PV_MW"] * 1000.0,
           "sitios_kW": {int(b): p * 1000.0 for b, p in zip(res["pv_sites"]["bus"], res["pv_sites"]["P_cap_MW"])
                         if p * 1000.0 >= 1.0},
           "perdidas_kW_medias": s["losses_MWh"] * 1000.0 / (T * res["config"].dt),
           "perdidas_ficticias_kW_medias": s["fictitious_losses_MWh"] * 1000.0 / (T * res["config"].dt),
           "brecha_rel_max": float(s["conic_gap_rel"]),
           "ramas_hora_brecha_1e-4": int(sum(1 for (j, t), g in res["conic_gap_map"].items()
                                              if g / max(res["vars"]["v"][res["network"].parent[j], t].X
                                                         * res["vars"]["l"][j, t].X, 1e-12) > 1e-4)),
           "P_S_min_kW": float(res["substation"]["P_S_MW"].min()) * 1000.0}
    return out


def _ac(res, p_s_ref) -> dict:
    """Flujo AC con el PV (y BESS) de la solución; mide límites y error de tensión del modelo."""
    if res["config"].T == 1:
        ac = flujo_ac(_resumen(res)["sitios_kW"])
        V = ac.pop("V")
        ac["max_dV_modelo"] = max(abs(float(res["voltages"].loc[1, j]) - V[j]) for j in V)
    else:
        ac = flujo_ac_24h(res)
        ac.pop("cumple", None)
    ac["viola"] = [k for k, c in (
        ("exportación", p_s_ref is not None and ac["export_kW"] > LIM["export_kW"] + 1.0),
        ("V_max", ac["Vmax_pu"] > LIM["Vmax_pu"] + 1e-4), ("V_min", ac["Vmin_pu"] < LIM["Vmin_pu"] - 1e-4),
        ("I_max", ac["Imax_A"] > LIM["Imax_A"] + 0.5)) if c]
    return ac


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bess", action="store_true", help="agrega el caso de 24 h con 2 BESS de 50 kW")
    a = ap.parse_args()
    t0 = time.time()
    print("=" * 78)
    print("PREGUNTA 4: error de la relajación cónica (MISOCP) frente al modelo exacto (MIQCP)")
    print("=" * 78)
    out = {"descripcion": "Pregunta 4: MISOCP relajado vs MIQCP exacto, objetivo max sum P^PV",
           "limites": LIM, "casos": {}}
    for clave, (desc, mk) in _casos(a.bess).items():
        print(f"\n--- {desc} ---", flush=True)
        caso = {"descripcion": desc}
        for nombre, exacto in (("exacto", True), ("relajado", False)):
            if clave == "24h_bess005" and exacto:
                caso["exacto"] = {"HC_kW": HC_P1_BESS005, "fuente": "pregunta 1 (óptimo demostrado)"}
                continue
            cfg = mk(exacto)
            res = run_hc_bess(cfg, save=False)
            if not res["summary"].get("solution"):
                caso[nombre] = {"status": int(res["summary"]["status"]), "HC_kW": None}
                print(f"  {nombre:<8} sin solución (status {res['summary']['status']})", flush=True)
                continue
            r = _resumen(res)
            r["ac"] = _ac(res, cfg.p_s_ref_pu)
            caso[nombre] = r
            print(f"  {nombre:<8} HC = {r['HC_kW']:8.1f} kW | sitios {sorted(r['sitios_kW'])} | "
                  f"pérdidas {r['perdidas_kW_medias']:.0f} kW (ficticias {r['perdidas_ficticias_kW_medias']:.0f}) | "
                  f"brecha rel {r['brecha_rel_max']:.1e} | gap {r['mip_gap']:.0e} | {r['tiempo_s']:.0f} s", flush=True)
            ac = r["ac"]
            print(f"           AC: exportación {ac['export_kW']:.0f} kW, V {ac['Vmin_pu']:.4f}-{ac['Vmax_pu']:.4f}, "
                  f"I máx {ac['Imax_A']:.0f} A, |dV| modelo-AC {ac['max_dV_modelo']:.1e}"
                  + (f"  ** VIOLA: {', '.join(ac['viola'])} **" if ac["viola"] else "  (cumple)"), flush=True)
        ex, rl = caso.get("exacto", {}).get("HC_kW"), caso.get("relajado", {}).get("HC_kW")
        if ex and rl:
            caso["error_HC_rel"] = (rl - ex) / ex
            print(f"  => error del relajado: {rl - ex:+.0f} kW ({caso['error_HC_rel']:+.1%})", flush=True)
        out["casos"][clave] = caso
        with open(RESULTS_JSON, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2, ensure_ascii=False, default=float)
    print(f"\nGuardado: {os.path.relpath(RESULTS_JSON, BASE_DIR)} ({(time.time() - t0) / 60:.1f} min)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
