"""
experimentos/pregunta1_bess_cotas.py
====================================
Pregunta de investigación 1: ¿cuánto cambia el HC al agregar BESS?

El modelo exacto de 24 h con BESS (1600 binarias y 768 igualdades no convexas) no cierra el gap
en 10-20 min. En vez de resolverlo completo, se ACOTA su HC óptimo por los dos lados:

    Cota inferior: el mismo modelo exacto (con las binarias mu_ch / mu_dis originales), pero con
                   el PV solo en las barras que elige el caso sin BESS y el BESS solo en un par de
                   barras candidatas. Cada solución es factible para el problema completo, así que
                   la mejor es una cota inferior de su HC. Se resuelve en segundos o minutos.
    Cota superior (horaria): sin el estado de carga de la BESS, cada hora t es un problema de un solo
                   período (como la Tabla 1, segundos a minutos) con la BESS como inyección neta en
                   [-P, P]. Cualquier solución de 24 h, mirada solo en la hora t, es factible para ese
                   problema, así que HC* <= min_t HC_t. Se calcula en las horas de mayor irradiancia.
                   Ignora el límite de energía de la BESS, así que con baterías grandes queda holgada.
    Cota superior (mu relajadas, opcional con --cota-mu): el problema completo con mu_ch y mu_dis en
                   [0, 1]. También es válida, pero es más lenta (20 min) y resultó más débil que la
                   horaria en todos los tamaños: su solución carga y descarga a la vez para «gastar»
                   energía, y el solver no cierra su gap.

Si las dos cotas quedan cerca, el HC con BESS queda determinado sin resolver el problema completo.
La mejor solución de la cota inferior se valida con un flujo AC de pandapower hora por hora.
La cota superior se resuelve primero: las barras de BESS y de PV de la solución de la hora crítica se
agregan como un caso extra de la cota inferior, porque con baterías grandes el PV puede cambiar de barras.

Caso base: julio, T = 24 h, exportación <= 4.6 MW, topes de PV no activos (20 MW por barra,
hasta 32 barras), modelo exacto, max sum P^PV, sin vertimiento, BESS con tau = 2 h.

Uso (desde cualquier carpeta):
    python experimentos/pregunta1_bess_cotas.py                        # 2 x 50 kW (caso base)
    python experimentos/pregunta1_bess_cotas.py --tamanos 0.05,0.5,1   # barrido [MW por BESS]
    python experimentos/pregunta1_bess_cotas.py --tamanos 0.5 --solo-horaria   # agrega solo la cota horaria
Opciones: --mes, --pares "32,33;21,22", --t-inferior [s], --t-horaria [s], --cota-mu, --t-superior [s].
Escribe results/pregunta1_bess_cotas.json; conserva los tamaños ya calculados con el mismo mes y
la misma configuración, así que el barrido se puede correr por partes.
"""
import argparse
import dataclasses
import json
import os
import sys
import time

import numpy as np
import pandas as pd
import pandapower as pp
import pandapower.networks as pn
from gurobipy import GRB

# OJO: NO usar rutas absolutas (p.ej. r"C:\Users\..." o "/Users/..."): solo funcionan en un PC.
# Se resuelve la raíz del proyecto relativa a este archivo (<raíz>/<carpeta>/este_script.py).
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # raíz del proyecto
sys.path.insert(0, BASE_DIR)

from modelo.misocp_hc_bess import (HCConfig, build_model, extract_results,  # noqa: E402
                                   load_inputs, run_hc_bess)

RESULTS_JSON = os.path.join(BASE_DIR, "results", "pregunta1_bess_cotas.json")

P_S_REF_PU = -0.46            # exportación <= 4.6 MW  [4, Sec. 4.1]
TAU_H = 2.0                   # E = tau * P  (autonomía del caso base)
PARES_DEFECTO = [(32, 33), (21, 22), (17, 18), (18, 22)]
LIM = {"export_kW": 4600.0, "Vmin_pu": 0.90, "Vmax_pu": 1.10, "Imax_A": 300.0}


def cfg_base(mes: int, **kw) -> HCConfig:
    base = dict(month=mes, p_pv_max_mw=20.0, n_pv_max=32, mip_gap=1e-5, output_flag=0,
                p_s_ref_pu=P_S_REF_PU)
    base.update(kw)
    return HCConfig(**base)


def _hc_kw(obj_pu: float, alpha, cfg: HCConfig) -> float:
    """Sin vertimiento el objetivo es sum_t alpha_t * dt * sum_j P_cap_j, así que HC = obj / sum(alpha dt)."""
    return obj_pu / (float(np.sum(alpha)) * cfg.dt) * cfg.s_base_mva * 1000.0


def simultaneas(X, kw_tol: float = 0.1, S_kw: float = 1e4) -> int:
    return sum(1 for j in X["G_b"] for t in X["T"]
               if min(X["Pch"][j, t].X, X["Pdis"][j, t].X) * S_kw > kw_tol)


def flujo_ac_24h(res: dict) -> dict:
    """Flujo AC de pandapower en cada hora con la carga, el PV y el BESS de la solución."""
    net_m, cfg = res["network"], res["config"]
    S = cfg.s_base_mva                                           # p.u. -> MW
    pv = res["pv_ops"].set_index(["bus", "t"])["P_pv_MW"] if len(res["pv_ops"]) else None
    bo = res["bess_ops"].set_index(["bus", "t"]) if len(res["bess_ops"]) else None
    peor = {"export_kW": -np.inf, "Vmax_pu": -np.inf, "Vmin_pu": np.inf, "Imax_A": -np.inf,
            "max_dV_modelo": 0.0}
    for t in range(1, cfg.T + 1):
        net = pn.case33bw()
        net.line = net.line.iloc[:32].copy()                     # red radial, sin tie-lines
        for k, row in net.load.iterrows():
            j = int(row["bus"]) + 1
            net.load.at[k, "p_mw"] = net_m.PL[j, t] * S
            net.load.at[k, "q_mvar"] = net_m.QL[j, t] * S
        if pv is not None:
            for (j, tt), p in pv.items():
                if tt == t and p > 0:
                    pp.create_sgen(net, int(j) - 1, p_mw=float(p), q_mvar=0.0)
        if bo is not None:
            for (j, tt), row in bo.iterrows():
                if tt == t:
                    pp.create_load(net, int(j) - 1, p_mw=float(row["P_ch_MW"] - row["P_dis_MW"]), q_mvar=0.0)
        pp.runpp(net, numba=False, tolerance_mva=1e-9)
        vm = net.res_bus.vm_pu
        dV = max(abs(float(res["voltages"].at[t, j]) - float(vm.iloc[j - 1])) for j in net_m.nodes)
        peor["export_kW"] = max(peor["export_kW"], -float(net.res_ext_grid.p_mw.iloc[0]) * 1000.0)
        peor["Vmax_pu"] = max(peor["Vmax_pu"], float(vm.max()))
        peor["Vmin_pu"] = min(peor["Vmin_pu"], float(vm.min()))
        peor["Imax_A"] = max(peor["Imax_A"], float(net.res_line.i_ka.max()) * 1000.0)
        peor["max_dV_modelo"] = max(peor["max_dV_modelo"], dV)
    peor["cumple"] = bool(peor["export_kW"] <= LIM["export_kW"] + 1.0
                          and peor["Vmax_pu"] <= LIM["Vmax_pu"] + 1e-4
                          and peor["Vmin_pu"] >= LIM["Vmin_pu"] - 1e-4
                          and peor["Imax_A"] <= LIM["Imax_A"] + 0.5
                          and peor["max_dV_modelo"] <= 1e-4)
    return peor


def sin_bess(mes: int, t_lim: float) -> dict:
    r = run_hc_bess(cfg_base(mes, n_bess_max=0, bess_candidates=[], time_limit=t_lim), save=False)
    s = r["summary"]
    if r["model"].Status != GRB.OPTIMAL:
        raise RuntimeError(f"El caso sin BESS no llegó al óptimo (status {r['model'].Status}).")
    sitios = {int(b): p * 1000.0 for b, p in zip(r["pv_sites"]["bus"], r["pv_sites"]["P_cap_MW"]) if p * 1000.0 >= 1.0}
    return {"HC_kW": s["hosting_capacity_PV_MW"] * 1000.0, "sitios_kW": sitios,
            "mip_gap": s["mip_gap"], "tiempo_s": s["runtime_s"]}


def cota_inferior(mes: int, p_mw: float, sitios_pv, pares, t_lim: float, extra=None) -> dict:
    """pares: pares de barras para el BESS, con el PV en sitios_pv. extra: (par, sitios_pv) adicional,
    tomado de la solución de la cota superior (con baterías grandes el PV puede cambiar de barras)."""
    mejor, corridas = None, []
    casos = [(tuple(par), list(sitios_pv)) for par in pares]
    if extra is not None and tuple(extra[0]) not in {c[0] for c in casos}:
        casos.append((tuple(extra[0]), list(extra[1])))
    elif extra is not None:                                      # mismo par: ampliar los sitios de PV
        casos = [(par, sorted(set(pv) | set(extra[1])) if par == tuple(extra[0]) else pv) for par, pv in casos]
    for par, pv in casos:
        cfg = cfg_base(mes, pv_candidates=pv, bess_candidates=list(par),
                       p_b_max_mw=p_mw, e_b_max_mwh=TAU_H * p_mw, time_limit=t_lim)
        r = run_hc_bess(cfg, save=False)
        m, s = r["model"], r["summary"]
        c = {"par": list(par), "pv_candidatas": pv, "status": int(m.Status), "tiempo_s": round(m.Runtime, 1)}
        if m.SolCount:
            c.update(HC_kW=s["hosting_capacity_PV_MW"] * 1000.0, mip_gap=s["mip_gap"],
                     brecha_rel=s["conic_gap_rel"], horas_simultaneas=simultaneas(r["vars"]),
                     pv_kW={int(b): p * 1000.0 for b, p in zip(r["pv_sites"]["bus"], r["pv_sites"]["P_cap_MW"])
                            if p * 1000.0 >= 1.0},
                     bess_kW={int(b): p * 1000.0 for b, p in zip(r["bess_sites"]["bus"], r["bess_sites"]["P_cap_MW"])}
                     if len(r["bess_sites"]) else {})
            if c["horas_simultaneas"] == 0 and (mejor is None or c["HC_kW"] > mejor[0]["HC_kW"]):
                mejor = (c, r)
        corridas.append(c)
        print(f"    inferior, BESS en {par}, PV en {pv}: " + (f"HC = {c['HC_kW']:.1f} kW, gap {c['mip_gap']:.0e}, "
              f"{c['tiempo_s']:.0f} s" if "HC_kW" in c else f"sin solución (status {c['status']})"), flush=True)
    if mejor is None:
        return {"HC_kW": None, "corridas": corridas}
    c, r = mejor
    ac = flujo_ac_24h(r)
    print(f"    flujo AC de la mejor (BESS en {c['par']}): {'cumple' if ac['cumple'] else 'NO CUMPLE'} "
          f"(exportación máx {ac['export_kW']:.0f} kW, V {ac['Vmin_pu']:.3f}-{ac['Vmax_pu']:.4f}, "
          f"I máx {ac['Imax_A']:.0f} A, |V_modelo - V_AC| {ac['max_dV_modelo']:.0e})", flush=True)
    return {"HC_kW": c["HC_kW"], "mejor_par": c["par"], "ac": ac, "corridas": corridas}


def cota_superior(mes: int, p_mw: float, t_lim: float) -> dict:
    cfg = cfg_base(mes, p_b_max_mw=p_mw, e_b_max_mwh=TAU_H * p_mw, time_limit=t_lim)
    net, alpha = load_inputs(cfg)
    m, X = build_model(net, alpha, cfg)
    for d in (X["mu_ch"], X["mu_dis"]):                          # relajación: mu en [0, 1]
        for var in d.values():
            var.VType = GRB.CONTINUOUS
    m.optimize()
    out = {"status": int(m.Status), "tiempo_s": round(m.Runtime, 1),
           "HC_cota_kW": _hc_kw(m.ObjBound, alpha.to_numpy(), cfg)}
    if m.SolCount:
        r = extract_results(m, X, net, cfg)
        out.update(HC_solucion_relajada_kW=r["summary"]["hosting_capacity_PV_MW"] * 1000.0,
                   horas_simultaneas=simultaneas(X),
                   pv_kW={int(b): p * 1000.0 for b, p in zip(r["pv_sites"]["bus"], r["pv_sites"]["P_cap_MW"])
                          if p * 1000.0 >= 1.0},
                   bess_kW={int(b): p * 1000.0 for b, p in zip(r["bess_sites"]["bus"], r["bess_sites"]["P_cap_MW"])}
                   if len(r["bess_sites"]) else {})
    print(f"    superior (mu relajadas): cota {out['HC_cota_kW']:.1f} kW, {out['tiempo_s']:.0f} s"
          + (f", su solución carga y descarga a la vez en {out['horas_simultaneas']} casos"
             if out.get("horas_simultaneas") else ""), flush=True)
    return out


def cota_superior_horaria(mes: int, p_mw: float, t_lim: float, frac_alpha: float = 0.9) -> dict:
    """Cota superior por hora. Sin el estado de carga (SoC) las horas quedan desacopladas, salvo por los
    sitios y capacidades. La hora t sola es un problema T = 1 (como la Tabla 1) con la BESS como inyección
    neta en [-P_cap, P_cap] (mu relajadas: sin SoC no hay energía que disipar). Cualquier solución de
    24 h, mirada solo en la hora t, es factible para ese problema, así que HC* <= HC_t para cada t y
    HC* <= min_t HC_t. Basta con un subconjunto de horas: se usan las de alpha >= frac_alpha * max(alpha)."""
    cfg = cfg_base(mes, p_b_max_mw=p_mw, e_b_max_mwh=TAU_H * p_mw, time_limit=t_lim)
    net, alpha = load_inputs(cfg)
    horas, mejor = [], None
    for t in [t for t in alpha.index if alpha[t] >= frac_alpha * alpha.max()]:
        net1 = dataclasses.replace(net, PL={(j, 1): net.PL[j, t] for j in net.nodes},
                                   QL={(j, 1): net.QL[j, t] for j in net.nodes})
        cfg1 = dataclasses.replace(cfg, T=1)
        a1 = pd.Series([alpha[t]], index=[1], name="alpha")
        m, X = build_model(net1, a1, cfg1)
        m.update()
        for c in m.getConstrs():
            if c.ConstrName.startswith(("SoC0[", "SoCT[", "SoCdyn[", "SoCmin[", "SoCmax[")):
                m.remove(c)
        for d in (X["mu_ch"], X["mu_dis"]):
            for var in d.values():
                var.VType = GRB.CONTINUOUS
        m.optimize()
        h = {"t": int(t), "alpha": float(alpha[t]), "status": int(m.Status), "tiempo_s": round(m.Runtime, 1),
             "HC_cota_kW": _hc_kw(m.ObjBound, a1.to_numpy(), cfg1)}
        if m.SolCount:
            S = cfg.s_base_mva * 1000.0
            h.update(HC_solucion_kW=_hc_kw(m.ObjVal, a1.to_numpy(), cfg1),
                     pv_kW={int(j): X["Ppv_cap"][j].X * S for j in X["G_pv"] if X["Ppv_cap"][j].X * S >= 1.0},
                     bess_kW={int(j): X["Pb_cap"][j].X * S for j in X["G_b"] if X["z"][j].X > 0.5})
        horas.append(h)
        print(f"    superior horaria, hora {t} (alpha {alpha[t]:.3f}): cota {h['HC_cota_kW']:.1f} kW, "
              f"{h['tiempo_s']:.0f} s", flush=True)
        if mejor is None or h["HC_cota_kW"] < mejor["HC_cota_kW"]:
            mejor = h
    return {"HC_cota_kW": mejor["HC_cota_kW"], "hora": mejor["t"], "horas": horas}


def main() -> int:
    ap = argparse.ArgumentParser(description="Pregunta 1: cotas del HC con BESS (24 h, modelo exacto).")
    ap.add_argument("--mes", type=int, default=7)
    ap.add_argument("--tamanos", default="0.05", help="potencia por BESS [MW], separadas por coma")
    ap.add_argument("--pares", default=";".join(f"{a},{b}" for a, b in PARES_DEFECTO),
                    help='pares de barras para el BESS de la cota inferior, p.ej. "32,33;21,22"')
    ap.add_argument("--t-inferior", type=float, default=600.0, help="tope de tiempo por par [s]")
    ap.add_argument("--t-horaria", type=float, default=900.0, help="tope de tiempo por hora de la cota horaria [s]")
    ap.add_argument("--cota-mu", action="store_true",
                    help="calcular también la cota con mu relajadas (más lenta y más débil que la horaria)")
    ap.add_argument("--t-superior", type=float, default=1200.0, help="tope de tiempo de la cota con mu relajadas [s]")
    ap.add_argument("--solo-horaria", action="store_true",
                    help="solo agregar la cota horaria a los tamaños ya guardados (no recalcula la cota inferior)")
    a = ap.parse_args()
    tamanos = [float(x) for x in a.tamanos.split(",")]
    pares = [tuple(int(b) for b in p.split(",")) for p in a.pares.split(";")]

    print("=" * 78)
    print(f"PREGUNTA 1: cotas del HC con BESS (mes {a.mes}, 24 h, exportación <= 4.6 MW, modelo exacto)")
    print("=" * 78)
    t0 = time.time()
    base = sin_bess(a.mes, 600.0)
    print(f"Sin BESS: HC = {base['HC_kW']:.1f} kW (óptimo), PV en "
          f"{ {j: round(p) for j, p in base['sitios_kW'].items()} }", flush=True)

    salida = {"mes": a.mes, "tau_h": TAU_H, "export_max_kW": -P_S_REF_PU * 1e4, "sin_bess": base, "tamanos": {}}
    # Conservar los tamaños ya calculados con la misma configuración (el barrido se corre por partes)
    if os.path.exists(RESULTS_JSON):
        with open(RESULTS_JSON, encoding="utf-8") as f:
            previo = json.load(f)
        if all(previo.get(k) == salida[k] for k in ("mes", "tau_h", "export_max_kW")):
            salida["tamanos"] = previo.get("tamanos", {})

    def guardar():
        os.makedirs(os.path.dirname(RESULTS_JSON), exist_ok=True)
        salida["tamanos"] = dict(sorted(salida["tamanos"].items(), key=lambda kv: float(kv[0])))
        with open(RESULTS_JSON, "w", encoding="utf-8") as f:
            json.dump(salida, f, indent=2, ensure_ascii=False, default=float)

    for p in tamanos:
        print(f"\n--- 2 BESS de {p * 1000:.0f} kW / {TAU_H * p * 1000:.0f} kWh ---", flush=True)
        if a.solo_horaria:
            d = salida["tamanos"].get(f"{p:g}")
            if d is None:
                print("    (sin cota inferior guardada para este tamaño; se omite)", flush=True)
                continue
            d["cota_superior_horaria"] = cota_superior_horaria(a.mes, p, a.t_horaria)
            inf = d["cota_inferior"]
        else:
            d = {"cota_superior_horaria": cota_superior_horaria(a.mes, p, a.t_horaria)}
            if a.cota_mu:
                d["cota_superior"] = cota_superior(a.mes, p, a.t_superior)
            # Caso extra para la cota inferior: las barras de BESS y PV de la solución de la hora crítica
            hc = d["cota_superior_horaria"]
            sol_h = next(h for h in hc["horas"] if h["t"] == hc["hora"])
            extra = None
            if len(sol_h.get("bess_kW", {})) == 2:
                extra = (sorted(sol_h["bess_kW"]), sorted(set(base["sitios_kW"]) | set(sol_h.get("pv_kW", {}))))
            inf = cota_inferior(a.mes, p, base["sitios_kW"].keys(), pares, a.t_inferior, extra)
            d["cota_inferior"] = inf
        if inf["HC_kW"] is not None:
            cotas = [d[k]["HC_cota_kW"] for k in ("cota_superior_horaria", "cota_superior") if k in d]
            lo, hi, h0 = inf["HC_kW"], min(cotas), base["HC_kW"]
            d["resumen"] = {"HC_min_kW": lo, "HC_max_kW": hi, "ancho_pct": 100 * (hi - lo) / lo,
                            "dHC_min_kW": lo - h0, "dHC_max_kW": hi - h0,
                            "dHC_min_pct": 100 * (lo / h0 - 1), "dHC_max_pct": 100 * (hi / h0 - 1)}
            print(f"  => HC con BESS entre {lo:.0f} y {hi:.0f} kW (ancho {d['resumen']['ancho_pct']:.2f} %): "
                  f"{d['resumen']['dHC_min_pct']:+.2f} % a {d['resumen']['dHC_max_pct']:+.2f} % sobre sin BESS",
                  flush=True)
        salida["tamanos"][f"{p:g}"] = d
        guardar()                                                # guardar tras cada tamaño

    guardar()
    print(f"\nGuardado: {os.path.relpath(RESULTS_JSON, BASE_DIR)} ({(time.time() - t0) / 60:.1f} min)")
    ok = all(salida["tamanos"].get(f"{p:g}", {}).get("cota_inferior", {}).get("ac", {}).get("cumple", False)
             for p in tamanos)
    print("Las soluciones de la cota inferior cumplen los límites en el flujo AC." if ok
          else "OJO: alguna cota inferior sin solución o con violaciones en el flujo AC.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
