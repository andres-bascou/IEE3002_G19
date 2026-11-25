"""
experimentos/pregunta2_concentrado_distribuido.py
=================================================
Pregunta de investigación 2: ¿qué efecto tiene la generación concentrada frente a la distribuida?

Se usa la configuración de la Tabla 1 de [4] (modelo.misocp_hc_bess.config_tabla1, escenario 1:
carga base, T = 1, sin BESS, todas las barras candidatas, modelo exacto, max sum P^PV) y se
cambia cuánto se puede concentrar el PV:

    A. Número de sitios:     n_pv_max en {1, 2, 3, 4, 6, 8, 12, 32}   (32 = sin límite)
                             Si un n' ya alcanza el HC sin límite de sitios, los n > n' tienen ese
                             mismo HC (monotonía) y no se resuelven: con 6-12 sitios el
                             branch-and-bound no cierra el gap en minutos.
    B. Tope por sitio:       p_pv_max en {0.25, 0.5, 1, 2, 4, 20} MW  con n_pv_max = 32
                             (un tope bajo obliga a repartir el PV en muchas barras)
    C. Uniforme:             la misma capacidad en las 32 barras (PV distribuido de referencia)

Cada barrido se resuelve con y sin el límite de exportación de 4.6 MW de [4], porque ese
límite cambia qué restricción determina el HC. Cada solución se valida con un flujo AC de
pandapower (la misma función de la Etapa 2).

Uso (desde cualquier carpeta):
    python experimentos/pregunta2_concentrado_distribuido.py
Escribe results/pregunta2_concentrado_distribuido.json y la figura
results/figures/pregunta2/hc_concentrado_distribuido.{png,pdf}.
"""
import json
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

# OJO: NO usar rutas absolutas (p.ej. r"C:\Users\..." o "/Users/..."): solo funcionan en un PC.
# Se resuelve la raíz del proyecto relativa a este archivo (<raíz>/<carpeta>/este_script.py).
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # raíz del proyecto
sys.path.insert(0, BASE_DIR)

from modelo.misocp_hc_bess import (build_model, config_tabla1,  # noqa: E402
                                   extract_results, load_inputs)
from verificacion.etapa2_tabla1 import LIMITES, flujo_ac  # noqa: E402

RESULTS_JSON = os.path.join(BASE_DIR, "results", "pregunta2_concentrado_distribuido.json")
FIG_DIR = os.path.join(BASE_DIR, "results", "figures", "pregunta2")

N_SITIOS = [1, 2, 3, 4, 6, 8, 12, 32]
TOPES_MW = [0.25, 0.5, 1.0, 2.0, 4.0, 20.0]
EXPORTACION = {"con_limite": -0.46, "sin_limite": None}     # P_S >= -4.6 MW, o sin límite
THREADS = int(os.environ.get("HC_THREADS", "0")) or None    # hilos de Gurobi (None = todos)
TIME_LIMIT = 120                                            # [s] por caso; si se alcanza, se reporta el gap
TOL_IGUAL = 1e-4                                            # HC iguales dentro del MIP gap exigido

# Holguras para decir que un límite está activo en el flujo AC
TOL_ACTIVO = {"export_kW": 1.0, "Vmax_pu": 1e-4, "Imax_A": 0.5}


def resolver(p_s_ref, uniforme=False, **kw) -> dict:
    kw.setdefault("threads", THREADS)
    kw.setdefault("time_limit", TIME_LIMIT)
    cfg = config_tabla1(1, p_s_ref_pu=p_s_ref, **kw)
    net, alpha = load_inputs(cfg)
    m, X = build_model(net, alpha, cfg)
    if uniforme:
        # PV en todas las barras candidatas, todas con la misma capacidad
        G = X["G_pv"]
        for j in G:
            X["w"][j].LB = 1.0
        for j in G[1:]:
            m.addConstr(X["Ppv_cap"][j] == X["Ppv_cap"][G[0]], name=f"uniforme[{j}]")
    m.optimize()
    r = extract_results(m, X, net, cfg)
    s = r["summary"]
    if not s.get("solution"):
        raise RuntimeError(f"Sin solución (status {s['status']}) para {kw}, uniforme={uniforme}.")

    sitios = {int(b): p * 1000.0 for b, p in zip(r["pv_sites"]["bus"], r["pv_sites"]["P_cap_MW"])
              if p * 1000.0 >= 1.0}
    ac = flujo_ac(sitios)
    ac.pop("V")
    activos = []
    if p_s_ref is not None and ac["export_kW"] >= LIMITES["export_kW"] - TOL_ACTIVO["export_kW"]:
        activos.append("exportación")
    if ac["Vmax_pu"] >= LIMITES["Vmax_pu"] - TOL_ACTIVO["Vmax_pu"]:
        activos.append("V_max")
    if ac["Imax_A"] >= LIMITES["Imax_A"] - TOL_ACTIVO["Imax_A"]:
        activos.append("I_max")
    viola = (ac["Vmax_pu"] > LIMITES["Vmax_pu"] + 1e-4 or ac["Vmin_pu"] < LIMITES["Vmin_pu"] - 1e-4
             or ac["Imax_A"] > LIMITES["Imax_A"] + 0.5
             or (p_s_ref is not None and ac["export_kW"] > LIMITES["export_kW"] + 1.0))
    return {"HC_kW": s["hosting_capacity_PV_MW"] * 1000.0, "n_sitios": len(sitios), "sitios_kW": sitios,
            "status": int(s["status"]), "mip_gap": float(s["mip_gap"]), "tiempo_s": float(s["runtime_s"]),
            "brecha_rel": float(s["conic_gap_rel"]), "perdidas_kW": s["losses_MWh"] * 1000.0,
            "limites_activos": activos, "viola_limites_AC": bool(viola), "ac": ac}


def ejecutar() -> dict:
    out = {"descripcion": "Pregunta 2: HC concentrado vs distribuido (Tabla 1 de [4], escenario 1)",
           "limites": LIMITES}
    for tag, ps in EXPORTACION.items():
        print(f"\n=== Exportación {tag.replace('_', ' ')} ===", flush=True)
        bloque = {"n_sitios": {}, "tope_MW": {}}
        # Monotonía: HC(n) es no decreciente en n y HC(n) <= HC(sin límite de sitios). Si un n' ya
        # alcanza HC(sin límite), todo n >= n' tiene ese mismo HC óptimo, sin necesidad de resolverlo
        # (con 6-12 sitios el branch-and-bound no cierra el gap en minutos, aunque la cota sea conocida).
        libre = resolver(ps, n_pv_max=max(N_SITIOS))
        alcanzado = None
        for n in N_SITIOS:
            if n == max(N_SITIOS):
                r = libre
            elif alcanzado is not None:
                r = dict(bloque["n_sitios"][str(alcanzado)], certificado_por=(
                    f"monotonía: HC({alcanzado}) = HC(sin límite de sitios)"), tiempo_s=0.0)
            else:
                r = resolver(ps, n_pv_max=n)
                if r["status"] == 2 and r["HC_kW"] >= libre["HC_kW"] * (1 - TOL_IGUAL):
                    alcanzado = n
            bloque["n_sitios"][str(n)] = r
            _imprimir(f"n_pv_max = {n:>2}", r)
        for tope in TOPES_MW:
            r = resolver(ps, p_pv_max_mw=tope)
            bloque["tope_MW"][str(tope)] = r
            _imprimir(f"tope {tope:>5} MW", r)
        bloque["uniforme"] = resolver(ps, uniforme=True)
        _imprimir("uniforme (32 barras)", bloque["uniforme"])
        out[tag] = bloque
    return out


def _imprimir(nombre: str, r: dict):
    top = sorted(r["sitios_kW"].items(), key=lambda kv: -kv[1])[:3]
    print(f"  {nombre:<22} HC = {r['HC_kW']:8.1f} kW | {r['n_sitios']:>2} sitios "
          f"(mayores: {', '.join(f'{j}: {p:.0f}' for j, p in top)}) | "
          f"activos: {', '.join(r['limites_activos']) or '-'} | pérdidas {r['perdidas_kW']:.0f} kW | "
          f"gap {r['mip_gap']:.0e} | {r['tiempo_s']:.1f} s"
          + ("  (certificado por monotonía)" if r.get("certificado_por")
             else "" if r["status"] == 2 else "  (tope de tiempo)")
          + ("  ** VIOLA LÍMITES EN AC **" if r["viola_limites_AC"] else ""), flush=True)


def graficar(res: dict):
    os.makedirs(FIG_DIR, exist_ok=True)
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4.2), sharey=True)
    estilos = {"con_limite": ("#14213D", "o", "Exportación ≤ 4.6 MW"),
               "sin_limite": ("#C8641A", "s", "Sin límite de exportación")}
    for tag, (color, mk, etiqueta) in estilos.items():
        b = res[tag]
        a1.plot(N_SITIOS, [b["n_sitios"][str(n)]["HC_kW"] / 1000 for n in N_SITIOS],
                marker=mk, color=color, label=etiqueta)
        a2.plot(TOPES_MW, [b["tope_MW"][str(t)]["HC_kW"] / 1000 for t in TOPES_MW],
                marker=mk, color=color, label=etiqueta)
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
    fig.text(0.5, -0.02, "Líneas punteadas: PV uniforme en las 32 barras. Tabla 1 de [4], escenario 1 "
             "(carga base, sin BESS), modelo exacto.", ha="center", fontsize=8.5, color="#4A5568")
    fig.tight_layout()
    for ext in ("png", "pdf"):
        fig.savefig(os.path.join(FIG_DIR, f"hc_concentrado_distribuido.{ext}"), dpi=200, bbox_inches="tight")
    plt.close(fig)


def main() -> int:
    print("=" * 78)
    print("PREGUNTA 2: HC concentrado vs distribuido (Tabla 1 de [4], escenario 1, modelo exacto)")
    print("=" * 78)
    res = ejecutar()
    os.makedirs(os.path.dirname(RESULTS_JSON), exist_ok=True)
    with open(RESULTS_JSON, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=2, ensure_ascii=False, default=float)
    graficar(res)
    malos = [k for tag in EXPORTACION for grupo in ("n_sitios", "tope_MW")
             for k, r in res[tag][grupo].items() if r["viola_limites_AC"] or r["status"] != 2]
    print(f"\nGuardado: {os.path.relpath(RESULTS_JSON, BASE_DIR)} y "
          f"{os.path.relpath(FIG_DIR, BASE_DIR)}/hc_concentrado_distribuido.{{png,pdf}}")
    print("Todas las soluciones son óptimas y respetan los límites en el flujo AC." if not malos
          else f"OJO: soluciones no óptimas o con violaciones: {malos}")
    return 0 if not malos else 1


if __name__ == "__main__":
    sys.exit(main())
