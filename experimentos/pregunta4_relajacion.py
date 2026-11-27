"""
experimentos/pregunta4_relajacion.py
====================================
Pregunta 4: ¿cuánto afecta la relajación cónica respecto del problema original (MIQCP)?

Compara, en el modelo de 24 h de julio, el MIQCP exacto (P^2 + Q^2 = v*l) con el MISOCP relajado del
informe (P^2 + Q^2 <= v*l), y valida las inyecciones de la solución relajada (PV y BESS) en un flujo
AC de pandapower: si el modelo relajado "disipa" PV en pérdidas ficticias, la red real viola límites.
    * Sin BESS, con y sin el límite de exportación (PV en cualquier barra).
    * Con BESS (2 x 0.5 MW y 2 x 2 MW, tau = 2 h, límite de exportación): relajado con la ubicación libre
      (es convexo, así que elige sitios sin problema) y exacto con la mejor ubicación de
      experimentos/pregunta1_bess.py.
La comparación de la Tabla 1 de [4] (carga base) ya está en verificacion/preliminar_tabla1.py.

Uso (desde cualquier carpeta):
    python experimentos/pregunta4_relajacion.py
Escribe results/pregunta4_relajacion.json.
"""
import json
import os
import sys

# OJO: NO usar rutas absolutas (p.ej. r"C:\Users\..." o "/Users/..."): solo funcionan en un PC.
# Se resuelve la raíz del proyecto relativa a este archivo (<raíz>/<carpeta>/este_script.py).
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # raíz del proyecto
sys.path.insert(0, BASE_DIR)

from experimentos.comun_24h import EXPORTACION, config_24h, resolver_24h, resumen  # noqa: E402

RESULTS_JSON = os.path.join(BASE_DIR, "results", "pregunta4_relajacion.json")
P1_JSON = os.path.join(BASE_DIR, "results", "pregunta1_bess.json")
THREADS = int(os.environ.get("HC_THREADS", "0")) or None


def _relajado(P, exp) -> dict:
    cfg = config_24h(P, p_s_ref=EXPORTACION[exp], exact_cone=False, time_limit=600, threads=THREADS)
    r = resolver_24h(cfg)
    s, ac = r["summary"], r["ac"]
    rs = resumen(r, ac)
    return {"HC_kW": rs["HC_kW"], "sitios_pv_kW": rs["sitios_pv_kW"], "bess": rs["bess"], "mip_gap": rs["mip_gap"],
            "tiempo_s": rs["tiempo_s"], "perdidas_MWh": s["losses_MWh"],
            "perdidas_ficticias_MWh": s["fictitious_losses_MWh"], "brecha_rel_max": s["conic_gap_rel"],
            "ac_peor": ac["peor"], "viola_limites_AC": ac["viola_limites_AC"],
            "horas_con_violacion": [h["t"] - 1 for h in ac["horas"] if (
                h["Vmax_pu"] > 1.1001 or h["Imax_A"] > 300.5
                or (cfg.p_s_ref_pu is not None and h["export_kW"] > 4601.0))]}


def main() -> int:
    with open(P1_JSON, encoding="utf-8") as f:
        p1 = json.load(f)
    out = {"descripcion": "Pregunta 4: MIQCP exacto vs MISOCP relajado (julio, 24 h)", "casos": {}}
    casos = [(0.0, "con_limite"), (0.0, "sin_limite"), (0.5, "con_limite"), (2.0, "con_limite")]
    for P, exp in casos:
        exacto = p1["sin_bess"][exp] if P == 0 else p1["corridas"][f"{exp}|tau=2|P={P:g}"]["mejor"]
        rel = _relajado(P, exp)
        c = {"P_MW": P, "exportacion": exp, "exacto_HC_kW": exacto["HC_kW"], "relajado": rel,
             "sobreestimacion_pct": 100.0 * (rel["HC_kW"] / exacto["HC_kW"] - 1.0)}
        out["casos"][f"{exp}|P={P:g}"] = c
        print(f"  2 x {P:g} MW, {exp:<10}: exacto {exacto['HC_kW']:8.1f} kW | relajado {rel['HC_kW']:8.1f} kW "
              f"({c['sobreestimacion_pct']:+.1f} %), pérdidas ficticias {rel['perdidas_ficticias_MWh']:.2f} MWh | "
              f"AC del relajado: V_max {rel['ac_peor']['Vmax_pu']:.4f}, I_max {rel['ac_peor']['Imax_A']:.0f} A, "
              f"exportación {rel['ac_peor']['export_kW']:.0f} kW, viola en h {rel['horas_con_violacion']}",
              flush=True)
        with open(RESULTS_JSON, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2, ensure_ascii=False, default=float)
    print(f"\nGuardado: {os.path.relpath(RESULTS_JSON, BASE_DIR)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
