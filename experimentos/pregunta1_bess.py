"""
experimentos/pregunta1_bess.py
==============================
Pregunta de investigación 1: ¿cuánto cambia el HC con y sin BESS, bajo qué condiciones y a qué costo?

Modelo multiperíodo (T = 24 h, julio) exacto, max sum P^PV, sin vertimiento, SoC cíclico
(experimentos/comun_24h.py). Se barre el presupuesto de energía de los BESS, sum_j E_j <= B, sin
costo de inversión: la frontera HC vs B y su pendiente (kW de HC por kWh de BESS) permiten evaluar
el costo después.

    Barrido A: tau = 2 h, B en {0.5, 1, 2, 4, 8} MWh, con y sin el límite de exportación de 4.6 MW.
    Barrido B: tau = 4 h, mismo B, solo con el límite de exportación (¿limita la potencia o la energía?).

Método (decisiones D8-D10 del equipo; el modelo exacto con BESS no cierra el gap si elige los sitios):
    1. Sin BESS (B = 0) se resuelve el modelo completo (PV en cualquier barra) => sitios PV.
    2. Con BESS, el PV queda en esos sitios (tamaños libres) y se enumeran todas las ubicaciones de
       BESS: las 8 barras candidatas solas y los 28 pares. Cada combinación se resuelve exacta
       (~30 s, gap <= 1e-4) y se certifica con el flujo AC hora a hora. Se reporta la mejor.
    3. Verificación (aparte, experimentos/pregunta1_verificacion.py): la mejor combinación de BESS se
       resuelve con el PV libre en las 32 barras partiendo de la solución completa. La versión dentro
       de este script (--verificar) solo usa un arranque parcial y no sirvió: gaps de 6-20 % en 10 min.
    Los BESS cargan solo en las horas con sol y descargan solo en las demás (bess_horas_carga):
    excluye cargar y descargar a la vez sin binarias; con B = 2 MWh da el mismo HC que con binarias.

El script es reanudable: guarda results/pregunta1_bess.json después de cada solución y no repite
las que ya están (--rehacer para forzarlas). El resultado completo de la mejor combinación de cada
configuración queda en results/pregunta1/ (graficable con modelo/grafico_resultados.py).

Uso (desde cualquier carpeta):
    python experimentos/pregunta1_bess.py                  # todo (~3 h)
    python experimentos/pregunta1_bess.py --barrido A      # solo un barrido
    HC_WORKERS=1 python experimentos/pregunta1_bess.py     # una combinación a la vez
"""
import argparse
import itertools
import json
import multiprocessing as mp
import os
import sys
import time

# OJO: NO usar rutas absolutas (p.ej. r"C:\Users\..." o "/Users/..."): solo funcionan en un PC.
# Se resuelve la raíz del proyecto relativa a este archivo (<raíz>/<carpeta>/este_script.py).
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # raíz del proyecto
sys.path.insert(0, BASE_DIR)

from experimentos.comun_24h import (BESS_CANDIDATOS, EXPORTACION, HORAS_SOL,  # noqa: E402
                                    config_24h, resolver_24h, resumen)
from modelo.misocp_hc_bess import save_results  # noqa: E402

RESULTS_JSON = os.path.join(BASE_DIR, "results", "pregunta1_bess.json")
RUNS_DIR = os.path.join(BASE_DIR, "results", "pregunta1")
PRESUPUESTOS = [0.5, 1.0, 2.0, 4.0, 8.0]
BARRIDOS = {
    "A": [("con_limite", 2.0), ("sin_limite", 2.0)],
    "B": [("con_limite", 4.0)],
}
WORKERS = int(os.environ.get("HC_WORKERS", "2"))
THREADS = max(1, (os.cpu_count() or 8) // WORKERS)
TL_COMBO = 180.0          # [s] por combinación de sitios (normalmente cierra en ~30 s)
TL_VERIF = 600.0          # [s] verificación con PV libre
TL_SIN_BESS = 1200.0      # [s] caso sin BESS (PV libre)

# Opciones comunes con BESS: cono exacto en todas las horas, sin binarias de carga/descarga,
# ventanas de carga (horas con sol) y descarga (resto).
OPC_BESS = dict(exact_cone_horas=None, bess_mu_binaries=False, bess_horas_carga=list(HORAS_SOL))


def combinaciones():
    return [(j,) for j in BESS_CANDIDATOS] + list(itertools.combinations(BESS_CANDIDATOS, 2))


def _warm(sitios_pv_kW):
    return {"w": {int(j): 1 for j in sitios_pv_kW},
            "Ppv_cap": {int(j): p / 1000 for j, p in sitios_pv_kW.items()}}


def _compacto(r) -> dict:
    s = r["summary"]
    if not s.get("solution"):
        return {"solucion": False, "status": int(s["status"])}
    rs = resumen(r, r["ac"])
    keep = ("HC_kW", "cota_HC_kW", "sitios_pv_kW", "bess", "BESS_P_MW", "BESS_E_MWh", "status", "mip_gap",
            "tiempo_s", "perdidas_MWh", "bess_simultaneo_MW")
    out = {k: rs[k] for k in keep}
    out.update(solucion=True, certificado_AC=bool(s.get("certificado_AC", False)),
               viola_limites_AC=bool(r["ac"]["viola_limites_AC"]), limites_activos=r["ac"]["limites_activos"],
               horas_activas=r["ac"]["horas_activas"])
    return out


def _resolver_combo(args):
    """Proceso hijo: resuelve una combinación de sitios BESS con el PV fijo en sus sitios."""
    exp, tau, B, combo, pv_sitios_kW = args
    cfg = config_24h(B, p_s_ref=EXPORTACION[exp], tau_h=tau, time_limit=TL_COMBO, threads=THREADS,
                     pv_candidates=sorted(int(j) for j in pv_sitios_kW), bess_candidates=list(combo),
                     n_bess_max=len(combo), **OPC_BESS)
    return combo, _compacto(resolver_24h(cfg, warm=_warm(pv_sitios_kW)))


def clave(exp, tau, B):
    return f"{exp}|tau={tau:g}|B={B:g}"


def cargar() -> dict:
    if os.path.exists(RESULTS_JSON):
        with open(RESULTS_JSON, encoding="utf-8") as f:
            return json.load(f)
    return {"descripcion": "Pregunta 1: HC vs presupuesto de energía BESS (julio, 24 h, modelo exacto, "
                           "SoC cíclico, sitios BESS enumerados)", "sin_bess": {}, "corridas": {}}


def guardar(out: dict):
    os.makedirs(os.path.dirname(RESULTS_JSON), exist_ok=True)
    tmp = RESULTS_JSON + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False, default=float)
    os.replace(tmp, RESULTS_JSON)


def _guardar_completo(r, cfg, nombre) -> str:
    os.makedirs(RUNS_DIR, exist_ok=True)
    save_results(r, cfg, out_dir=RUNS_DIR, filename=nombre)
    return os.path.relpath(os.path.join(RUNS_DIR, nombre + ".json"), BASE_DIR)


def _linea(tag, c):
    if not c.get("solucion"):
        return f"[{tag}] sin solución (status {c.get('status')})"
    bess = ", ".join(f"{b['bus']}: {b['P_MW']:.2f} MW/{b['E_MWh']:.2f} MWh" for b in c["bess"] if b["E_MWh"] > 1e-4) or "-"
    return (f"[{tag}] HC = {c['HC_kW']:8.1f} kW (cota {c['cota_HC_kW']:.0f}) | PV "
            f"{ {int(j): round(p) for j, p in c['sitios_pv_kW'].items()} } | BESS {bess} | gap {c['mip_gap']:.0e}"
            f" | {c['tiempo_s']:.0f} s | activos: {', '.join(c['limites_activos']) or '-'} (h {c['horas_activas']})"
            + ("" if c["certificado_AC"] else "  ** NO CERTIFICADO EN AC **"))


def sin_bess(out, exp, rehacer) -> dict:
    if exp in out["sin_bess"] and not rehacer:
        return out["sin_bess"][exp]
    cfg = config_24h(0.0, p_s_ref=EXPORTACION[exp], time_limit=TL_SIN_BESS, exact_cone_horas=None)
    r = resolver_24h(cfg)
    c = _compacto(r)
    c["archivo"] = _guardar_completo(r, cfg, f"p1_{exp}_B0")
    out["sin_bess"][exp] = c
    guardar(out)
    print(_linea(f"{exp}|sin BESS", c), flush=True)
    return c


def main() -> int:
    ap = argparse.ArgumentParser(description="Pregunta 1: HC con y sin BESS (24 h).")
    ap.add_argument("--barrido", choices=sorted(BARRIDOS), action="append")
    ap.add_argument("--rehacer", action="store_true", help="vuelve a resolver lo ya guardado")
    ap.add_argument("--verificar", action="store_true",
                    help="verificación con PV libre y arranque parcial (mejor: pregunta1_verificacion.py)")
    args = ap.parse_args()

    out = cargar()
    malos = []
    ctx = mp.get_context("spawn")
    for nombre in args.barrido or sorted(BARRIDOS):
        for exp, tau in BARRIDOS[nombre]:
            base = sin_bess(out, exp, args.rehacer)
            pv = base["sitios_pv_kW"]
            for B in PRESUPUESTOS:
                k = clave(exp, tau, B)
                run = out["corridas"].setdefault(k, {"exportacion": exp, "tau_h": tau, "B_MWh": B,
                                                     "combinaciones": {}})
                if args.rehacer:
                    run["combinaciones"] = {}
                pendientes = [cb for cb in combinaciones() if "-".join(map(str, cb)) not in run["combinaciones"]]
                t0 = time.time()
                if pendientes:
                    print(f"\n[{k}] {len(pendientes)} combinaciones de sitios BESS ({WORKERS} en paralelo)...",
                          flush=True)
                    with ctx.Pool(WORKERS) as pool:
                        for combo, c in pool.imap_unordered(_resolver_combo,
                                                            [(exp, tau, B, cb, pv) for cb in pendientes]):
                            run["combinaciones"]["-".join(map(str, combo))] = c
                            guardar(out)
                validas = {cb: c for cb, c in run["combinaciones"].items()
                           if c.get("solucion") and c["certificado_AC"]}
                if not validas:
                    print(f"[{k}] ninguna combinación válida", flush=True)
                    malos.append(k)
                    continue
                mejor = max(validas, key=lambda cb: validas[cb]["HC_kW"])
                n_abiertas = sum(1 for c in run["combinaciones"].values()
                                 if c.get("solucion") and c["mip_gap"] > 1e-4)
                run.update(mejor_combinacion=mejor, mejor=validas[mejor], combinaciones_sin_cerrar=n_abiertas,
                           cota_max_kW=max(c["cota_HC_kW"] for c in run["combinaciones"].values()
                                           if c.get("solucion")),
                           tiempo_enumeracion_s=run.get("tiempo_enumeracion_s", 0.0) + time.time() - t0)
                print(_linea(f"{k} mejor {mejor}", validas[mejor]), flush=True)

                # Resultado completo de la mejor combinación y verificación con PV libre
                combo = [int(j) for j in mejor.split("-")]
                if "archivo" not in run or args.rehacer:
                    cfg = config_24h(B, p_s_ref=EXPORTACION[exp], tau_h=tau, time_limit=TL_COMBO,
                                     pv_candidates=sorted(int(j) for j in pv), bess_candidates=combo,
                                     n_bess_max=len(combo), **OPC_BESS)
                    r = resolver_24h(cfg, warm=_warm(pv))
                    run["archivo"] = _guardar_completo(r, cfg, f"p1_{exp}_tau{tau:g}_B{B:g}".replace(".", "p"))
                    run["mejor_completo"] = resumen(r, r["ac"])
                    guardar(out)
                if args.verificar and ("verificacion_pv_libre" not in run or args.rehacer):
                    cfg = config_24h(B, p_s_ref=EXPORTACION[exp], tau_h=tau, time_limit=TL_VERIF,
                                     pv_candidates=None, bess_candidates=combo, n_bess_max=len(combo),
                                     **OPC_BESS)
                    c = _compacto(resolver_24h(cfg, warm=_warm(run["mejor"]["sitios_pv_kW"])))
                    run["verificacion_pv_libre"] = c
                    guardar(out)
                    print(_linea(f"{k} verificación PV libre", c), flush=True)
                if not run["mejor"]["certificado_AC"] or run["mejor"]["viola_limites_AC"]:
                    malos.append(k)

    print(f"\nGuardado: {os.path.relpath(RESULTS_JSON, BASE_DIR)}")
    print("Todas las configuraciones tienen una solución certificada en AC." if not malos
          else f"OJO: configuraciones con problemas: {malos}")
    return 0 if not malos else 1


if __name__ == "__main__":
    sys.exit(main())
