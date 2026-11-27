"""
experimentos/pregunta1_bess.py
==============================
Pregunta de investigación 1: ¿cuánto cambia el HC con y sin BESS, bajo qué condiciones y a qué costo?

Modelo multiperíodo (T = 24 h, julio) exacto, max sum P^PV, sin vertimiento, SoC final según (19) del
informe (experimentos/comun_24h.py). BESS de tamaño fijo por unidad: hasta 2 unidades de P MW y
tau * P MWh, P en {0.05, 0.25, 0.5, 1, 2} MW (mismos tamaños que experimentos/pregunta1_bess_cotas.py).

    Barrido A: tau = 2 h, con y sin el límite de exportación de 4.6 MW.
    Barrido B: tau = 4 h, solo con el límite de exportación (¿limita la potencia o la energía?).

Método combinado (decisión del equipo; el modelo exacto con BESS no cierra el gap si elige los sitios):
    * Cota superior horaria (comun_24h.cota_horaria, método de pregunta1_bess_cotas.py): válida para
      el problema completo (PV y BESS en cualquier barra). No depende de tau.
    * Solución (cota inferior): sitios fijos, cada combinación resuelta exacta y certificada con el flujo
      AC hora a hora. Se enumeran los 28 pares de las 8 barras candidatas (con el PV en los sitios del
      óptimo sin BESS) y además: los casos que probó pregunta1_bess_cotas.py y el par de BESS + barras
      de PV que sugiere la solución de la hora crítica de la cota horaria. Se reporta la mejor.
    * La verificación con el PV libre está en experimentos/pregunta1_verificacion.py.

El script es reanudable: guarda results/pregunta1_bess.json después de cada solución y no repite lo
que ya está (--rehacer para forzarlo). El resultado completo de la mejor combinación de cada
configuración queda en results/pregunta1/ (graficable con modelo/grafico_resultados.py).

Uso (desde cualquier carpeta):
    python experimentos/pregunta1_bess.py                  # todo
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

from experimentos.comun_24h import (BESS_CANDIDATOS, EXPORTACION, config_24h,  # noqa: E402
                                    cota_horaria, resolver_24h, resumen)
from modelo.misocp_hc_bess import save_results  # noqa: E402

RESULTS_JSON = os.path.join(BASE_DIR, "results", "pregunta1_bess.json")
COTAS_JSON = os.path.join(BASE_DIR, "results", "pregunta1_bess_cotas.json")
RUNS_DIR = os.path.join(BASE_DIR, "results", "pregunta1")
TAMANOS_MW = [0.05, 0.25, 0.5, 1.0, 2.0]
BARRIDOS = {
    "A": [("con_limite", 2.0), ("sin_limite", 2.0)],
    "B": [("con_limite", 4.0)],
}
WORKERS = int(os.environ.get("HC_WORKERS", "2"))
THREADS = max(1, (os.cpu_count() or 8) // WORKERS)
TL_COMBO = 300.0          # [s] por combinación de sitios
TL_SIN_BESS = 1200.0      # [s] caso sin BESS (PV libre)
TL_HORARIA = 900.0        # [s] por hora de la cota horaria


def _k(bess, pv) -> str:
    return f"b={'-'.join(map(str, sorted(bess)))}|pv={'-'.join(map(str, sorted(pv)))}"


def casos(exp, P, pv_base, horaria) -> list:
    """Combinaciones (sitios BESS, sitios PV) a resolver para una configuración."""
    pv0 = tuple(sorted(int(j) for j in pv_base))
    cs = [(par, pv0) for par in itertools.combinations(BESS_CANDIDATOS, 2)]
    # Casos de pregunta1_bess_cotas.py (solo existe con el límite de exportación)
    if exp == "con_limite" and os.path.exists(COTAS_JSON):
        with open(COTAS_JSON, encoding="utf-8") as f:
            d = json.load(f).get("tamanos", {}).get(f"{P:g}", {})
        for c in d.get("cota_inferior", {}).get("corridas", []):
            cs.append((tuple(sorted(c["par"])), tuple(sorted(c.get("pv_candidatas") or pv0))))
    # Sugerencia de la hora crítica de la cota horaria: sus barras de BESS y de PV
    sol = next((h for h in horaria["horas"] if h["t"] == horaria["t"]), {})
    if sol.get("bess_kW"):
        b = tuple(sorted(int(j) for j in sol["bess_kW"]))      # 1 o 2 barras
        cs.append((b, tuple(sorted(set(pv0) | {int(j) for j in sol.get("pv_kW", {})}))))
    vistos, out = set(), []
    for b, pv in cs:
        if _k(b, pv) not in vistos:
            vistos.add(_k(b, pv))
            out.append((b, pv))
    return out


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


def _cfg_combo(exp, tau, P, bess, pv, time_limit):
    return config_24h(P, p_s_ref=EXPORTACION[exp], tau_h=tau, time_limit=time_limit, threads=THREADS,
                      pv_candidates=list(pv), bess_candidates=list(bess), n_bess_max=2)


def _resolver_combo(args):
    """Proceso hijo: resuelve una combinación (sitios BESS, sitios PV)."""
    exp, tau, P, bess, pv, pv_base = args
    warm = _warm({j: p for j, p in pv_base.items() if int(j) in pv})
    return _k(bess, pv), _compacto(resolver_24h(_cfg_combo(exp, tau, P, bess, pv, TL_COMBO), warm=warm))


def clave(exp, tau, P):
    return f"{exp}|tau={tau:g}|P={P:g}"


def cargar() -> dict:
    if os.path.exists(RESULTS_JSON):
        with open(RESULTS_JSON, encoding="utf-8") as f:
            return json.load(f)
    return {"descripcion": "Pregunta 1: HC con 2 BESS de P MW (julio, 24 h, modelo exacto, SoC final (19), "
                           "sitios enumerados + cota superior horaria)", "sin_bess": {}, "cotas_horarias": {},
            "corridas": {}}


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
    return (f"[{tag}] HC = {c['HC_kW']:8.1f} kW | PV "
            f"{ {int(j): round(p) for j, p in c['sitios_pv_kW'].items()} } | BESS {bess} | gap {c['mip_gap']:.0e}"
            f" | {c['tiempo_s']:.0f} s | activos: {', '.join(c['limites_activos']) or '-'} (h {c['horas_activas']})"
            + ("" if c["certificado_AC"] else "  ** NO CERTIFICADO EN AC **"))


def sin_bess(out, exp, rehacer) -> dict:
    """Óptimo sin BESS. Los sitios de PV salen de sin_bess_24h.resolver_sin_bess (horas críticas +
    flujo AC de 24 h, exacto y en segundos): el modelo completo de 24 h no cierra el gap sin el
    límite de exportación (14 401 kW, gap 2 % en 20 min, frente a 14 484 kW óptimo). Luego se
    resuelve el modelo de 24 h con el PV en esos sitios, para guardar el resultado completo."""
    if exp in out["sin_bess"] and not rehacer:
        return out["sin_bess"][exp]
    from experimentos.sin_bess_24h import resolver_sin_bess
    rc = resolver_sin_bess(config_24h(0.0, p_s_ref=EXPORTACION[exp], time_limit=TL_SIN_BESS))
    if not (rc["solucion"] and rc["certificado_AC"]):
        raise RuntimeError(f"Sin BESS ({exp}): el atajo de horas críticas no dio una solución certificada.")
    cfg = config_24h(0.0, p_s_ref=EXPORTACION[exp], time_limit=TL_SIN_BESS,
                     pv_candidates=sorted(int(j) for j in rc["sitios_kW"]))
    r = resolver_24h(cfg, warm=_warm(rc["sitios_kW"]))
    c = _compacto(r)
    c["atajo_horas_criticas"] = {k: rc[k] for k in ("HC_kW", "sitios_kW", "mip_gap", "horas_modelo", "tiempo_s")}
    c["archivo"] = _guardar_completo(r, cfg, f"p1_{exp}_P0")
    out["sin_bess"][exp] = c
    guardar(out)
    print(_linea(f"{exp}|sin BESS", c), flush=True)
    return c


def horaria(out, exp, P, rehacer) -> dict:
    k = f"{exp}|P={P:g}"
    if k not in out["cotas_horarias"] or rehacer:
        out["cotas_horarias"][k] = cota_horaria(P, EXPORTACION[exp], time_limit=TL_HORARIA)
        guardar(out)
        h = out["cotas_horarias"][k]
        print(f"[{k}] cota superior horaria: {h['HC_cota_kW']:.1f} kW (hora {h['t'] - 1})", flush=True)
    return out["cotas_horarias"][k]


def main() -> int:
    ap = argparse.ArgumentParser(description="Pregunta 1: HC con y sin BESS (24 h).")
    ap.add_argument("--barrido", choices=sorted(BARRIDOS), action="append")
    ap.add_argument("--rehacer", action="store_true", help="vuelve a resolver lo ya guardado")
    args = ap.parse_args()

    out = cargar()
    malos = []
    ctx = mp.get_context("spawn")
    for nombre in args.barrido or sorted(BARRIDOS):
        for exp, tau in BARRIDOS[nombre]:
            base = sin_bess(out, exp, args.rehacer)
            pv_base = {int(j): p for j, p in base["sitios_pv_kW"].items()}
            for P in TAMANOS_MW:
                k = clave(exp, tau, P)
                cota = horaria(out, exp, P, args.rehacer)
                run = out["corridas"].setdefault(k, {"exportacion": exp, "tau_h": tau, "P_MW": P, "combinaciones": {}})
                if args.rehacer:
                    run["combinaciones"] = {}
                todos = casos(exp, P, pv_base, cota)
                pendientes = [(b, pv) for b, pv in todos if _k(b, pv) not in run["combinaciones"]]
                t0 = time.time()
                if pendientes:
                    print(f"\n[{k}] {len(pendientes)} combinaciones (BESS, PV) ({WORKERS} en paralelo)...", flush=True)
                    with ctx.Pool(WORKERS) as pool:
                        for kk, c in pool.imap_unordered(_resolver_combo,
                                                         [(exp, tau, P, b, pv, pv_base) for b, pv in pendientes]):
                            run["combinaciones"][kk] = c
                            guardar(out)
                validas = {kk: c for kk, c in run["combinaciones"].items() if c.get("solucion") and c["certificado_AC"]}
                if not validas:
                    print(f"[{k}] ninguna combinación válida", flush=True)
                    malos.append(k)
                    continue
                mejor = max(validas, key=lambda kk: validas[kk]["HC_kW"])
                run.update(mejor_combinacion=mejor, mejor=validas[mejor],
                           cota_superior_kW=cota["HC_cota_kW"],
                           rango_pct=100.0 * (cota["HC_cota_kW"] / validas[mejor]["HC_kW"] - 1.0),
                           combinaciones_sin_cerrar=sum(1 for c in run["combinaciones"].values()
                                                        if c.get("solucion") and c["mip_gap"] > 1e-4),
                           tiempo_enumeracion_s=run.get("tiempo_enumeracion_s", 0.0) + time.time() - t0)
                print(_linea(f"{k} mejor {mejor}", validas[mejor])
                      + f" | cota superior {cota['HC_cota_kW']:.0f} kW (rango {run['rango_pct']:.1f} %)", flush=True)
                if "archivo" not in run or args.rehacer or run.get("archivo_de") != mejor:
                    b = [int(j) for j in mejor.split("|")[0][2:].split("-")]
                    pv = [int(j) for j in mejor.split("|")[1][3:].split("-")]
                    cfg = _cfg_combo(exp, tau, P, b, pv, TL_COMBO)
                    r = resolver_24h(cfg, warm=_warm({j: p for j, p in validas[mejor]["sitios_pv_kW"].items()}))
                    run["archivo"] = _guardar_completo(r, cfg, f"p1_{exp}_tau{tau:g}_P{P:g}".replace(".", "p"))
                    run["archivo_de"] = mejor
                    run["mejor_completo"] = resumen(r, r["ac"])
                    guardar(out)
                if not run["mejor"]["certificado_AC"] or run["mejor"]["viola_limites_AC"]:
                    malos.append(k)

    print(f"\nGuardado: {os.path.relpath(RESULTS_JSON, BASE_DIR)}")
    print("Todas las configuraciones tienen una solución certificada en AC." if not malos
          else f"OJO: configuraciones con problemas: {malos}")
    return 0        # los problemas se avisan arriba; código != 0 solo si el script falla


if __name__ == "__main__":
    sys.exit(main())
