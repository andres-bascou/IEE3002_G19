"""
experimentos/pregunta3_sensibilidad.py
======================================
Pregunta de investigación 3: ¿qué tan sensible es el HC a los parámetros del modelo?

Todo con el modelo exacto, max sum P^PV y sin vertimiento. Tres bloques (--bloques):

    red   Límites de la red sobre la Tabla 1 de [4] (escenario 1: carga base, T = 1, sin BESS),
          cambiando un parámetro a la vez desde el caso base (exportación 4.6 MW, V_max 1.10 p.u.,
          I_max 300 A):
              exportación máxima: 0, 2.3, 4.6, 6.9, 9.2 MW y sin límite
              V_max:              1.05, 1.06, 1.08, 1.10 p.u.   (con y sin límite de exportación)
              I_max:              200, 250, 300, 400 A          (con y sin límite de exportación)
          V_max e I_max vienen en data/grid/*.csv, así que se cambian en la red ya cargada.
    mes   Perfil de PV de cada mes (alpha_t de Calama) en el modelo de 24 h sin BESS, con
          exportación <= 4.6 MW. La demanda es siempre la del CEN (31 de julio).
    bess  Parámetros de la BESS en el modelo de 24 h, julio, 2 BESS de 0.5 MW en 32 y 33, PV en 18
          y 22 (la cota inferior de la pregunta 1, que es una solución factible). Se cambia uno a la
          vez desde el caso base (tau = 2 h, eta = 0.95, SoC 10-90 %): tau 1 y 4 h, eta 0.90 y 1.0,
          SoC 20-80 % y 0-100 %. c_deg no se prueba: con el objetivo max sum P^PV no aparece en el
          modelo, así que no cambia el HC. Cada caso tiene un tope de tiempo (--t-bess), así que los
          valores son cotas inferiores con el gap que se reporta.

Cada solución se valida con un flujo AC de pandapower, contra los límites de su propio caso.

Uso (desde cualquier carpeta):
    python experimentos/pregunta3_sensibilidad.py [--bloques red,mes,bess] [--t-bess 300]
    python experimentos/pregunta3_sensibilidad.py --solo-grafico
Escribe results/pregunta3_sensibilidad.json (conserva los bloques que no se vuelven a correr) y la
figura results/figures/pregunta3/sensibilidad.{png,pdf}.
"""
import argparse
import json
import os
import sys
import time

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

# OJO: NO usar rutas absolutas (p.ej. r"C:\Users\..." o "/Users/..."): solo funcionan en un PC.
# Se resuelve la raíz del proyecto relativa a este archivo (<raíz>/<carpeta>/este_script.py).
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # raíz del proyecto
sys.path.insert(0, BASE_DIR)

from experimentos.pregunta1_bess_cotas import cfg_base, flujo_ac_24h  # noqa: E402
from modelo.misocp_hc_bess import build_model, config_tabla1, extract_results, load_inputs  # noqa: E402
from verificacion.etapa2_tabla1 import flujo_ac  # noqa: E402

RESULTS_JSON = os.path.join(BASE_DIR, "results", "pregunta3_sensibilidad.json")
FIG_DIR = os.path.join(BASE_DIR, "results", "figures", "pregunta3")
THREADS = int(os.environ.get("HC_THREADS", "0")) or None

EXPORT_MW = [0.0, 2.3, 4.6, 6.9, 9.2, None]
VMAX = [1.05, 1.06, 1.08, 1.10]
IMAX_A = [200.0, 250.0, 300.0, 400.0]
BESS_BASE = dict(tau=2.0, eta=0.95, soc=(0.10, 0.90))
BESS_VARIANTES = {"tau_1h": dict(tau=1.0), "tau_4h": dict(tau=4.0), "eta_0.90": dict(eta=0.90),
                  "eta_1.00": dict(eta=1.0), "soc_20-80": dict(soc=(0.20, 0.80)),
                  "soc_0-100": dict(soc=(0.0, 1.0))}


def resolver(cfg, vmax=None, imax_a=None) -> dict:
    net, alpha = load_inputs(cfg)
    if vmax is not None:                      # todas las barras menos la slack (V = 1)
        net.v_max.update({j: vmax for j, v in net.v_max.items() if v > 1.0})
    if imax_a is not None:
        i_base_ka = cfg.s_base_mva / (np.sqrt(3.0) * cfg.v_base_kv)
        net.i_max.update({j: imax_a / 1000.0 / i_base_ka for j in net.i_max})
    m, X = build_model(net, alpha, cfg)
    m.optimize()
    r = extract_results(m, X, net, cfg)
    s = r["summary"]
    if not s.get("solution"):
        return {"status": int(s["status"]), "HC_kW": None}
    r.update(config=cfg)
    sitios = {int(b): p * 1000.0 for b, p in zip(r["pv_sites"]["bus"], r["pv_sites"]["P_cap_MW"])
              if p * 1000.0 >= 1.0}
    if cfg.T == 1:
        ac = flujo_ac(sitios)
        V = ac.pop("V")
        ac["max_dV_modelo"] = max(abs(float(r["voltages"].loc[1, j]) - V[j]) for j in V)
    else:
        ac = flujo_ac_24h(r)
        ac.pop("cumple", None)
    lim_v = vmax or 1.10
    lim_i = imax_a or 300.0
    exp_kw = -cfg.p_s_ref_pu * cfg.s_base_mva * 1000.0 if cfg.p_s_ref_pu is not None else None
    activos = [k for k, c in (("exportación", exp_kw is not None and ac["export_kW"] >= exp_kw - 1.0),
                              ("V_max", ac["Vmax_pu"] >= lim_v - 1e-4), ("I_max", ac["Imax_A"] >= lim_i - 0.5)) if c]
    viola = (ac["Vmax_pu"] > lim_v + 1e-4 or ac["Vmin_pu"] < 0.90 - 1e-4 or ac["Imax_A"] > lim_i + 0.5
             or ac["max_dV_modelo"] > 1e-4 or (exp_kw is not None and ac["export_kW"] > exp_kw + 1.0))
    out = {"HC_kW": s["hosting_capacity_PV_MW"] * 1000.0, "sitios_kW": sitios, "status": int(s["status"]),
           "mip_gap": float(s["mip_gap"]), "tiempo_s": float(s["runtime_s"]),
           "limites_activos": activos, "viola_limites_AC": bool(viola), "ac": ac}
    if len(r["bess_sites"]):
        out["bess_kW"] = {int(b): p * 1000.0 for b, p in zip(r["bess_sites"]["bus"], r["bess_sites"]["P_cap_MW"])}
    return out


def _imprimir(nombre, r):
    if r.get("HC_kW") is None:
        print(f"  {nombre:<28} sin solución (status {r['status']})", flush=True)
        return
    top = sorted(r["sitios_kW"].items(), key=lambda kv: -kv[1])[:3]
    print(f"  {nombre:<28} HC = {r['HC_kW']:8.1f} kW | PV {', '.join(f'{j}: {p:.0f}' for j, p in top)} | "
          f"activos: {', '.join(r['limites_activos']) or '-'} | gap {r['mip_gap']:.0e} | {r['tiempo_s']:.0f} s"
          + ("" if r["status"] == 2 else "  (tope de tiempo)")
          + ("  ** VIOLA LÍMITES EN AC **" if r["viola_limites_AC"] else ""), flush=True)


def bloque_red() -> dict:
    print("\n=== Límites de red (Tabla 1 de [4], escenario 1, carga base) ===", flush=True)
    out = {"exportacion_MW": {}, "Vmax_pu": {}, "Imax_A": {}}
    tab = lambda ps: config_tabla1(1, p_s_ref_pu=ps, threads=THREADS, time_limit=120)  # noqa: E731
    for e in EXPORT_MW:
        r = resolver(tab(-e / 10.0 if e is not None else None))
        out["exportacion_MW"]["sin_limite" if e is None else str(e)] = r
        _imprimir(f"exportación {'sin límite' if e is None else f'{e} MW'}", r)
    for tag, ps in (("con_limite", -0.46), ("sin_limite", None)):
        out["Vmax_pu"][tag], out["Imax_A"][tag] = {}, {}
        for vm in VMAX:
            r = resolver(tab(ps), vmax=vm)
            out["Vmax_pu"][tag][str(vm)] = r
            _imprimir(f"V_max {vm} ({tag.replace('_', ' ')})", r)
        for im in IMAX_A:
            r = resolver(tab(ps), imax_a=im)
            out["Imax_A"][tag][str(im)] = r
            _imprimir(f"I_max {im:.0f} A ({tag.replace('_', ' ')})", r)
    return out


def bloque_mes() -> dict:
    print("\n=== Perfil de PV por mes (24 h, sin BESS, exportación <= 4.6 MW) ===", flush=True)
    out = {}
    for mes in range(1, 13):
        cfg = cfg_base(mes, n_bess_max=0, bess_candidates=[], mip_gap=1e-4, threads=THREADS, time_limit=600)
        _, alpha = load_inputs(cfg)
        r = resolver(cfg)
        r.update(alpha_max=float(alpha.max()), hora_alpha_max=int(alpha.idxmax()))
        out[str(mes)] = r
        _imprimir(f"mes {mes:>2} (alpha máx {r['alpha_max']:.3f})", r)
    return out


def bloque_bess(t_lim: float) -> dict:
    print("\n=== Parámetros de la BESS (24 h, julio, 2 x 0.5 MW en 32 y 33, PV en 18 y 22) ===", flush=True)
    out = {}
    for nombre, cambio in {"base": {}, **BESS_VARIANTES}.items():
        p = {**BESS_BASE, **cambio}
        cfg = cfg_base(7, pv_candidates=[18, 22], bess_candidates=[32, 33], p_b_max_mw=0.5,
                       e_b_max_mwh=p["tau"] * 0.5, tau_min=p["tau"], tau_max=p["tau"],
                       eta_ch=p["eta"], eta_dis=p["eta"], kappa_min=p["soc"][0], kappa_max=p["soc"][1],
                       kappa_0=max(p["soc"][0], 0.10), threads=THREADS, time_limit=t_lim)
        r = resolver(cfg)
        r["parametros"] = {"tau_h": p["tau"], "eta": p["eta"], "soc_min": p["soc"][0], "soc_max": p["soc"][1]}
        out[nombre] = r
        _imprimir(nombre, r)
    return out


def graficar(res: dict):
    paneles = [b for b in ("red", "mes", "bess") if b in res]
    if not paneles:
        return
    n = 3 * ("red" in res) + ("mes" in res) + ("bess" in res)
    fig, axs = plt.subplots(1, n, figsize=(4.2 * n, 3.8))
    axs = list(np.atleast_1d(axs))
    col = {"con_limite": ("#14213D", "o", "Exportación ≤ 4.6 MW"), "sin_limite": ("#C8641A", "s", "Sin límite")}
    hc = lambda r: r["HC_kW"] / 1000 if r.get("HC_kW") else np.nan  # noqa: E731
    if "red" in res:
        red = res["red"]
        ax = axs.pop(0)
        xs = [k for k in red["exportacion_MW"] if k != "sin_limite"]
        ax.plot([float(x) for x in xs], [hc(red["exportacion_MW"][x]) for x in xs], marker="o", color="#14213D")
        ax.axhline(hc(red["exportacion_MW"]["sin_limite"]), color="#C8641A", ls="--", lw=1, label="Sin límite")
        ax.set(xlabel="Exportación máxima [MW]", ylabel="HC [MW]", title="A. Límite de exportación")
        ax.legend(fontsize=8)
        for clave, xlab, tit in (("Vmax_pu", "V_max [p.u.]", "B. Tensión máxima"),
                                 ("Imax_A", "I_max [A]", "C. Corriente máxima")):
            ax = axs.pop(0)
            for tag, (c, mk, lab) in col.items():
                d = red[clave].get(tag, {})
                ax.plot([float(x) for x in d], [hc(d[x]) for x in d], marker=mk, color=c, label=lab)
            ax.set(xlabel=xlab, title=tit)
            ax.legend(fontsize=8)
    if "mes" in res:
        ax = axs.pop(0)
        meses = sorted(res["mes"], key=int)
        ax.plot([int(m) for m in meses], [hc(res["mes"][m]) for m in meses], marker="o", color="#14213D")
        ax.set(xlabel="Mes", ylabel="HC [MW]", title="D. Perfil de PV por mes (24 h)")
        ax2 = ax.twinx()
        ax2.plot([int(m) for m in meses], [res["mes"][m].get("alpha_max", np.nan) for m in meses],
                 ls=":", color="#C8641A")
        ax2.set_ylabel("α máx (punteado)", color="#C8641A")
        ax.set_xticks(range(1, 13))
    if "bess" in res:
        ax = axs.pop(0)
        nombres = [k for k in res["bess"] if isinstance(res["bess"][k], dict) and "parametros" in res["bess"][k]]
        ax.barh(nombres, [hc(res["bess"][k]) for k in nombres], color="#14213D")
        base = hc(res["bess"]["base"]) if "base" in res["bess"] else None
        if base:
            ax.axvline(base, color="#C8641A", ls="--", lw=1)
        vals = [hc(res["bess"][k]) for k in nombres]
        ax.set_xlim(min(vals) * 0.99, max(vals) * 1.01)
        ax.set(xlabel="HC [MW] (cota inferior)", title="E. Parámetros de la BESS (2 × 0.5 MW)")
    for ax in fig.axes:
        ax.grid(alpha=0.3)
    fig.tight_layout()
    os.makedirs(FIG_DIR, exist_ok=True)
    for ext in ("png", "pdf"):
        fig.savefig(os.path.join(FIG_DIR, f"sensibilidad.{ext}"), dpi=200, bbox_inches="tight")
    plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bloques", default="red,mes,bess")
    ap.add_argument("--t-bess", type=float, default=300, help="tope de tiempo por caso del bloque bess [s]")
    ap.add_argument("--solo-grafico", action="store_true", help="solo rehace la figura desde el JSON")
    a = ap.parse_args()
    if a.solo_grafico:
        with open(RESULTS_JSON, encoding="utf-8") as f:
            graficar(json.load(f))
        return 0
    t0 = time.time()
    print("=" * 78)
    print("PREGUNTA 3: sensibilidad del HC a los parámetros (modelo exacto)")
    print("=" * 78)
    res = {"descripcion": "Pregunta 3: sensibilidad del HC (modelo exacto, max sum P^PV)"}
    if os.path.exists(RESULTS_JSON):
        with open(RESULTS_JSON, encoding="utf-8") as f:
            res.update(json.load(f))
    for b in a.bloques.split(","):
        b = b.strip()
        res[b] = {"red": bloque_red, "mes": bloque_mes, "bess": lambda: bloque_bess(a.t_bess)}[b]()
        if b == "bess":
            res[b]["t_lim_s"] = a.t_bess
        with open(RESULTS_JSON, "w", encoding="utf-8") as f:
            json.dump(res, f, indent=2, ensure_ascii=False, default=float)
    graficar(res)
    print(f"\nGuardado: {os.path.relpath(RESULTS_JSON, BASE_DIR)} y figura en "
          f"{os.path.relpath(FIG_DIR, BASE_DIR)} ({(time.time() - t0) / 60:.1f} min)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
