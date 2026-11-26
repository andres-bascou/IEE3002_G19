"""
experimentos/pregunta3_sensibilidad.py
======================================
Pregunta 3: ¿cómo cambian las soluciones al variar los parámetros? (modelo de 24 h, julio)

Parte "sin_bess" (rápida, experimentos/sin_bess_24h.resolver_sin_bess):
    * Factor de potencia del PV: 1.00 (base, [4]) vs 0.95 absorbiendo reactivos, con y sin el
      límite de exportación (decisión D7 del equipo).
    * Límite de exportación: 0 (sin flujo inverso), 2.3, 4.6 (base [4]), 6.9 MW y sin límite.
Parte "bess" (después de experimentos/pregunta1_bess.py; usa la mejor ubicación de BESS de cada
configuración y la resuelve exacta con los sitios fijos, ~30 s por caso):
    * Eficiencias eta_ch = eta_dis en {0.90, 0.95 (base), 0.98}.
    * Profundidad de descarga: SoC en [0.10, 0.90] (base), [0.20, 0.80] y [0.05, 0.95].
    * Factor de potencia 0.95 con BESS.
    Con B = 2 MWh, tau = 2 h y el límite de exportación (y sin límite para el fp).

Uso (desde cualquier carpeta):
    python experimentos/pregunta3_sensibilidad.py --parte sin_bess
    python experimentos/pregunta3_sensibilidad.py --parte bess
Escribe results/pregunta3_sensibilidad.json (conserva la otra parte si ya existe).
"""
import argparse
import json
import os
import sys

# OJO: NO usar rutas absolutas (p.ej. r"C:\Users\..." o "/Users/..."): solo funcionan en un PC.
# Se resuelve la raíz del proyecto relativa a este archivo (<raíz>/<carpeta>/este_script.py).
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # raíz del proyecto
sys.path.insert(0, BASE_DIR)

from experimentos.comun_24h import EXPORTACION, HORAS_SOL, config_24h, resolver_24h, resumen  # noqa: E402
from experimentos.sin_bess_24h import resolver_sin_bess  # noqa: E402

RESULTS_JSON = os.path.join(BASE_DIR, "results", "pregunta3_sensibilidad.json")
P1_JSON = os.path.join(BASE_DIR, "results", "pregunta1_bess.json")
THREADS = int(os.environ.get("HC_THREADS", "0")) or None
EXPORT_MW = {"0": 0.0, "2.3": -0.23, "4.6": -0.46, "6.9": -0.69, "sin_limite": None}
B_REF, TAU_REF = 2.0, 2.0
TL_SIN_BESS = 1200      # [s] por caso sin BESS (los de fp = 0.95 no cierran el gap en 300 s)
OPC_BESS = dict(exact_cone_horas=None, bess_mu_binaries=False, bess_horas_carga=list(HORAS_SOL))


def _corto(r: dict) -> dict:
    keep = ("HC_kW", "sitios_kW", "mip_gap", "tiempo_s", "certificado_AC", "limites_activos", "horas_activas",
            "status")
    return {k: r.get(k) for k in keep}


def parte_sin_bess() -> dict:
    out = {"fp": {}, "exportacion": {}}
    for tag, ps in EXPORTACION.items():
        for pf in (1.0, 0.95):
            r = _corto(resolver_sin_bess(config_24h(0.0, p_s_ref=ps, pv_pf=pf, threads=THREADS,
                                                    time_limit=TL_SIN_BESS)))
            out["fp"][f"{tag}|fp={pf:g}"] = r
            print(f"  fp = {pf:4.2f}, exportación {tag:<10}: HC = {r['HC_kW']:8.1f} kW | PV "
                  f"{ {j: round(p) for j, p in r['sitios_kW'].items()} } | activos {r['limites_activos']}", flush=True)
    for tag, ps in EXPORT_MW.items():
        r = _corto(resolver_sin_bess(config_24h(0.0, p_s_ref=ps, threads=THREADS, time_limit=TL_SIN_BESS)))
        out["exportacion"][tag] = r
        print(f"  límite de exportación {tag:>10} MW: HC = {r['HC_kW']:8.1f} kW | PV "
              f"{ {j: round(p) for j, p in r['sitios_kW'].items()} } | activos {r['limites_activos']}", flush=True)
    return out


def _caso_bess(exp: str, nombre: str, **kw) -> dict:
    with open(P1_JSON, encoding="utf-8") as f:
        p1 = json.load(f)
    run = p1["corridas"][f"{exp}|tau={TAU_REF:g}|B={B_REF:g}"]
    combo = [int(j) for j in run["mejor_combinacion"].split("-")]
    pv = run["mejor"]["sitios_pv_kW"]
    cfg = config_24h(B_REF, p_s_ref=EXPORTACION[exp], tau_h=TAU_REF, time_limit=300, threads=THREADS,
                     pv_candidates=sorted(int(j) for j in pv), bess_candidates=combo, n_bess_max=len(combo),
                     **OPC_BESS, **kw)
    r = resolver_24h(cfg, warm={"w": {int(j): 1 for j in pv}, "Ppv_cap": {int(j): p / 1000 for j, p in pv.items()}})
    s = resumen(r, r["ac"])
    c = {k: s[k] for k in ("HC_kW", "cota_HC_kW", "sitios_pv_kW", "bess", "mip_gap", "tiempo_s")}
    c.update(certificado_AC=bool(r["summary"].get("certificado_AC")), limites_activos=r["ac"]["limites_activos"],
             sitios_bess=combo, HC_sin_bess_kW=p1["sin_bess"][exp]["HC_kW"], HC_base_kW=run["mejor"]["HC_kW"])
    print(f"  {nombre:<28} ({exp}): HC = {c['HC_kW']:8.1f} kW (base {c['HC_base_kW']:.1f}, sin BESS "
          f"{c['HC_sin_bess_kW']:.1f}) | gap {c['mip_gap']:.0e} | {c['tiempo_s']:.0f} s"
          + ("" if c["certificado_AC"] else "  ** NO CERTIFICADO EN AC **"), flush=True)
    return c


def parte_bess() -> dict:
    out = {"eficiencia": {}, "soc": {}, "fp": {}}
    for eta in (0.90, 0.98):
        out["eficiencia"][f"{eta:g}"] = _caso_bess("con_limite", f"eta = {eta:g}", eta_ch=eta, eta_dis=eta)
    for kmin, kmax in ((0.20, 0.80), (0.05, 0.95)):
        out["soc"][f"{kmin:g}-{kmax:g}"] = _caso_bess("con_limite", f"SoC en [{kmin:g}, {kmax:g}]",
                                                      kappa_min=kmin, kappa_max=kmax, kappa_0=kmin)
    for exp in EXPORTACION:
        out["fp"][exp] = _caso_bess(exp, "fp = 0.95", pv_pf=0.95)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Pregunta 3: sensibilidad (24 h).")
    ap.add_argument("--parte", choices=("sin_bess", "bess"), action="append")
    partes = ap.parse_args().parte or ["sin_bess", "bess"]
    out = {}
    if os.path.exists(RESULTS_JSON):
        with open(RESULTS_JSON, encoding="utf-8") as f:
            out = json.load(f)
    out["descripcion"] = "Pregunta 3: sensibilidad del HC (julio, 24 h, modelo exacto)"
    for parte in partes:
        print(f"\n=== Parte {parte} ===", flush=True)
        out[parte] = parte_sin_bess() if parte == "sin_bess" else parte_bess()
        with open(RESULTS_JSON, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2, ensure_ascii=False, default=float)
    print(f"\nGuardado: {os.path.relpath(RESULTS_JSON, BASE_DIR)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
