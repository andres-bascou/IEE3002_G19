"""
experimentos/pregunta2_24h_entrega_final.py
===========================================
Pregunta 2 (PV concentrado vs distribuido) con el modelo de 24 h de julio, sin BESS.

Mismos barridos que experimentos/pregunta2_concentrado_distribuido.py (carga base), pero con los
perfiles horarios de julio (config_24h):
    A. Número de sitios:  n_pv_max en {1, 2, 3, 4, 6, 8, 12, 32}   (32 = sin límite)
    B. Tope por sitio:    p_pv_max en {0.25, 0.5, 1, 2, 4, 20} MW  con n_pv_max = 32
    C. Uniforme:          la misma capacidad en las 32 barras
Cada barrido con y sin el límite de exportación de 4.6 MW.

Se resuelve con experimentos/sin_bess_24h.resolver_sin_bess: modelo exacto en las horas que
limitan, certificado con un flujo AC en las 24 horas (exacto para el modelo de 24 h sin BESS).
Monotonía como en la versión de carga base: si n' sitios ya alcanzan el HC sin límite de sitios,
todo n > n' tiene ese HC y no se resuelve.

Uso (desde cualquier carpeta):
    python experimentos/pregunta2_24h_entrega_final.py
Escribe results/pregunta2_24h_entrega_final.json.
"""
import json
import os
import sys

# OJO: NO usar rutas absolutas (p.ej. r"C:\Users\..." o "/Users/..."): solo funcionan en un PC.
# Se resuelve la raíz del proyecto relativa a este archivo (<raíz>/<carpeta>/este_script.py).
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # raíz del proyecto
sys.path.insert(0, BASE_DIR)

from experimentos.comun_24h import EXPORTACION, config_24h  # noqa: E402
from experimentos.sin_bess_24h import resolver_sin_bess  # noqa: E402

RESULTS_JSON = os.path.join(BASE_DIR, "results", "pregunta2_24h_entrega_final.json")
N_SITIOS = [1, 2, 3, 4, 6, 8, 12, 32]
TOPES_MW = [0.25, 0.5, 1.0, 2.0, 4.0, 20.0]
THREADS = int(os.environ.get("HC_THREADS", "0")) or None
TIME_LIMIT = 300
TOL_IGUAL = 1e-4


def resolver(ps, uniforme=False, **kw):
    kw.setdefault("threads", THREADS)
    kw.setdefault("time_limit", TIME_LIMIT)
    r = resolver_sin_bess(config_24h(0.0, p_s_ref=ps, **kw), uniforme=uniforme)
    if not r["solucion"]:
        raise RuntimeError(f"Sin solución: {kw}, uniforme={uniforme}")
    return r


def _imprimir(nombre, r):
    top = sorted(r["sitios_kW"].items(), key=lambda kv: -kv[1])[:3]
    print(f"  {nombre:<22} HC = {r['HC_kW']:8.1f} kW | {r['n_sitios']:>2} sitios "
          f"(mayores: {', '.join(f'{j}: {p:.0f}' for j, p in top)}) | activos: "
          f"{', '.join(r['limites_activos']) or '-'} (h {r['horas_activas']}) | gap {r['mip_gap']:.0e} | "
          f"{r['tiempo_s']:.1f} s" + ("  (certificado por monotonía)" if r.get("certificado_por") else "")
          + ("" if r["certificado_AC"] else "  ** NO CERTIFICADO EN AC **"), flush=True)


def main() -> int:
    out = {"descripcion": "Pregunta 2 en 24 h (julio, sin BESS, modelo exacto en horas críticas + AC 24 h)"}
    malos = []
    for tag, ps in EXPORTACION.items():
        print(f"\n=== Exportación {tag.replace('_', ' ')} ===", flush=True)
        b = {"n_sitios": {}, "tope_MW": {}}
        libre = resolver(ps, n_pv_max=max(N_SITIOS))
        alcanzado = None
        for n in N_SITIOS:
            if n == max(N_SITIOS):
                r = libre
            elif alcanzado is not None:
                r = dict(b["n_sitios"][str(alcanzado)], tiempo_s=0.0,
                         certificado_por=f"monotonía: HC({alcanzado}) = HC(sin límite de sitios)")
            else:
                r = resolver(ps, n_pv_max=n)
                if r["status"] == 2 and r["HC_kW"] >= libre["HC_kW"] * (1 - TOL_IGUAL):
                    alcanzado = n
            b["n_sitios"][str(n)] = r
            _imprimir(f"n_pv_max = {n:>2}", r)
        for tope in TOPES_MW:
            r = resolver(ps, p_pv_max_mw=tope)
            b["tope_MW"][str(tope)] = r
            _imprimir(f"tope {tope:>5} MW", r)
        b["uniforme"] = resolver(ps, uniforme=True)
        _imprimir("uniforme (32 barras)", b["uniforme"])
        out[tag] = b
        malos += [f"{tag}:{g}:{k}" for g in ("n_sitios", "tope_MW") for k, r in b[g].items()
                  if not r["certificado_AC"] or (r["status"] != 2 and not r.get("certificado_por"))]
    os.makedirs(os.path.dirname(RESULTS_JSON), exist_ok=True)
    with open(RESULTS_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False, default=float)
    print(f"\nGuardado: {os.path.relpath(RESULTS_JSON, BASE_DIR)}")
    print("Todas las soluciones son óptimas y certificadas en AC." if not malos else f"OJO: {malos}")
    return 0 if not malos else 1


if __name__ == "__main__":
    sys.exit(main())
