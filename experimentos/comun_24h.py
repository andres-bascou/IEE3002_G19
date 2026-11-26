"""
experimentos/comun_24h.py
=========================
Funciones comunes para los experimentos con el modelo multiperíodo (T = 24 h) y BESS.

Decisiones del equipo para la entrega final (ver README, sección 7):
    * Día de diseño: julio (perfil PV promedio del mes y demanda CEN del 31-jul).
    * BESS: barrido de un presupuesto de energía sum_j E_j <= B [MWh]; ubicación y tamaño
      los elige el modelo (sin costo de inversión). Hasta 2 unidades, en 8 barras candidatas
      (extremos y puntos medios de los cuatro alimentadores). Duración fija tau = E/P.
    * Límite de exportación de 4.6 MW de [4]: con y sin.
    * SoC cíclico (SoC_24 = SoC_0): el día se puede repetir (reemplaza la restr. (19) del informe).
    * Exactitud y binarias "perezosas" (resolver_24h): la igualdad cónica y las binarias de
      carga/descarga se imponen solo en las horas que pueden limitar el HC (alpha_t >= 70 % del
      máximo, HORAS_EXACTAS); en las demás se usa el cono relajado y no hay binarias. Este modelo
      mixto es una relajación del exacto, así que su óptimo es una cota superior del HC. El
      certificado de factibilidad es el flujo AC: si las inyecciones de la solución (PV y BESS)
      cumplen todos los límites en el flujo AC de pandapower en cada hora, y ningún BESS carga y
      descarga a la vez, el HC es alcanzable y por lo tanto óptimo. Si alguna hora falla, se le
      imponen la igualdad y las binarias y se vuelve a resolver.
      Pruebas con B = 2 MWh (20 min cada una): sin binarias, el BESS cargó y descargó a la vez para
      disipar energía (gap 12.9 %); con igualdad y binarias en las 11 horas de sol, gap 18 %.
    * Cada solución se valida hora a hora con un flujo AC de pandapower (flujo_ac_24h).
"""
import os
import sys

import numpy as np
import pandapower as pp
import pandapower.networks as pn
from gurobipy import GRB

# OJO: NO usar rutas absolutas (p.ej. r"C:\Users\..." o "/Users/..."): solo funcionan en un PC.
# Se resuelve la raíz del proyecto relativa a este archivo (<raíz>/<carpeta>/este_script.py).
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # raíz del proyecto
sys.path.insert(0, BASE_DIR)

from modelo.misocp_hc_bess import (HCConfig, build_model, extract_results,  # noqa: E402
                                   load_inputs, load_pv_profile, resolve_data_dir)

# Extremos y puntos medios de los alimentadores: troncal 1-18 (9, 13, 18), ramal 2-22 (22),
# ramal 3-25 (25), ramal 6-33 (6, 29, 33).
BESS_CANDIDATOS = [6, 9, 13, 18, 22, 25, 29, 33]
EXPORTACION = {"con_limite": -0.46, "sin_limite": None}     # P_S >= -4.6 MW, o sin límite
LIMITES = {"export_kW": 4600.0, "Vmin_pu": 0.90, "Vmax_pu": 1.10, "Imax_A": 300.0}
TOL_SIMULTANEO_MW = 1e-4          # 0.1 kW: carga y descarga simultáneas que se consideran reales
TOL_ACTIVO = {"export_kW": 1.0, "Vmax_pu": 1e-4, "Imax_A": 0.5}
MES = 7
_alpha = load_pv_profile(resolve_data_dir(), 24, MES)
HORAS_SOL = [int(t) for t in _alpha.index if _alpha[t] > 0]     # períodos t (1..24) con alpha_t > 0
FRAC_EXACTA = 0.70
HORAS_EXACTAS = [int(t) for t in _alpha.index if _alpha[t] >= FRAC_EXACTA * _alpha.max()]


def config_24h(B_mwh: float = 0.0, p_s_ref=-0.46, tau_h: float = 2.0, **kw) -> HCConfig:
    """Configuración base de la Etapa 3 (julio, 24 h, modelo exacto, max sum P^PV, sin vertimiento).
    B_mwh = 0 => sin BESS. Cada unidad puede tomar todo el presupuesto (P <= B/tau, E <= B)."""
    base = dict(T=24, month=MES, exact_cone=True, objective="pv", curtailment_allowed=False,
                p_pv_max_mw=20.0, n_pv_max=32, pv_candidates=None, p_s_ref_pu=p_s_ref,
                mip_gap=1e-4, time_limit=1200, output_flag=0,
                exact_cone_horas=list(HORAS_EXACTAS), bess_mu_binaries=True, bess_mu_horas=list(HORAS_EXACTAS),
                soc_ciclico=True)
    if B_mwh > 0:
        base.update(n_bess_max=2, bess_candidates=list(BESS_CANDIDATOS), e_b_budget_mwh=B_mwh,
                    e_b_max_mwh=B_mwh, p_b_max_mw=B_mwh / tau_h, tau_min=tau_h, tau_max=tau_h)
    else:
        base.update(n_bess_max=0, bess_candidates=[])
    base.update(kw)
    return HCConfig(**base)


def _horas_violadas(ac: dict, cfg: HCConfig) -> list:
    """Períodos t donde el flujo AC con las inyecciones de la solución viola algún límite."""
    con_lim = cfg.p_s_ref_pu is not None
    return [h["t"] for h in ac["horas"] if (
        h["Vmax_pu"] > LIMITES["Vmax_pu"] + 1e-4 or h["Vmin_pu"] < LIMITES["Vmin_pu"] - 1e-4
        or h["Imax_A"] > LIMITES["Imax_A"] + 0.5
        or (con_lim and h["export_kW"] > LIMITES["export_kW"] + 1.0))]


def resolver_24h(cfg: HCConfig, max_iter: int = 6, warm: dict = None) -> dict:
    """Resuelve el modelo mixto (igualdad cónica y binarias solo en cfg.exact_cone_horas /
    cfg.bess_mu_horas) y certifica la solución con el flujo AC. Si una hora viola límites en AC,
    o un BESS carga y descarga a la vez en una hora sin binarias, se imponen la igualdad y las
    binarias en esa hora y se vuelve a resolver desde la solución anterior.
    El tope cfg.time_limit es para toda la corrida. Devuelve también r["ac"].
    warm: {"Ppv_cap": {j: MW}, "w": {j: 0/1}} como solución inicial (opcional)."""
    net, alpha = load_inputs(cfg)
    m, X = build_model(net, alpha, cfg)
    S, T = cfg.s_base_mva, X["T"]
    if warm:
        for j, val in warm.get("w", {}).items():
            if j in X["w"]:
                X["w"][j].Start = val
        for j, val in warm.get("Ppv_cap", {}).items():
            if j in X["Ppv_cap"]:
                X["Ppv_cap"][j].Start = val / S
    h_eq = set(T if cfg.exact_cone_horas is None else cfg.exact_cone_horas) if cfg.exact_cone else set()
    h_mu = set(T if cfg.bess_mu_horas is None else cfg.bess_mu_horas) if cfg.bess_mu_binaries else set()
    agregadas, iters, t_total, r_ok = [], 0, 0.0, None
    pb = cfg.p_b_max_mw / S
    while True:
        if cfg.time_limit:
            m.Params.TimeLimit = max(cfg.time_limit - t_total, 60.0)
        m.optimize()
        t_total += m.Runtime
        if m.SolCount == 0:
            break
        r_ok = r = _resultado(m, X, net, cfg, alpha, t_total, iters, agregadas)
        ac = flujo_ac_24h(r)
        r["ac"] = ac
        sitios = [j for j in X["G_b"] if X["z"][j].X > 0.5]
        simult = {t for j in sitios for t in T if t not in h_mu
                  and min(X["Pch"][j, t].X, X["Pdis"][j, t].X) * S > TOL_SIMULTANEO_MW}
        malas = sorted((set(_horas_violadas(ac, cfg)) - h_eq) | simult)
        r["summary"]["certificado_AC"] = not malas
        if not malas or iters >= max_iter or not cfg.exact_cone:
            return r
        iters += 1
        vars_ = m.getVars()
        start = [v.X for v in vars_]
        for t in malas:
            if t not in h_eq:
                for j in net.nplus:
                    p = net.parent[j]
                    m.addQConstr(X["Pf"][j, t] * X["Pf"][j, t] + X["Qf"][j, t] * X["Qf"][j, t]
                                 == X["v"][p, t] * X["l"][j, t], name=f"BFM_expost[{j},{t}]")
                h_eq.add(t)
            if t not in h_mu:
                for j in X["G_b"]:
                    b = m.addVar(vtype=GRB.BINARY, name=f"mu_expost[{j},{t}]")
                    m.addConstr(X["Pch"][j, t] <= b * pb, name=f"Pch_mu_expost[{j},{t}]")
                    m.addConstr(X["Pdis"][j, t] <= (1 - b) * pb, name=f"Pdis_mu_expost[{j},{t}]")
                h_mu.add(t)
            agregadas.append(t)
        m.update()
        for v, x0 in zip(vars_, start):
            v.Start = x0
        print(f"    iteración {iters}: horas exactas agregadas {malas} ({t_total:.0f} s)", flush=True)
    if r_ok is not None:            # la última reoptimización no encontró solución: se devuelve la anterior
        r_ok["summary"]["certificado_AC"] = False
        return r_ok
    r = _resultado(m, X, net, cfg, alpha, t_total, iters, agregadas)
    r["ac"] = None                  # sin solución
    return r


def _resultado(m, X, net, cfg, alpha, t_total, iters, agregadas) -> dict:
    r = extract_results(m, X, net, cfg)
    r.update(model=m, network=net, config=cfg, vars=X, alpha=alpha)
    if r["summary"].get("solution"):
        r["summary"].update(runtime_s=t_total, expost_iter=iters, horas_agregadas=list(agregadas),
                            mip_bound_MW=m.ObjBound * cfg.s_base_mva / max(
                                float(alpha.sum()) * cfg.dt, 1e-12))
    return r


def flujo_ac_24h(r: dict) -> dict:
    """Flujo AC de pandapower en cada hora con la solución del modelo: cargas P_L(j,t), PV
    alpha_t * P_cap (Q según el fp) y BESS como inyección neta P_dis - P_ch."""
    net_m, cfg, alpha = r["network"], r["config"], r["alpha"]
    S = cfg.s_base_mva
    tan_phi = float(np.tan(np.arccos(cfg.pv_pf))) if cfg.pv_pf < 1.0 else 0.0
    pv = {int(b): p for b, p in zip(r["pv_sites"]["bus"], r["pv_sites"]["P_cap_MW"])}
    ops = r["bess_ops"]
    V_mod = r["voltages"]
    horas = []
    for t in range(1, cfg.T + 1):
        net = pn.case33bw()
        net.line = net.line.iloc[:32].copy()             # red radial, sin tie-lines
        for idx, b in net.load.bus.items():
            j = int(b) + 1
            net.load.at[idx, "p_mw"] = net_m.PL[j, t] * S
            net.load.at[idx, "q_mvar"] = net_m.QL[j, t] * S
        for j, cap in pv.items():
            p = float(alpha[t]) * cap
            pp.create_sgen(net, j - 1, p_mw=p, q_mvar=-tan_phi * p)
        if len(ops):
            for _, o in ops[ops["t"] == t].iterrows():
                pp.create_sgen(net, int(o["bus"]) - 1, p_mw=o["P_dis_MW"] - o["P_ch_MW"], q_mvar=0.0)
        pp.runpp(net, numba=False, tolerance_mva=1e-9)
        V = {int(b) + 1: float(v) for b, v in net.res_bus.vm_pu.items()}
        horas.append({"t": t, "export_kW": -float(net.res_ext_grid.p_mw.iloc[0]) * 1000.0,
                      "Vmax_pu": max(V.values()), "Vmin_pu": min(V.values()),
                      "Imax_A": float(net.res_line.i_ka.max()) * 1000.0,
                      "perdidas_kW": float(net.res_line.pl_mw.sum()) * 1000.0,
                      "dV_max": max(abs(float(V_mod.loc[t, j]) - V[j]) for j in V)})
    peor = {"export_kW": max(h["export_kW"] for h in horas), "Vmax_pu": max(h["Vmax_pu"] for h in horas),
            "Vmin_pu": min(h["Vmin_pu"] for h in horas), "Imax_A": max(h["Imax_A"] for h in horas),
            "dV_max": max(h["dV_max"] for h in horas)}
    con_lim = cfg.p_s_ref_pu is not None
    activos = sorted({k for h in horas for k, ok in (
        ("exportación", con_lim and h["export_kW"] >= LIMITES["export_kW"] - TOL_ACTIVO["export_kW"]),
        ("V_max", h["Vmax_pu"] >= LIMITES["Vmax_pu"] - TOL_ACTIVO["Vmax_pu"]),
        ("I_max", h["Imax_A"] >= LIMITES["Imax_A"] - TOL_ACTIVO["Imax_A"])) if ok})
    horas_activas = sorted({h["t"] - 1 for h in horas if (
        (con_lim and h["export_kW"] >= LIMITES["export_kW"] - TOL_ACTIVO["export_kW"])
        or h["Vmax_pu"] >= LIMITES["Vmax_pu"] - TOL_ACTIVO["Vmax_pu"]
        or h["Imax_A"] >= LIMITES["Imax_A"] - TOL_ACTIVO["Imax_A"])})
    viola = (peor["Vmax_pu"] > LIMITES["Vmax_pu"] + 1e-4 or peor["Vmin_pu"] < LIMITES["Vmin_pu"] - 1e-4
             or peor["Imax_A"] > LIMITES["Imax_A"] + 0.5
             or (con_lim and peor["export_kW"] > LIMITES["export_kW"] + 1.0))
    return {"peor": peor, "limites_activos": activos, "horas_activas": horas_activas,
            "viola_limites_AC": bool(viola), "horas": horas}


def resumen(r: dict, ac: dict) -> dict:
    """Resumen compacto (JSON) de una corrida."""
    s = r["summary"]
    S = r["config"].s_base_mva
    bess = [{"bus": int(b), "P_MW": float(p), "E_MWh": float(e)}
            for b, p, e in zip(r["bess_sites"]["bus"], r["bess_sites"]["P_cap_MW"],
                               r["bess_sites"]["E_cap_MWh"])] if len(r["bess_sites"]) else []
    ops = r["bess_ops"]
    despacho = {}
    if len(ops):
        for b in ops["bus"].unique():
            o = ops[ops["bus"] == b].sort_values("t")
            despacho[str(int(b))] = {"P_ch_MW": o["P_ch_MW"].round(6).tolist(),
                                     "P_dis_MW": o["P_dis_MW"].round(6).tolist(),
                                     "SoC_MWh": o["SoC_MWh"].round(6).tolist()}
    return {"HC_kW": s["hosting_capacity_PV_MW"] * 1000.0,
            "sitios_pv_kW": {int(b): p * 1000.0 for b, p in zip(r["pv_sites"]["bus"], r["pv_sites"]["P_cap_MW"])
                             if p * 1000.0 >= 1.0},
            "bess": bess, "BESS_P_MW": s["BESS_P_MW"], "BESS_E_MWh": s["BESS_E_MWh"],
            "status": int(s["status"]), "mip_gap": float(s["mip_gap"]), "tiempo_s": float(s["runtime_s"]),
            "brecha_rel": float(s["conic_gap_rel"]), "perdidas_MWh": float(s["losses_MWh"]),
            "bess_simultaneo_MW": float(s["bess_simultaneo_MW"]),
            "expost_iter": int(s.get("expost_iter", 0)), "horas_agregadas": s.get("horas_agregadas", []),
            "cota_HC_kW": float(s.get("mip_bound_MW", float("nan"))) * 1000.0,
            "P_S_MW": r["substation"]["P_S_MW"].round(6).tolist(),
            "Vmax_t_pu": r["voltages"].max(axis=1).round(6).tolist(),
            "despacho": despacho, "ac": ac, "S_base": S}
