"""
experimentos/pregunta2_24h.py
=============================
Pregunta de investigación 2 en el modelo de 24 h: ¿qué efecto tiene la generación concentrada
frente a la distribuida?

Repite experimentos/pregunta2_concentrado_distribuido.py (que usa la carga base de la Tabla 1 de
[4]) con los perfiles de 24 h de julio: carga CEN por tipo de cliente y PV de Calama, sin BESS,
modelo exacto, max sum P^PV, sin vertimiento. Se cambia cuánto se puede concentrar el PV:

    A. Número de sitios:  n_pv_max en {1, 2, 3, 4, 32}  (32 = sin límite). Si un n ya alcanza la
                          cota superior del caso sin límite de sitios, los n mayores tienen ese
                          mismo HC (monotonía).
    B. Tope por sitio:    p_pv_max en {0.5, 1, 2, 4, 20} MW con n_pv_max = 32.
    C. Uniforme:          la misma capacidad en las 32 barras.

Se corre con el límite de exportación de 4.6 MW (decisión del equipo) y sin él. Cada solución se
valida con un flujo AC de pandapower en las 24 horas (flujo_ac_24h de la pregunta 1).

Con muchas barras candidatas Gurobi no siempre cierra el gap en el tope de tiempo (sin límite de
exportación, el caso sin límite de sitios queda peor que el de 2 sitios). Por eso:
    * cada caso intenta partir (MIP start) de la mejor solución factible ya encontrada que cumpla
      sus restricciones; Gurobi no siempre logra completarla;
    * al final se consolida: toda solución factible de un caso lo es también de cualquier caso menos
      restrictivo (más sitios o tope mayor), así que HC_mejor_kW es la mejor de ellas, y
      cota_mejor_kW = min(su cota, la cota del caso sin límite de sitios). El HC óptimo de cada
      caso queda en [HC_mejor_kW, cota_mejor_kW].
    python experimentos/pregunta2_24h.py --solo-consolidar   rehace la consolidación y la figura

Uso (desde cualquier carpeta):
    python experimentos/pregunta2_24h.py [--mes 7] [--exportacion con,sin] [--time-limit 300]
Escribe results/pregunta2_24h.json (después de cada caso) y la figura
results/figures/pregunta2/hc_concentrado_distribuido_24h.{png,pdf}.
"""
import argparse
import json
import os
import sys
import time

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

# OJO: NO usar rutas absolutas (p.ej. r"C:\Users\..." o "/Users/..."): solo funcionan en un PC.
# Se resuelve la raíz del proyecto relativa a este archivo (<raíz>/<carpeta>/este_script.py).
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # raíz del proyecto
sys.path.insert(0, BASE_DIR)

from experimentos.pregunta1_bess_cotas import LIM, _hc_kw, cfg_base, flujo_ac_24h  # noqa: E402
from modelo.misocp_hc_bess import build_model, extract_results, load_inputs  # noqa: E402

RESULTS_JSON = os.path.join(BASE_DIR, "results", "pregunta2_24h.json")
FIG_DIR = os.path.join(BASE_DIR, "results", "figures", "pregunta2")

N_SITIOS = [1, 2, 3, 4, 32]
TOPES_MW = [0.5, 1.0, 2.0, 4.0, 20.0]
EXPORTACION = {"con": ("con_limite", -0.46), "sin": ("sin_limite", None)}
THREADS = int(os.environ.get("HC_THREADS", "0")) or None    # hilos de Gurobi (None = todos)
TOL_IGUAL = 1e-4
TOL_ACTIVO = {"export_kW": 1.0, "Vmax_pu": 1e-4, "Imax_A": 0.5}


def resolver(mes, p_s_ref, t_lim, uniforme=False, inicio=None, **kw) -> dict:
    """inicio: sitios_kW de una solución factible conocida, como MIP start."""
    cfg = cfg_base(mes, p_s_ref_pu=p_s_ref, n_bess_max=0, bess_candidates=[], mip_gap=1e-4,
                   time_limit=t_lim, threads=THREADS, **kw)
    net, alpha = load_inputs(cfg)
    m, X = build_model(net, alpha, cfg)
    if uniforme:
        G = X["G_pv"]
        for j in G:
            X["w"][j].LB = 1.0
        for j in G[1:]:
            m.addConstr(X["Ppv_cap"][j] == X["Ppv_cap"][G[0]], name=f"uniforme[{j}]")
    if inicio:
        for j in X["G_pv"]:
            X["w"][j].Start = 1.0 if j in inicio else 0.0
            X["Ppv_cap"][j].Start = inicio.get(j, 0.0) / 1000.0 / cfg.s_base_mva
    m.optimize()
    r = extract_results(m, X, net, cfg)
    s = r["summary"]
    if not s.get("solution"):
        return {"status": int(s["status"]), "HC_kW": None, "sin_solucion": True}
    r.update(config=cfg)
    sitios = {int(b): p * 1000.0 for b, p in zip(r["pv_sites"]["bus"], r["pv_sites"]["P_cap_MW"])
              if p * 1000.0 >= 1.0}
    ac = flujo_ac_24h(r)
    activos = []
    if p_s_ref is not None and ac["export_kW"] >= LIM["export_kW"] - TOL_ACTIVO["export_kW"]:
        activos.append("exportación")
    if ac["Vmax_pu"] >= LIM["Vmax_pu"] - TOL_ACTIVO["Vmax_pu"]:
        activos.append("V_max")
    if ac["Imax_A"] >= LIM["Imax_A"] - TOL_ACTIVO["Imax_A"]:
        activos.append("I_max")
    viola = (ac["Vmax_pu"] > LIM["Vmax_pu"] + 1e-4 or ac["Vmin_pu"] < LIM["Vmin_pu"] - 1e-4
             or ac["Imax_A"] > LIM["Imax_A"] + 0.5 or ac["max_dV_modelo"] > 1e-4
             or (p_s_ref is not None and ac["export_kW"] > LIM["export_kW"] + 1.0))
    return {"HC_kW": s["hosting_capacity_PV_MW"] * 1000.0, "cota_HC_kW": _hc_kw(m.ObjBound, alpha, cfg),
            "n_sitios": len(sitios), "sitios_kW": sitios,
            "status": int(s["status"]), "mip_gap": float(s["mip_gap"]), "tiempo_s": float(s["runtime_s"]),
            "brecha_rel": float(s["conic_gap_rel"]), "perdidas_MWh": s["losses_MWh"],
            "limites_activos": activos, "viola_limites_AC": bool(viola), "ac": ac}


def _imprimir(nombre, r):
    if r.get("HC_kW") is None:
        print(f"  {nombre:<22} sin solución (status {r['status']})", flush=True)
        return
    top = sorted(r["sitios_kW"].items(), key=lambda kv: -kv[1])[:3]
    print(f"  {nombre:<22} HC = {r['HC_kW']:8.1f} kW | {r['n_sitios']:>2} sitios "
          f"(mayores: {', '.join(f'{j}: {p:.0f}' for j, p in top)}) | "
          f"activos: {', '.join(r['limites_activos']) or '-'} | gap {r['mip_gap']:.0e} "
          f"(cota {r.get('cota_HC_kW', float('nan')):.0f}) | {r['tiempo_s']:.0f} s"
          + ("  (certificado por monotonía)" if r.get("certificado_por")
             else "" if r["status"] == 2 else "  (tope de tiempo)")
          + ("  ** VIOLA LÍMITES EN AC **" if r["viola_limites_AC"] else ""), flush=True)


def guardar(res):
    os.makedirs(os.path.dirname(RESULTS_JSON), exist_ok=True)
    with open(RESULTS_JSON, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=2, ensure_ascii=False, default=float)


def consolidar(b: dict):
    """Toda solución factible de un caso lo es de cualquier caso menos restrictivo (ver docstring)."""
    casos = [(b["n_sitios"][k], f"n_pv_max = {k}", int(k), None) for k in b["n_sitios"]]
    casos += [(b["tope_MW"][k], f"tope {k} MW", 32, float(k) * 1000.0) for k in b["tope_MW"]]
    sols = [(nom, r) for r, nom, _, _ in casos + [(b["uniforme"], "uniforme", 32, None)]
            if r.get("HC_kW") and not r["viola_limites_AC"]]
    cota_libre = b["n_sitios"]["32"].get("cota_HC_kW", float("inf"))
    for r, nombre, n, tope in casos:
        ok = [(nom, x) for nom, x in sols if len(x["sitios_kW"]) <= n
              and (tope is None or max(x["sitios_kW"].values()) <= tope + 1.0)]
        nom, mejor = max(ok, key=lambda t: t[1]["HC_kW"])
        r["HC_mejor_kW"] = mejor["HC_kW"]
        r["HC_mejor_fuente"] = nom
        r["cota_mejor_kW"] = min(r.get("cota_HC_kW") or float("inf"), cota_libre)
        print(f"  {nombre:<16} HC óptimo en [{r['HC_mejor_kW']:8.1f}, {r['cota_mejor_kW']:8.1f}] kW"
              f" (ancho {r['cota_mejor_kW'] / r['HC_mejor_kW'] - 1:.2%}; mejor solución: {nom})", flush=True)
    b["uniforme"]["HC_mejor_kW"] = b["uniforme"]["HC_kW"]


def graficar(res):
    os.makedirs(FIG_DIR, exist_ok=True)
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4.2), sharey=True)
    estilos = {"con_limite": ("#14213D", "o", "Exportación ≤ 4.6 MW"),
               "sin_limite": ("#C8641A", "s", "Sin límite de exportación")}
    for tag, (color, mk, etiqueta) in estilos.items():
        b = res.get(tag)
        if not b or "uniforme" not in b:
            continue
        hc = lambda r: (r.get("HC_mejor_kW") or r.get("HC_kW") or float("nan")) / 1000  # noqa: E731
        a1.plot(N_SITIOS, [hc(b["n_sitios"][str(n)]) for n in N_SITIOS], marker=mk, color=color, label=etiqueta)
        a2.plot(TOPES_MW, [hc(b["tope_MW"][str(t)]) for t in TOPES_MW], marker=mk, color=color, label=etiqueta)
        if b["uniforme"].get("HC_kW"):
            for ax in (a1, a2):
                ax.axhline(b["uniforme"]["HC_kW"] / 1000, color=color, ls="--", lw=1)
    a1.set_xscale("log", base=2)
    a1.set_xticks(N_SITIOS, [str(n) if n < 32 else "sin límite" for n in N_SITIOS])
    a1.set_xlabel("Número máximo de barras con PV")
    a1.set_ylabel("Hosting capacity [MW]")
    a1.set_title("A. Concentración por número de sitios")
    a2.set_xscale("log")
    a2.set_xticks(TOPES_MW, [f"{t:g}" for t in TOPES_MW])
    a2.set_xlabel("Tope de capacidad por barra [MW]")
    a2.set_title("B. Concentración por tope por sitio")
    for ax in (a1, a2):
        ax.grid(alpha=0.3)
    a1.legend(loc="lower right", fontsize=9)
    fig.text(0.5, -0.02, f"Líneas punteadas: PV uniforme en las 32 barras. Modelo exacto de 24 h, mes "
             f"{res['mes']}, sin BESS.", ha="center", fontsize=8.5, color="#4A5568")
    fig.tight_layout()
    for ext in ("png", "pdf"):
        fig.savefig(os.path.join(FIG_DIR, f"hc_concentrado_distribuido_24h.{ext}"), dpi=200,
                    bbox_inches="tight")
    plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mes", type=int, default=7)
    ap.add_argument("--exportacion", default="con,sin", help="con, sin o con,sin")
    ap.add_argument("--time-limit", type=float, default=300)
    ap.add_argument("--solo-consolidar", action="store_true", help="solo consolida el JSON y rehace la figura")
    a = ap.parse_args()
    if a.solo_consolidar:
        with open(RESULTS_JSON, encoding="utf-8") as f:
            res = json.load(f)
        for tag in ("con_limite", "sin_limite"):
            if tag in res:
                print(f"\n=== Exportación {tag.replace('_', ' ')}: consolidado ===")
                consolidar(res[tag])
        guardar(res)
        graficar(res)
        return 0
    t0 = time.time()
    print("=" * 78)
    print(f"PREGUNTA 2 EN 24 h: HC concentrado vs distribuido (mes {a.mes}, sin BESS, modelo exacto)")
    print("=" * 78)
    res = {"descripcion": "Pregunta 2 en el modelo de 24 h, sin BESS", "mes": a.mes, "limites": LIM}
    if os.path.exists(RESULTS_JSON):
        with open(RESULTS_JSON, encoding="utf-8") as f:
            prev = json.load(f)
        if prev.get("mes") == a.mes:
            res.update({k: v for k, v in prev.items() if k in ("con_limite", "sin_limite")})
    for clave in a.exportacion.split(","):
        tag, ps = EXPORTACION[clave.strip()]
        print(f"\n=== Exportación {tag.replace('_', ' ')} ===", flush=True)
        b = res[tag] = {"n_sitios": {}, "tope_MW": {}}
        conocidas = []                                   # soluciones factibles (sitios_kW, HC)

        def mejor_inicio(n_max=32, tope_kw=None):
            ok = [(hc, st) for st, hc in conocidas if len(st) <= n_max
                  and (tope_kw is None or max(st.values()) <= tope_kw + 1e-6)]
            return max(ok, key=lambda x: x[0])[1] if ok else None

        def correr(nombre, **kw):
            r = resolver(a.mes, ps, a.time_limit, **kw)
            if r.get("HC_kW") is not None and not r["viola_limites_AC"]:
                conocidas.append(({int(k): v for k, v in r["sitios_kW"].items()}, r["HC_kW"]))
            _imprimir(nombre, r)
            return r

        b["uniforme"] = correr("uniforme (32 barras)", uniforme=True)
        guardar(res)
        # Primero 1 y 2 sitios (rápidos), luego sin límite de sitios partiendo de la mejor solución.
        for n in [n for n in N_SITIOS if n <= 2]:
            b["n_sitios"][str(n)] = correr(f"n_pv_max = {n:>2}", n_pv_max=n, inicio=mejor_inicio(n))
            guardar(res)
        libre = correr("n_pv_max = 32", n_pv_max=32, inicio=mejor_inicio())
        b["n_sitios"]["32"] = libre
        for n in [n for n in N_SITIOS if 2 < n < 32]:
            prev = [m for m in N_SITIOS if m < n and b["n_sitios"][str(m)].get("status") == 2
                    and b["n_sitios"][str(m)]["HC_kW"] >= libre["cota_HC_kW"] * (1 - TOL_IGUAL)]
            if prev:
                r = dict(b["n_sitios"][str(prev[0])], tiempo_s=0.0,
                         certificado_por=f"monotonía: HC({prev[0]}) = cota de HC(sin límite de sitios)")
                _imprimir(f"n_pv_max = {n:>2}", r)
            else:
                r = correr(f"n_pv_max = {n:>2}", n_pv_max=n, inicio=mejor_inicio(n))
            b["n_sitios"][str(n)] = r
            guardar(res)
        for tope in TOPES_MW:
            r = libre if tope == 20.0 else correr(f"tope {tope:>5} MW", p_pv_max_mw=tope,
                                                  inicio=mejor_inicio(tope_kw=tope * 1000.0))
            b["tope_MW"][str(tope)] = r
            guardar(res)
    for tag in ("con_limite", "sin_limite"):
        if tag in res:
            print(f"\n=== Exportación {tag.replace('_', ' ')}: consolidado ===")
            consolidar(res[tag])
    guardar(res)
    graficar(res)
    malos = [f"{tag}/{g}/{k}" for tag in ("con_limite", "sin_limite") if tag in res
             for g in ("n_sitios", "tope_MW") for k, r in res[tag][g].items()
             if r.get("HC_kW") is not None and r["viola_limites_AC"]]
    print(f"\nGuardado: {os.path.relpath(RESULTS_JSON, BASE_DIR)} y figura en "
          f"{os.path.relpath(FIG_DIR, BASE_DIR)} ({(time.time() - t0) / 60:.1f} min)")
    print("Todas las soluciones respetan los límites en el flujo AC (ver los rangos consolidados)." if not malos
          else f"OJO: soluciones con violaciones en el flujo AC: {malos}")
    return 0 if not malos else 1


if __name__ == "__main__":
    sys.exit(main())
