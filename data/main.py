"""
models/misocp_hc_bess.py
========================
Hosting Capacity (HC) con PV + BESS en redes de distribución radiales.

MISOCP multiperíodo (T = 24 h) basado en la relajación cónica del Branch Flow
Model (Jabr / Farivar & Low) sobre la red IEEE 33-bus.

Decisiones de planificación : w_j, P_j^{PV,cap}, z_j, P_j^{B,cap}, E_j^{B,cap}
Decisiones de operación     : P^{PV}, P^{ch}, P^{dis}, SoC, mu^{ch}, mu^{dis}
Estado de red               : v, l, P_br, Q_br, P_S, Q_S

Uso rápido
----------
    from models.misocp_hc_bess import HCConfig, run_hc_bess
    res = run_hc_bess(HCConfig(month=7, n_pv_max=3, n_bess_max=2))
    print(res["summary"])

Portabilidad de rutas
---------------------
La carpeta de datos se resuelve (en este orden) con:
    1. argumento `data_dir` / `HCConfig.data_dir`
    2. variable de entorno HC_DATA_DIR
    3. <raíz_del_proyecto>/data   (raíz = carpeta padre de /models)
    4. ./data  (directorio de trabajo actual)
Nunca se usan rutas absolutas, así que funciona en cualquier PC.

Fuentes de los parámetros por defecto (ver HCConfig)
----------------------------------------------------
[R1] M. E. Baran and F. F. Wu, "Network reconfiguration in distribution
     systems for loss reduction and load balancing," IEEE Trans. Power
     Delivery, vol. 4, no. 2, pp. 1401-1407, Apr. 1989, doi: 10.1109/61.25627.
     Red IEEE 33-bus cargada desde pandapower (pandapower.networks.case33bw,
     equivalente a case33bw de MATPOWER): S_base = 10 MVA, V_base = 12.66 kV.
[R2] Blanco-Solano et al. (2026), Sec. 4.1: misma red como benchmark y
     límite térmico de conductores I_max = 300 A.
[R3] Terralink, "Almacenamiento de energía solar (BESS): guía para empresas",
     https://www.terralink.cl/aprende/almacenamiento-energia-solar-bess-guia-empresas-chile
     -> eficiencias de carga y descarga (eta_ch = eta_dis = 0.95).
[R4] TFM-2026-006, Universidad de Zaragoza,
     https://zaguan.unizar.es/record/170538/files/TAZ-TFM-2026-006.pdf
     -> coeficiente de degradación de celdas (c_deg = beta = 0.019).
[R5] National Battery Authority, "Battery energy storage systems commercial",
     https://nationalbatteryauthority.com/battery-energy-storage-systems-commercial/
     -> capacidad máxima de energía por BESS (100 kWh).
[R6] Supuestos propios del proyecto (paramV2.py): potencia máx. de carga/descarga
     50 kW (autonomía de 2 h => tau = 2 h) y energía inicial/final S0 = 10 kWh
     (arbitrario) => kappa_0 = S0 / E_max = 0.10.
"""
from __future__ import annotations

import json
import os
from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import gurobipy as gp
import numpy as np
import pandas as pd
from gurobipy import GRB


# =============================================================================
# 1. CONFIGURACIÓN
# =============================================================================
@dataclass
class HCConfig:
    # --- Datos -------------------------------------------------------------
    data_dir: Optional[str] = None           # carpeta /data (None = autodetección)
    demand_basis: str = "peak"               # "peak" | "mean" (archivo de perfiles)
    month: object = 7                        # int 1..12 o nombre de columna/mes
    alpha_file: Optional[str] = None         # p.ej. "alpha_t_mes_07.csv" (opcional)

    # --- Red / simulación ---------------------------------------------------
    T: int = 24
    dt: float = 1.0                          # [h]
    s_base_mva: float = 10.0                 # [MVA]  [R1] net.sn_mva de case33bw
    v_base_kv: float = 12.66                 # [kV]   [R1] net.bus.vn_kv de case33bw
    v_min: float = 0.95                      # usado si el CSV no trae v_min_pu
    v_max: float = 1.05                      # usado si el CSV no trae v_max_pu
    v_slack: float = 1.0
    # Límite térmico [R2]: 300 A. pandapower trae max_i_ka = 99999 (= "sin límite"),
    # por eso se define aquí y se convierte a p.u. con I_base = S_base/(sqrt(3) V_base).
    # Se usa cuando i_max_pu falta en el CSV o viene como "infinito" (>= 1e3 p.u.).
    i_max_a: Optional[float] = 300.0         # [A]; None = sin límite
    # OJO: Gmax = 500 kW de paramV2.py es el trafo del problema EV (otra escala);
    # NO se usa aquí porque la demanda IEEE-33 (3.715 MW) lo haría infactible.
    s_sub_max_pu: float = 1.0                # capacidad transformador SE [p.u.]
    p_s_ref_pu: Optional[float] = None       # P_S >= p_s_ref (None = sin límite; 0 = sin retorno)

    # --- PV -------------------------------------------------------------------
    p_pv_max_mw: float = 2.0                 # por proyecto [MW]
    n_pv_max: int = 3
    pv_candidates: Optional[Iterable[int]] = None   # None = todas las barras N+
    curtailment_allowed: bool = True         # False => P_pv = alpha_t * P_cap

    # --- BESS -----------------------------------------------------------------
    p_b_max_mw: float = 0.050                # [MW]  = Dmax = Cmax = 50 kW   [R6]
    e_b_max_mwh: float = 0.100               # [MWh] = Smax = 100 kWh        [R5]
    tau_min: float = 2.0                     # [h] autonomía de 2 h => E/P = 2 [R6]
    tau_max: float = 2.0                     # [h] (subir tau_max para dar flexibilidad)
    n_bess_max: int = 2
    bess_candidates: Optional[Iterable[int]] = None
    eta_ch: float = 0.95                     # [R3]
    eta_dis: float = 0.95                    # [R3]
    kappa_min: float = 0.10                  # DoD 80 % (documento del modelo)
    kappa_max: float = 0.90
    kappa_0: float = 0.10                    # = S0/Smax = 10 kWh / 100 kWh  [R6]
    c_deg: float = 0.019                     # beta [R4]

    # --- Solver ---------------------------------------------------------------
    mip_gap: float = 1e-3
    time_limit: Optional[float] = 600
    threads: Optional[int] = None
    output_flag: int = 1


# =============================================================================
# 2. CARGA DE DATOS (pandas)
# =============================================================================
def resolve_data_dir(data_dir: Optional[str] = None) -> Path:
    candidates = []
    if data_dir:
        candidates.append(Path(data_dir))
    if os.environ.get("HC_DATA_DIR"):
        candidates.append(Path(os.environ["HC_DATA_DIR"]))
    candidates.append(Path(__file__).resolve().parents[1] / "data")
    candidates.append(Path.cwd() / "data")
    for c in candidates:
        if c.is_dir():
            return c
    raise FileNotFoundError(
        "No se encontró la carpeta 'data'. Pasa data_dir=... o define HC_DATA_DIR. "
        f"Probé: {[str(c) for c in candidates]}"
    )


def load_grid(data_dir: Path) -> Tuple[pd.DataFrame, pd.DataFrame]:
    nodes = pd.read_csv(data_dir / "grid" / "ieee33_nodes.csv")
    branches = pd.read_csv(data_dir / "grid" / "ieee33_branches.csv")
    nodes.columns = [c.strip() for c in nodes.columns]
    branches.columns = [c.strip() for c in branches.columns]
    return nodes, branches


def load_demand_profiles(data_dir: Path, basis: str, T: int) -> pd.DataFrame:
    df = pd.read_csv(data_dir / "demand" / f"demand_profiles_norm_{basis}.csv")
    df.columns = [c.strip() for c in df.columns]
    if "periodo_t" in df.columns:
        df = df.sort_values("periodo_t")
    df = df.reset_index(drop=True).iloc[:T]
    if len(df) < T:
        raise ValueError(f"El perfil de demanda tiene {len(df)} filas; se requieren {T}.")
    df.index = range(1, T + 1)   # t = 1..T
    return df


_META_COLS = {"hora", "hour", "periodo_t", "periodo", "t", "time", "unnamed: 0"}


def load_pv_profile(data_dir: Path, T: int, month: object = 7,
                    alpha_file: Optional[str] = None) -> pd.Series:
    """Devuelve alpha_t (índice 1..T) en [0, 1]."""
    path = Path(alpha_file) if alpha_file else data_dir / "pv_profiles" / "alpha_t_mensual_anual.csv"
    if alpha_file and not path.is_absolute() and not path.exists():
        path = data_dir / "pv_profiles" / alpha_file
    df = pd.read_csv(path)
    df.columns = [str(c).strip() for c in df.columns]
    cols = [c for c in df.columns if c.lower() not in _META_COLS]

    if len(cols) == 1:                       # archivo de un solo mes
        col = cols[0]
    elif isinstance(month, (int, np.integer)):
        col = cols[int(month) - 1]           # meses en orden de columnas
    else:
        match = [c for c in cols if str(month).strip().lower() in c.lower()]
        if not match:
            raise KeyError(f"Mes '{month}' no encontrado en columnas {cols}")
        col = match[0]

    alpha = df[col].astype(float).iloc[:T].clip(0.0, 1.0).to_numpy()
    if len(alpha) < T:
        raise ValueError(f"El perfil PV tiene {len(alpha)} filas; se requieren {T}.")
    return pd.Series(alpha, index=range(1, T + 1), name="alpha")


def _lambda_column(customer_type: object) -> str:
    s = str(customer_type).strip().lower()
    if s.startswith("peq") or "small" in s:
        return "lambda_pequenas"
    if s.startswith("gra") or "large" in s:
        return "lambda_grandes"
    return "lambda_regulados"


# =============================================================================
# 3. TOPOLOGÍA Y PARÁMETROS DE RED
# =============================================================================
@dataclass
class Network:
    nodes: List[int]
    slack: int
    parent: Dict[int, int]                   # pi(j)
    children: Dict[int, List[int]]           # C(j)
    r: Dict[int, float]                      # r_{pi(j) j}, indexado por j
    x: Dict[int, float]
    i_max: Dict[int, float]                  # NaN/inf si no hay límite
    v_min: Dict[int, float]
    v_max: Dict[int, float]
    PL: Dict[Tuple[int, int], float]         # (j, t)
    QL: Dict[Tuple[int, int], float]

    @property
    def nplus(self) -> List[int]:
        return [j for j in self.nodes if j != self.slack]


def _detect_slack(nodes: pd.DataFrame) -> int:
    for _, row in nodes.iterrows():
        tipo = str(row.get("tipo", "")).strip().lower()
        if any(k in tipo for k in ("slack", "ref", "sub", "swing")) or tipo in ("3", "3.0"):
            return int(row["bus_id"])
    return int(nodes["bus_id"].min())


def build_network(nodes: pd.DataFrame, branches: pd.DataFrame,
                  demand: pd.DataFrame, cfg: HCConfig) -> Network:
    ids = [int(b) for b in nodes["bus_id"]]
    slack = _detect_slack(nodes)

    # Orientación aguas abajo mediante BFS desde la subestación (árbol)
    adj = defaultdict(list)
    for k, row in branches.iterrows():
        a, b = int(row["i"]), int(row["j"])
        adj[a].append((b, k))
        adj[b].append((a, k))

    parent, br_of, children = {}, {}, defaultdict(list)
    seen, queue = {slack}, deque([slack])
    while queue:
        u = queue.popleft()
        for w, k in adj[u]:
            if w not in seen:
                seen.add(w)
                parent[w] = u
                br_of[w] = k
                children[u].append(w)
                queue.append(w)
    if len(seen) != len(ids) or len(branches) != len(ids) - 1:
        raise ValueError("La red no es un árbol conexo (|S_br| != |N|-1).")

    # I_base = S_base / (sqrt(3) * V_base) [kA];  I_max[p.u.] = I_max[A]/1000/I_base  [R1, R2]
    i_base_ka = cfg.s_base_mva / (np.sqrt(3.0) * cfg.v_base_kv)
    i_max_default = (cfg.i_max_a / 1000.0 / i_base_ka) if cfg.i_max_a is not None else np.inf

    r, x, imax = {}, {}, {}
    for j, k in br_of.items():
        row = branches.loc[k]
        r[j], x[j] = float(row["r_pu"]), float(row["x_pu"])
        im = row["i_max_pu"] if "i_max_pu" in branches.columns else np.nan
        if pd.isna(im) or im >= 1e3:       # vacío o "sin límite" (p.ej. 99999 de pandapower)
            im = i_max_default
        imax[j] = float(im)

    nd = nodes.set_index("bus_id")
    vmin = {j: float(nd.at[j, "v_min_pu"]) if "v_min_pu" in nd and pd.notna(nd.at[j, "v_min_pu"])
            else cfg.v_min for j in ids}
    vmax = {j: float(nd.at[j, "v_max_pu"]) if "v_max_pu" in nd and pd.notna(nd.at[j, "v_max_pu"])
            else cfg.v_max for j in ids}

    # Demanda: P_L(j,t) = P0_pu(j) * lambda_tipo(t)  (factor de potencia constante)
    PL, QL = {}, {}
    for j in ids:
        col = _lambda_column(nd.at[j, "customer_type"] if "customer_type" in nd else "")
        p0, q0 = float(nd.at[j, "P0_pu"]), float(nd.at[j, "Q0_pu"])
        for t in range(1, cfg.T + 1):
            lam = float(demand.at[t, col])
            PL[j, t], QL[j, t] = p0 * lam, q0 * lam

    return Network(ids, slack, parent, dict(children), r, x, imax, vmin, vmax, PL, QL)


# =============================================================================
# 4. MODELO MISOCP
# =============================================================================
def build_model(net: Network, alpha: pd.Series, cfg: HCConfig) -> Tuple[gp.Model, dict]:
    T = list(range(1, cfg.T + 1))
    T0 = [0] + T
    dt = cfg.dt
    N, Np, s = net.nodes, net.nplus, net.slack
    ch = lambda j: net.children.get(j, [])

    G_pv = sorted(set(cfg.pv_candidates)) if cfg.pv_candidates is not None else list(Np)
    G_b = sorted(set(cfg.bess_candidates)) if cfg.bess_candidates is not None else list(Np)
    if s in G_pv or s in G_b:
        raise ValueError("La subestación no puede ser candidata a PV/BESS.")

    # Conversión a p.u.
    E_base = cfg.s_base_mva * 1.0                          # [MWh], con dt0 = 1 h
    P_pv_max = cfg.p_pv_max_mw / cfg.s_base_mva
    P_b_max = cfg.p_b_max_mw / cfg.s_base_mva
    E_b_max = cfg.e_b_max_mwh / E_base

    m = gp.Model("misocp_hc_bess")
    m.Params.OutputFlag = cfg.output_flag
    m.Params.MIPGap = cfg.mip_gap
    if cfg.time_limit:
        m.Params.TimeLimit = cfg.time_limit
    if cfg.threads:
        m.Params.Threads = cfg.threads

    # ---- Variables de red (límites como bounds => modelo más compacto) --------
    v = m.addVars(N, T, name="v",
                  lb={(j, t): net.v_min[j] ** 2 for j in N for t in T},
                  ub={(j, t): net.v_max[j] ** 2 for j in N for t in T})
    for t in T:                                            # (eq. slack_volt)
        v[s, t].LB = v[s, t].UB = cfg.v_slack ** 2
    l = m.addVars(Np, T, name="l", lb=0.0,
                  ub={(j, t): (net.i_max[j] ** 2 if np.isfinite(net.i_max[j]) else GRB.INFINITY)
                      for j in Np for t in T})
    Pf = m.addVars(Np, T, lb=-GRB.INFINITY, name="Pbr")
    Qf = m.addVars(Np, T, lb=-GRB.INFINITY, name="Qbr")
    PS = m.addVars(T, lb=-GRB.INFINITY, name="PS")
    QS = m.addVars(T, lb=-GRB.INFINITY, name="QS")

    # ---- Variables PV ------------------------------------------------------------
    w = m.addVars(G_pv, vtype=GRB.BINARY, name="w")
    Ppv_cap = m.addVars(G_pv, lb=0.0, name="Ppv_cap")
    Ppv = m.addVars(G_pv, T, lb=0.0, name="Ppv")
    Qpv = m.addVars(G_pv, T, lb=0.0, ub=0.0, name="Qpv")   # FP unitario (restr. 9)

    # ---- Variables BESS ----------------------------------------------------------
    z = m.addVars(G_b, vtype=GRB.BINARY, name="z")
    Pb_cap = m.addVars(G_b, lb=0.0, name="Pb_cap")
    Eb_cap = m.addVars(G_b, lb=0.0, name="Eb_cap")
    Pch = m.addVars(G_b, T, lb=0.0, name="Pch")
    Pdis = m.addVars(G_b, T, lb=0.0, name="Pdis")
    SoC = m.addVars(G_b, T0, lb=0.0, name="SoC")
    mu_ch = m.addVars(G_b, T, vtype=GRB.BINARY, name="mu_ch")
    mu_dis = m.addVars(G_b, T, vtype=GRB.BINARY, name="mu_dis")

    pv_set, b_set = set(G_pv), set(G_b)
    PVx = lambda j, t: Ppv[j, t] if j in pv_set else 0.0
    QVx = lambda j, t: Qpv[j, t] if j in pv_set else 0.0
    CHx = lambda j, t: Pch[j, t] if j in b_set else 0.0
    DIx = lambda j, t: Pdis[j, t] if j in b_set else 0.0

    # ---- 1-2. Balances nodales (BFM) -------------------------------------------------
    for t in T:
        for j in Np:
            m.addConstr(Pf[j, t] - net.r[j] * l[j, t]
                        == net.PL[j, t] - PVx(j, t) + CHx(j, t) - DIx(j, t)
                        + gp.quicksum(Pf[k, t] for k in ch(j)), name=f"Pbal[{j},{t}]")
            m.addConstr(Qf[j, t] - net.x[j] * l[j, t]
                        == net.QL[j, t] - QVx(j, t)
                        + gp.quicksum(Qf[k, t] for k in ch(j)), name=f"Qbal[{j},{t}]")
        m.addConstr(PS[t] == net.PL[s, t] + gp.quicksum(Pf[k, t] for k in ch(s)), name=f"PS[{t}]")
        m.addConstr(QS[t] == net.QL[s, t] + gp.quicksum(Qf[k, t] for k in ch(s)), name=f"QS[{t}]")

    # ---- 3. Caída de tensión + relajación cónica (cono rotado) --------------------------
    for t in T:
        for j in Np:
            p = net.parent[j]
            m.addConstr(v[j, t] == v[p, t]
                        - 2.0 * (net.r[j] * Pf[j, t] + net.x[j] * Qf[j, t])
                        + (net.r[j] ** 2 + net.x[j] ** 2) * l[j, t], name=f"Vdrop[{j},{t}]")
            m.addConstr(Pf[j, t] * Pf[j, t] + Qf[j, t] * Qf[j, t] <= v[p, t] * l[j, t],
                        name=f"SOC[{j},{t}]")

    # ---- 4. Límites de red (tensión/corriente ya están como bounds) -----------------------
    for t in T:
        m.addQConstr(PS[t] * PS[t] + QS[t] * QS[t] <= cfg.s_sub_max_pu ** 2, name=f"Ssub[{t}]")
        if cfg.p_s_ref_pu is not None:
            m.addConstr(PS[t] >= cfg.p_s_ref_pu, name=f"Prev[{t}]")

    # ---- 5-8. PV -----------------------------------------------------------------------------
    for j in G_pv:
        m.addConstr(Ppv_cap[j] <= w[j] * P_pv_max, name=f"PVcap[{j}]")
        for t in T:
            if cfg.curtailment_allowed:
                m.addConstr(Ppv[j, t] <= alpha[t] * Ppv_cap[j], name=f"PVgen[{j},{t}]")
            else:
                m.addConstr(Ppv[j, t] == alpha[t] * Ppv_cap[j], name=f"PVgen[{j},{t}]")
    m.addConstr(w.sum() <= cfg.n_pv_max, name="PVbudget")

    # ---- 9-20. BESS ------------------------------------------------------------------------------
    for j in G_b:
        m.addConstr(SoC[j, 0] == cfg.kappa_0 * Eb_cap[j], name=f"SoC0[{j}]")
        m.addConstr(SoC[j, cfg.T] >= cfg.kappa_0 * Eb_cap[j], name=f"SoCT[{j}]")
        for t in T:
            m.addConstr(SoC[j, t] == SoC[j, t - 1]
                        + (cfg.eta_ch * Pch[j, t] - Pdis[j, t] / cfg.eta_dis) * dt,
                        name=f"SoCdyn[{j},{t}]")
            m.addConstr(SoC[j, t] >= cfg.kappa_min * Eb_cap[j], name=f"SoCmin[{j},{t}]")
            m.addConstr(SoC[j, t] <= cfg.kappa_max * Eb_cap[j], name=f"SoCmax[{j},{t}]")
            m.addConstr(Pch[j, t] <= Pb_cap[j], name=f"Pch_cap[{j},{t}]")
            m.addConstr(Pch[j, t] <= mu_ch[j, t] * P_b_max, name=f"Pch_mu[{j},{t}]")
            m.addConstr(Pdis[j, t] <= Pb_cap[j], name=f"Pdis_cap[{j},{t}]")
            m.addConstr(Pdis[j, t] <= mu_dis[j, t] * P_b_max, name=f"Pdis_mu[{j},{t}]")
            m.addConstr(mu_ch[j, t] + mu_dis[j, t] <= z[j], name=f"Excl[{j},{t}]")
        m.addConstr(Eb_cap[j] <= z[j] * E_b_max, name=f"Ecap[{j}]")
        m.addConstr(Pb_cap[j] <= z[j] * P_b_max, name=f"Pcap[{j}]")
        m.addConstr(Eb_cap[j] >= cfg.tau_min * Pb_cap[j], name=f"taumin[{j}]")
        m.addConstr(Eb_cap[j] <= cfg.tau_max * Pb_cap[j], name=f"taumax[{j}]")
    if G_b:
        m.addConstr(z.sum() <= cfg.n_bess_max, name="Bbudget")

    # ---- Función objetivo ------------------------------------------------------------------------------
    obj = gp.quicksum(
        gp.quicksum(Ppv[j, t] for j in G_pv)
        - gp.quicksum(cfg.c_deg * Pdis[j, t] for j in G_b)
        - gp.quicksum(net.r[j] * l[j, t] for j in Np)
        for t in T) * dt
    m.setObjective(obj, GRB.MAXIMIZE)

    vars_ = dict(v=v, l=l, Pf=Pf, Qf=Qf, PS=PS, QS=QS, w=w, Ppv_cap=Ppv_cap, Ppv=Ppv,
                 z=z, Pb_cap=Pb_cap, Eb_cap=Eb_cap, Pch=Pch, Pdis=Pdis, SoC=SoC,
                 mu_ch=mu_ch, mu_dis=mu_dis, G_pv=G_pv, G_b=G_b, T=T, T0=T0)
    return m, vars_


# =============================================================================
# 5. RESULTADOS Y VERIFICACIÓN DE LA RELAJACIÓN
# =============================================================================
def extract_results(m: gp.Model, X: dict, net: Network, cfg: HCConfig) -> dict:
    if m.SolCount == 0:
        return {"status": m.Status, "summary": {"status": m.Status, "solution": False}}

    T, Np = X["T"], net.nplus
    G_pv, G_b = X["G_pv"], X["G_b"]
    S, E = cfg.s_base_mva, cfg.s_base_mva
    val = lambda var: var.X

    pv_sites = pd.DataFrame([{
        "bus": j, "w": round(val(X["w"][j])), "P_cap_MW": val(X["Ppv_cap"][j]) * S,
        "E_gen_MWh": sum(val(X["Ppv"][j, t]) for t in T) * S * cfg.dt} for j in G_pv])
    pv_sites = pv_sites[pv_sites["w"] == 1].reset_index(drop=True)

    bess_sites = pd.DataFrame([{
        "bus": j, "z": round(val(X["z"][j])), "P_cap_MW": val(X["Pb_cap"][j]) * S,
        "E_cap_MWh": val(X["Eb_cap"][j]) * E} for j in G_b])
    bess_sites = bess_sites[bess_sites["z"] == 1].reset_index(drop=True) if len(bess_sites) else bess_sites

    volt = pd.DataFrame({j: [np.sqrt(max(val(X["v"][j, t]), 0)) for t in T] for j in net.nodes},
                        index=T)
    volt.index.name = "t"

    sub = pd.DataFrame({"P_S_MW": [val(X["PS"][t]) * S for t in T],
                        "Q_S_MVAr": [val(X["QS"][t]) * S for t in T]}, index=T)
    sub.index.name = "t"

    bess_ops = pd.DataFrame([{
        "bus": j, "t": t, "P_ch_MW": val(X["Pch"][j, t]) * S, "P_dis_MW": val(X["Pdis"][j, t]) * S,
        "SoC_MWh": val(X["SoC"][j, t]) * E}
        for j in bess_sites["bus"] for t in T]) if len(bess_sites) else pd.DataFrame()

    pv_ops = pd.DataFrame([{"bus": j, "t": t, "P_pv_MW": val(X["Ppv"][j, t]) * S}
                           for j in pv_sites["bus"] for t in T]) if len(pv_sites) else pd.DataFrame()

    # Brecha cónica: max | v_pi * l - (P^2 + Q^2) |
    gaps = {(j, t): abs(val(X["v"][net.parent[j], t]) * val(X["l"][j, t])
                        - (val(X["Pf"][j, t]) ** 2 + val(X["Qf"][j, t]) ** 2))
            for j in Np for t in T}
    gap = max(gaps.values())

    losses_MWh = sum(net.r[j] * val(X["l"][j, t]) for j in Np for t in T) * S * cfg.dt
    summary = {
        "status": m.Status, "solution": True, "objective_MWh": m.ObjVal * S,
        "mip_gap": m.MIPGap if m.IsMIP else 0.0,
        "hosting_capacity_PV_MW": float(pv_sites["P_cap_MW"].sum()) if len(pv_sites) else 0.0,
        "BESS_P_MW": float(bess_sites["P_cap_MW"].sum()) if len(bess_sites) else 0.0,
        "BESS_E_MWh": float(bess_sites["E_cap_MWh"].sum()) if len(bess_sites) else 0.0,
        "losses_MWh": losses_MWh, "conic_gap_pu2": gap,
        "conic_exact": gap <= 1e-4, "runtime_s": m.Runtime,
    }
    # Flujos por rama (para graficar cargabilidad)
    i_base_ka = cfg.s_base_mva / (np.sqrt(3.0) * cfg.v_base_kv)
    rows = []
    for j in Np:
        for t in T:
            i_pu = float(np.sqrt(max(val(X["l"][j, t]), 0.0)))
            lim = net.i_max[j]
            rows.append({"from": net.parent[j], "to": j, "t": t,
                         "P_MW": val(X["Pf"][j, t]) * S, "Q_MVAr": val(X["Qf"][j, t]) * S,
                         "I_pu": i_pu, "I_A": i_pu * i_base_ka * 1000.0,
                         "loading_pct": (100.0 * i_pu / lim) if np.isfinite(lim) else None})
    branch_flows = pd.DataFrame(rows)

    # Ubicación por barra (todas las barras, con 0 donde no hay instalación)
    pv_cap = dict(zip(pv_sites["bus"], pv_sites["P_cap_MW"])) if len(pv_sites) else {}
    b_p = dict(zip(bess_sites["bus"], bess_sites["P_cap_MW"])) if len(bess_sites) else {}
    b_e = dict(zip(bess_sites["bus"], bess_sites["E_cap_MWh"])) if len(bess_sites) else {}
    placement = pd.DataFrame([{
        "bus": j, "pv_MW": pv_cap.get(j, 0.0), "bess_MW": b_p.get(j, 0.0),
        "bess_MWh": b_e.get(j, 0.0), "has_pv": j in pv_cap, "has_bess": j in b_p}
        for j in net.nodes])

    gap_by_branch = {j: max(gaps[j, t] for t in T) for j in Np}

    return {"summary": summary, "pv_sites": pv_sites, "bess_sites": bess_sites,
            "placement": placement, "pv_ops": pv_ops, "bess_ops": bess_ops,
            "voltages": volt, "substation": sub, "branch_flows": branch_flows,
            "conic_gap_map": gaps, "conic_gap_by_branch": gap_by_branch, "network": net}


# =============================================================================
# 6. API DE ALTO NIVEL
# =============================================================================
def resolve_results_dir(out_dir: Optional[str] = None) -> Path:
    """Carpeta de salida: argumento > HC_RESULTS_DIR > <raíz_proyecto>/results."""
    if out_dir:
        p = Path(out_dir)
    elif os.environ.get("HC_RESULTS_DIR"):
        p = Path(os.environ["HC_RESULTS_DIR"])
    else:
        p = Path(__file__).resolve().parents[1] / "results"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _jsonable(o):
    """Convierte numpy/pandas/NaN/inf a tipos serializables en JSON."""
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple, set)):
        return [_jsonable(v) for v in o]
    if isinstance(o, pd.DataFrame):
        return _jsonable(o.reset_index().to_dict(orient="records")
                         if o.index.name else o.to_dict(orient="records"))
    if isinstance(o, (np.bool_, bool)):
        return bool(o)
    if isinstance(o, (np.integer, int)):
        return int(o)
    if isinstance(o, (np.floating, float)):
        return float(o) if np.isfinite(o) else None
    if isinstance(o, Path):
        return str(o)
    return o


def _tree_layout(net: Network) -> Tuple[Dict[int, int], Dict[int, float]]:
    """Layout de árbol: x = profundidad, y = posición vertical (hojas equiespaciadas)."""
    depth, y, counter = {net.slack: 0}, {}, [0]

    def dfs(u: int):
        ch = net.children.get(u, [])
        for c in ch:
            depth[c] = depth[u] + 1
            dfs(c)
        if ch:
            y[u] = sum(y[c] for c in ch) / len(ch)
        else:
            y[u] = float(counter[0])
            counter[0] += 1

    dfs(net.slack)
    return depth, y


def build_topology(net: Network, cfg: HCConfig) -> dict:
    """Topología autocontenida (nodos, ramas, layout) para graficar después."""
    depth, y = _tree_layout(net)
    i_base_ka = cfg.s_base_mva / (np.sqrt(3.0) * cfg.v_base_kv)
    S = cfg.s_base_mva
    nodes = [{
        "id": j, "is_slack": j == net.slack, "parent": net.parent.get(j),
        "children": net.children.get(j, []), "v_min": net.v_min[j], "v_max": net.v_max[j],
        "P_load_peak_MW": max(net.PL[j, t] for t in range(1, cfg.T + 1)) * S,
        "layout_x": depth[j], "layout_y": y[j]} for j in net.nodes]
    branches = [{
        "from": net.parent[j], "to": j, "r_pu": net.r[j], "x_pu": net.x[j],
        "i_max_pu": net.i_max[j],
        "i_max_A": net.i_max[j] * i_base_ka * 1000.0} for j in net.nplus]
    loads = {str(j): [net.PL[j, t] * S for t in range(1, cfg.T + 1)] for j in net.nodes}
    return {"slack": net.slack, "n_nodes": len(net.nodes), "nodes": nodes,
            "branches": branches, "P_load_MW_by_node": loads,
            "bases": {"S_base_MVA": cfg.s_base_mva, "V_base_kV": cfg.v_base_kv,
                      "I_base_kA": i_base_ka}}


def save_results(res: dict, cfg: HCConfig, out_dir: Optional[str] = None,
                 filename: Optional[str] = None, save_csv: bool = False) -> Path:
    """
    Guarda UN archivo JSON con config + topología + resultados completos
    (listo para graficar sin volver a resolver). Con save_csv=True además escribe
    CSV por tabla en una subcarpeta con el mismo nombre.
    """
    out = resolve_results_dir(out_dir)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = filename or f"hc_bess_results_m{cfg.month}_{stamp}"
    stem = stem[:-5] if stem.endswith(".json") else stem

    net: Network = res["network"]
    payload = {
        "meta": {"created": datetime.now().isoformat(timespec="seconds"),
                 "gurobi_version": ".".join(map(str, gp.gurobi.version())),
                 "model": "misocp_hc_bess"},
        "config": asdict(cfg),
        "topology": build_topology(net, cfg),
        "summary": res["summary"],
    }
    if res["summary"].get("solution"):
        volt = res["voltages"]
        payload["results"] = {
            "placement": res["placement"],            # por barra: PV/BESS instalados
            "pv_sites": res["pv_sites"],
            "bess_sites": res["bess_sites"],
            "pv_ops": res["pv_ops"],
            "bess_ops": res["bess_ops"],
            "voltages_pu": {"t": list(volt.index), **{str(c): volt[c].tolist() for c in volt.columns}},
            "substation": res["substation"],
            "branch_flows": res["branch_flows"],
            "conic_gap_by_branch": res["conic_gap_by_branch"],
        }

    path = out / f"{stem}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(_jsonable(payload), f, indent=2, ensure_ascii=False)

    if save_csv and res["summary"].get("solution"):
        d = out / stem
        d.mkdir(exist_ok=True)
        tables = {"placement": res["placement"], "pv_sites": res["pv_sites"],
                  "bess_sites": res["bess_sites"], "pv_ops": res["pv_ops"],
                  "bess_ops": res["bess_ops"], "voltages_pu": res["voltages"],
                  "substation": res["substation"], "branch_flows": res["branch_flows"],
                  "topology_nodes": pd.DataFrame(payload["topology"]["nodes"]),
                  "topology_branches": pd.DataFrame(payload["topology"]["branches"])}
        for name, df in tables.items():
            if isinstance(df, pd.DataFrame) and len(df):
                df.to_csv(d / f"{name}.csv", index=bool(df.index.name))
    return path


def load_results(path: str) -> dict:
    """Lee el JSON y devuelve dict con tablas como DataFrames (para graficar)."""
    with open(path, "r", encoding="utf-8") as f:
        d = json.load(f)
    out = {"meta": d["meta"], "config": d["config"], "summary": d["summary"],
           "topology": d["topology"],
           "nodes": pd.DataFrame(d["topology"]["nodes"]),
           "branches": pd.DataFrame(d["topology"]["branches"])}
    for k, v in d.get("results", {}).items():
        if k in ("voltages_pu",):
            out[k] = pd.DataFrame(v).set_index("t")
        elif isinstance(v, list):
            out[k] = pd.DataFrame(v)
        else:
            out[k] = v
    return out


def run_hc_bess(cfg: Optional[HCConfig] = None, save: bool = True,
                out_dir: Optional[str] = None, save_csv: bool = False) -> dict:
    cfg = cfg or HCConfig()
    data_dir = resolve_data_dir(cfg.data_dir)
    nodes, branches = load_grid(data_dir)
    demand = load_demand_profiles(data_dir, cfg.demand_basis, cfg.T)
    alpha = load_pv_profile(data_dir, cfg.T, cfg.month, cfg.alpha_file)
    net = build_network(nodes, branches, demand, cfg)

    model, X = build_model(net, alpha, cfg)
    model.optimize()
    res = extract_results(model, X, net, cfg)
    res.update(model=model, network=net, config=cfg)
    if save:
        res["results_path"] = save_results(res, cfg, out_dir=out_dir, save_csv=save_csv)
    return res


if __name__ == "__main__":
    out = run_hc_bess(HCConfig())
    for k, v_ in out["summary"].items():
        print(f"{k:>26}: {v_}")
    if "pv_sites" in out:
        print("\nPV instalados:\n", out["pv_sites"])
        print("\nBESS instalados:\n", out["bess_sites"])
    print("\nResultados guardados en:", out.get("results_path"))