"""
plot_results.py
===============
Graficación de los resultados del modelo MISOCP de Hosting Capacity (PV + BESS).

Lee el JSON generado por `save_results()` de misocp_hc_bess.py, por lo que:
  * NO necesita Gurobi ni pandapower (solo pandas, numpy y plotly).
  * Usa el MISMO layout de árbol y los MISMOS ids de barra del modelo
    (el código anterior con pandapower reordenaba y renumeraba las barras).

Figuras
-------
1. Topología interactiva (HTML):
     - Barras coloreadas por tensión (p.u.)
     - Ramas coloreadas por cargabilidad (% de I_max)
     - PV (estrella amarilla, tamaño ~ MW) y BESS (cuadrado azul, tamaño ~ MWh)
     - Control deslizante: "Peor caso" + cada hora t = 1..T (con botón Play)
2. Dashboard operativo (HTML):
     - Envolvente de tensiones, balance de potencia (demanda / PV / subestación),
       PV por sitio, potencia y SoC del BESS, mapa de calor de cargabilidad.

Uso
---
    # desde la terminal, en la carpeta del proyecto (usa el JSON más reciente de results/)
    python plot_results.py
    python plot_results.py results/hc_bess_results_m7_20260101_120000.json

    # desde Python, justo después de optimizar
    from misocp_hc_bess import HCConfig, run_hc_bess
    from plot_results import plot_all
    out = run_hc_bess(HCConfig(month=7))
    plot_all(out["results_path"])
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Dict, Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.colors import sample_colorscale
from plotly.subplots import make_subplots

# Paleta
C_PV = "#f2b705"
C_BESS = "#1f77b4"
C_SLACK = "#d62728"
C_GRID = "#9aa0a6"
# Rojo (bajo) -> verde (1.0 p.u.) -> rojo (alto)
V_SCALE = [[0.0, "#d73027"], [0.25, "#fdae61"], [0.5, "#1a9850"],
           [0.75, "#fdae61"], [1.0, "#d73027"]]


# =============================================================================
# 1. CARGA DEL JSON (sin depender de gurobipy)
# =============================================================================
def load_results(path: str | Path) -> Dict:
    with open(path, "r", encoding="utf-8") as f:
        d = json.load(f)
    if "results" not in d:
        raise ValueError("El JSON no contiene 'results' (el modelo no halló solución).")

    r = d["results"]
    volt = pd.DataFrame(r["voltages_pu"]).set_index("t")
    volt.columns = [int(c) for c in volt.columns]

    out = {
        "config": d["config"],
        "summary": d["summary"],
        "topology": d["topology"],
        "nodes": pd.DataFrame(d["topology"]["nodes"]).set_index("id", drop=False),
        "branches": pd.DataFrame(d["topology"]["branches"]),
        "voltages": volt,
        "placement": pd.DataFrame(r["placement"]).set_index("bus", drop=False),
        "pv_sites": pd.DataFrame(r["pv_sites"]),
        "bess_sites": pd.DataFrame(r["bess_sites"]),
        "pv_ops": pd.DataFrame(r["pv_ops"]),
        "bess_ops": pd.DataFrame(r["bess_ops"]),
        "substation": pd.DataFrame(r["substation"]).set_index("t"),
        "flows": pd.DataFrame(r["branch_flows"]),
        "loads": {int(k): v for k, v in d["topology"]["P_load_MW_by_node"].items()},
    }

    # Métrica de cargabilidad por rama: % de I_max; si no hay límite, corriente relativa
    fl = out["flows"]
    if fl["loading_pct"].notna().any():
        fl["load_metric"] = fl["loading_pct"]
        out["load_label"] = "Cargabilidad [% I_max]"
    else:
        fl["load_metric"] = 100.0 * fl["I_A"] / fl["I_A"].max()
        out["load_label"] = "Corriente relativa [% del máx.]"
    return out


def resolve_results_dir(results_dir: Optional[str | Path] = None) -> Path:
    """Carpeta de resultados, sin rutas absolutas. Orden de búsqueda:
         1. argumento results_dir
         2. variable de entorno HC_RESULTS_DIR
         3. <carpeta de este archivo>/results
         4. <carpeta padre de este archivo>/results   (si este archivo está en /models)
         5. ./results  (directorio de trabajo actual)
    """
    here = Path(__file__).resolve().parent
    candidates = []
    if results_dir:
        candidates.append(Path(results_dir))
    if os.environ.get("HC_RESULTS_DIR"):
        candidates.append(Path(os.environ["HC_RESULTS_DIR"]))
    candidates += [here / "results", here.parent / "results", Path.cwd() / "results"]
    for c in candidates:
        if c.is_dir():
            return c
    raise FileNotFoundError(
        "No se encontró la carpeta 'results'. Pasa el JSON como argumento o define "
        f"HC_RESULTS_DIR. Probé: {[str(c) for c in candidates]}")


def latest_results_file(results_dir: Optional[str | Path] = None) -> Path:
    d = resolve_results_dir(results_dir)
    files = sorted(d.glob("hc_bess_results_*.json"), key=lambda p: p.stat().st_mtime)
    if not files:
        raise FileNotFoundError(f"No hay archivos hc_bess_results_*.json en '{d}'.")
    return files[-1]


# =============================================================================
# 2. FIGURA DE TOPOLOGÍA
# =============================================================================
def _color(values, vmin, vmax, scale="RdYlGn_r"):
    """Valores -> colores rgb (para pintar ramas una a una)."""
    frac = np.clip((np.asarray(values, float) - vmin) / (vmax - vmin), 0, 1)
    return sample_colorscale(scale, list(frac))


def plot_topology(R: Dict, html_path: Optional[str | Path] = None) -> go.Figure:
    nodes, cfg, S = R["nodes"], R["config"], R["summary"]
    volt, fl, plc = R["voltages"], R["flows"], R["placement"]
    T = list(volt.index)
    slack = R["topology"]["slack"]
    x = nodes["layout_x"].to_dict()
    y = nodes["layout_y"].to_dict()
    ids = list(nodes.index)

    # ---- Tablas bus/rama x tiempo ------------------------------------------------
    load_tab = fl.pivot(index="to", columns="t", values="load_metric")
    I_tab = fl.pivot(index="to", columns="t", values="I_A")
    br = R["branches"].set_index("to", drop=False)
    br_ids = list(br.index)

    v_lo = min(cfg["v_min"], float(volt.min().min()))
    v_hi = max(cfg["v_max"], float(volt.max().max()))
    v_center = cfg["v_slack"]
    half = max(v_center - v_lo, v_hi - v_center, 1e-3)
    cmin, cmax = v_center - half, v_center + half

    # ---- Estados: "peor caso" + cada hora ----------------------------------------
    def state(t=None):
        if t is None:
            v = volt.min(axis=0)                       # tensión mínima de cada barra
            v_t = volt.idxmin(axis=0)
            lm = load_tab.max(axis=1)                  # cargabilidad máxima de cada rama
            lm_t = load_tab.idxmax(axis=1)
            Ia = I_tab.max(axis=1)
            v_txt = {j: f"V mín = {v[j]:.4f} p.u. (t={v_t[j]})" for j in ids}
            l_txt = {j: f"{lm[j]:.1f}% (t={lm_t[j]}) · I = {Ia[j]:.0f} A" for j in br_ids}
        else:
            v = volt.loc[t]
            lm = load_tab[t]
            Ia = I_tab[t]
            v_txt = {j: f"V = {v[j]:.4f} p.u." for j in ids}
            l_txt = {j: f"{lm[j]:.1f}% · I = {Ia[j]:.0f} A" for j in br_ids}
        node_hover = []
        for j in ids:
            row = nodes.loc[j]
            extra = ""
            if plc.at[j, "has_pv"]:
                extra += f"<br><b>PV</b>: {plc.at[j, 'pv_MW']:.3f} MW"
            if plc.at[j, "has_bess"]:
                extra += (f"<br><b>BESS</b>: {plc.at[j, 'bess_MW']*1000:.0f} kW / "
                          f"{plc.at[j, 'bess_MWh']*1000:.0f} kWh")
            node_hover.append(f"<b>Barra {j}</b><br>{v_txt[j]}<br>"
                              f"Carga pico: {row['P_load_peak_MW']*1000:.0f} kW{extra}")
        br_hover = [f"<b>Rama {br.at[j, 'from']}→{j}</b><br>{l_txt[j]}" for j in br_ids]
        return dict(v=[float(v[j]) for j in ids], lm=[float(lm[j]) for j in br_ids],
                    node_hover=node_hover, br_hover=br_hover)

    st0 = state(None)
    lcol0 = _color(st0["lm"], 0, 100)

    # ---- Trazas ---------------------------------------------------------------------
    fig = go.Figure()

    # (0..nb-1) ramas, una traza por rama para poder colorearlas individualmente
    for k, j in enumerate(br_ids):
        a = br.at[j, "from"]
        fig.add_trace(go.Scatter(
            x=[x[a], x[j]], y=[y[a], y[j]], mode="lines",
            line=dict(color=lcol0[k], width=4), hoverinfo="skip", showlegend=False))
    nb = len(br_ids)

    # (nb) puntos medios de rama: hover + barra de color de cargabilidad
    xm = [(x[br.at[j, "from"]] + x[j]) / 2 for j in br_ids]
    ym = [(y[br.at[j, "from"]] + y[j]) / 2 for j in br_ids]
    i_mid = len(fig.data)
    fig.add_trace(go.Scatter(
        x=xm, y=ym, mode="markers", name="Ramas",
        marker=dict(size=7, symbol="diamond", color=st0["lm"], colorscale="RdYlGn_r",
                    cmin=0, cmax=100, line=dict(width=0.5, color="white"),
                    colorbar=dict(title=R["load_label"], x=1.01, len=0.45, y=0.2,
                                  thickness=12)),
        hovertext=st0["br_hover"], hoverinfo="text", showlegend=False))

    # conectores punteados barra -> PV / BESS
    dy = 0.45
    seg_x, seg_y = [], []
    pv_buses = list(R["pv_sites"]["bus"]) if len(R["pv_sites"]) else []
    be_buses = list(R["bess_sites"]["bus"]) if len(R["bess_sites"]) else []
    for j in pv_buses:
        seg_x += [x[j], x[j], None]; seg_y += [y[j], y[j] + dy, None]
    for j in be_buses:
        seg_x += [x[j], x[j], None]; seg_y += [y[j], y[j] - dy, None]
    fig.add_trace(go.Scatter(x=seg_x, y=seg_y, mode="lines", hoverinfo="skip",
                             line=dict(color="#555", width=1.2, dash="dot"),
                             showlegend=False))

    # barras (coloreadas por tensión)
    non_slack = [j for j in ids if j != slack]
    i_nodes = len(fig.data)
    pos = {j: k for k, j in enumerate(ids)}
    fig.add_trace(go.Scatter(
        x=[x[j] for j in non_slack], y=[y[j] for j in non_slack],
        mode="markers+text", name="Barras",
        text=[str(j) for j in non_slack], textposition="middle center",
        textfont=dict(size=8, color="black"),
        marker=dict(size=19, color=[st0["v"][pos[j]] for j in non_slack],
                    colorscale=V_SCALE, cmin=cmin, cmax=cmax,
                    line=dict(width=1.2, color="#333"),
                    colorbar=dict(title="Tensión [p.u.]", x=1.01, len=0.45, y=0.75,
                                  thickness=12)),
        hovertext=[st0["node_hover"][pos[j]] for j in non_slack], hoverinfo="text"))

    # subestación
    fig.add_trace(go.Scatter(
        x=[x[slack]], y=[y[slack]], mode="markers+text", name="Subestación (slack)",
        text=[str(slack)], textposition="middle center", textfont=dict(color="white", size=9),
        marker=dict(size=28, symbol="square", color=C_SLACK, line=dict(width=1.5, color="#333")),
        hovertext=[st0["node_hover"][pos[slack]]], hoverinfo="text"))

    # PV
    if pv_buses:
        s = R["pv_sites"].set_index("bus")
        pmax = max(s["P_cap_MW"].max(), 1e-9)
        fig.add_trace(go.Scatter(
            x=[x[j] for j in pv_buses], y=[y[j] + dy for j in pv_buses],
            mode="markers+text", name="PV instalado",
            text=[f"{s.at[j, 'P_cap_MW']:.2f} MW" for j in pv_buses], textposition="top center",
            textfont=dict(size=10, color="#7a5c00"),
            marker=dict(symbol="star", color=C_PV, line=dict(width=1.2, color="#333"),
                        size=[20 + 22 * s.at[j, "P_cap_MW"] / pmax for j in pv_buses]),
            hovertext=[f"<b>PV en barra {j}</b><br>{s.at[j, 'P_cap_MW']:.3f} MW"
                       f"<br>Energía: {s.at[j, 'E_gen_MWh']:.2f} MWh/día" for j in pv_buses],
            hoverinfo="text"))

    # BESS
    if be_buses:
        b = R["bess_sites"].set_index("bus")
        emax = max(b["E_cap_MWh"].max(), 1e-9)
        fig.add_trace(go.Scatter(
            x=[x[j] for j in be_buses], y=[y[j] - dy for j in be_buses],
            mode="markers+text", name="BESS instalado",
            text=[f"{b.at[j, 'P_cap_MW']*1000:.0f} kW / {b.at[j, 'E_cap_MWh']*1000:.0f} kWh"
                  for j in be_buses], textposition="bottom center",
            textfont=dict(size=10, color="#0b3d66"),
            marker=dict(symbol="square", color=C_BESS, line=dict(width=1.2, color="#333"),
                        size=[16 + 14 * b.at[j, "E_cap_MWh"] / emax for j in be_buses]),
            hovertext=[f"<b>BESS en barra {j}</b><br>{b.at[j, 'P_cap_MW']*1000:.1f} kW"
                       f"<br>{b.at[j, 'E_cap_MWh']*1000:.1f} kWh" for j in be_buses],
            hoverinfo="text"))

    # ---- Frames (una por hora) ----------------------------------------------------------
    def frame_for(label, t):
        st = state(t)
        lcol = _color(st["lm"], 0, 100)
        data = [go.Scatter(line=dict(color=lcol[k])) for k in range(nb)]
        data.append(go.Scatter(marker=dict(color=st["lm"]), hovertext=st["br_hover"]))
        data.append(go.Scatter(marker=dict(color=[st["v"][pos[j]] for j in non_slack]),
                               hovertext=[st["node_hover"][pos[j]] for j in non_slack]))
        idx = list(range(nb)) + [i_mid, i_nodes]
        return go.Frame(data=data, traces=idx, name=label)

    labels = ["Peor caso"] + [f"t={t}" for t in T]
    frames = [frame_for("Peor caso", None)] + [frame_for(f"t={t}", t) for t in T]
    fig.frames = frames

    play = dict(label="▶ Play", method="animate",
                args=[None, {"frame": {"duration": 700, "redraw": True},
                             "transition": {"duration": 0}, "fromcurrent": True}])
    pause = dict(label="⏸", method="animate",
                 args=[[None], {"frame": {"duration": 0, "redraw": False},
                                "mode": "immediate", "transition": {"duration": 0}}])
    sliders = [dict(
        active=0, x=0.08, len=0.85, y=-0.02, currentvalue=dict(prefix="Vista: "),
        steps=[dict(label=lb, method="animate",
                    args=[[lb], {"mode": "immediate", "frame": {"duration": 0, "redraw": True},
                                 "transition": {"duration": 0}}]) for lb in labels])]

    resumen = (f"HC PV = {S['hosting_capacity_PV_MW']:.2f} MW · BESS = {S['BESS_P_MW']*1000:.0f} kW / "
               f"{S['BESS_E_MWh']*1000:.0f} kWh · Pérdidas = {S['losses_MWh']*1000:.1f} kWh · "
               f"Obj = {S['objective_MWh']:.3f} MWh · gap MIP = {S['mip_gap']*100:.2f}% · "
               f"cónica exacta: {'sí' if S['conic_exact'] else 'NO'}")
    xs = [x[j] for j in ids]; ys = [y[j] for j in ids]
    fig.update_layout(
        title=dict(text=f"Topología IEEE 33-bus — resultado de la optimización<br>"
                        f"<sup>{resumen}</sup>", x=0.01),
        plot_bgcolor="white", paper_bgcolor="white", width=1500, height=720,
        xaxis=dict(visible=False, range=[min(xs) - 0.7, max(xs) + 0.9]),
        yaxis=dict(visible=False, range=[min(ys) - 1.2, max(ys) + 1.2]),
        legend=dict(orientation="h", y=1.0, x=0.0, yanchor="bottom"),
        updatemenus=[dict(type="buttons", direction="left", x=0.0, y=-0.02,
                          xanchor="left", yanchor="top", buttons=[play, pause])],
        sliders=sliders, margin=dict(l=20, r=20, t=100, b=70), hovermode="closest")

    if html_path:
        fig.write_html(str(html_path), include_plotlyjs="cdn")
    return fig


# =============================================================================
# 3. DASHBOARD OPERATIVO
# =============================================================================
def plot_dashboard(R: Dict, html_path: Optional[str | Path] = None) -> go.Figure:
    cfg, volt, sub = R["config"], R["voltages"], R["substation"]
    pv_ops, be_ops, fl = R["pv_ops"], R["bess_ops"], R["flows"]
    T = list(volt.index)

    fig = make_subplots(
        rows=3, cols=2, vertical_spacing=0.10, horizontal_spacing=0.08,
        subplot_titles=("Envolvente de tensiones", "Balance de potencia",
                        "Generación PV por barra", "Potencia BESS (+ descarga / − carga)",
                        "Estado de carga BESS (SoC)", "Cargabilidad de ramas [% I_max]"))

    # (1,1) tensiones
    vmin, vmax, vmean = volt.min(axis=1), volt.max(axis=1), volt.mean(axis=1)
    fig.add_trace(go.Scatter(x=T, y=vmax, line=dict(width=0), showlegend=False,
                             hoverinfo="skip"), 1, 1)
    fig.add_trace(go.Scatter(x=T, y=vmin, fill="tonexty", fillcolor="rgba(31,119,180,0.2)",
                             line=dict(width=0), name="Rango entre barras"), 1, 1)
    fig.add_trace(go.Scatter(x=T, y=vmean, name="V media", line=dict(color=C_BESS)), 1, 1)
    fig.add_trace(go.Scatter(x=T, y=vmin, name="V mín", line=dict(color="#d62728", dash="dot")), 1, 1)
    for lim in (cfg["v_min"], cfg["v_max"]):
        fig.add_hline(y=lim, line=dict(color="gray", dash="dash", width=1), row=1, col=1)
    fig.update_yaxes(title_text="p.u.", row=1, col=1)

    # (1,2) balance de potencia
    demanda = np.sum([np.array(v) for v in R["loads"].values()], axis=0)
    pv_tot = (pv_ops.groupby("t")["P_pv_MW"].sum().reindex(T, fill_value=0.0)
              if len(pv_ops) else pd.Series(0.0, index=T))
    fig.add_trace(go.Scatter(x=T, y=demanda, name="Demanda total", line=dict(color="#444")), 1, 2)
    fig.add_trace(go.Scatter(x=T, y=pv_tot, name="PV total", fill="tozeroy",
                             line=dict(color=C_PV), fillcolor="rgba(242,183,5,0.3)"), 1, 2)
    fig.add_trace(go.Scatter(x=T, y=sub["P_S_MW"], name="P subestación",
                             line=dict(color=C_SLACK, width=3)), 1, 2)
    fig.add_trace(go.Scatter(x=T, y=sub["Q_S_MVAr"], name="Q subestación",
                             line=dict(color=C_SLACK, dash="dash")), 1, 2)
    fig.update_yaxes(title_text="MW / MVAr", row=1, col=2)

    # (2,1) PV por barra (apilado)
    if len(pv_ops):
        for bus, g in pv_ops.groupby("bus"):
            fig.add_trace(go.Scatter(x=g["t"], y=g["P_pv_MW"], stackgroup="pv",
                                     name=f"PV barra {bus}"), 2, 1)
    fig.update_yaxes(title_text="MW", row=2, col=1)

    # (2,2) potencia BESS y (3,1) SoC
    if len(be_ops):
        cap = R["bess_sites"].set_index("bus")["E_cap_MWh"]
        for bus, g in be_ops.groupby("bus"):
            fig.add_trace(go.Bar(x=g["t"], y=g["P_dis_MW"] * 1000, name=f"Desc. barra {bus}",
                                 marker_color=C_BESS, legendgroup=f"b{bus}"), 2, 2)
            fig.add_trace(go.Bar(x=g["t"], y=-g["P_ch_MW"] * 1000, name=f"Carga barra {bus}",
                                 marker_color="#ff7f0e", legendgroup=f"b{bus}"), 2, 2)
            fig.add_trace(go.Scatter(x=[0] + list(g["t"]),
                                     y=[None] + list(100 * g["SoC_MWh"] / cap[bus]),
                                     name=f"SoC barra {bus}", mode="lines+markers"), 3, 1)
        for lim in (cfg["kappa_min"] * 100, cfg["kappa_max"] * 100):
            fig.add_hline(y=lim, line=dict(color="gray", dash="dash", width=1), row=3, col=1)
        fig.update_layout(barmode="relative")
    fig.update_yaxes(title_text="kW", row=2, col=2)
    fig.update_yaxes(title_text="% de E_cap", row=3, col=1)

    # (3,2) mapa de calor de cargabilidad
    tab = fl.pivot(index="to", columns="t", values="load_metric")
    lbl = [f"{int(f)}→{int(t_)}" for f, t_ in
           R["branches"].set_index("to").loc[tab.index, "from"].items()]
    fig.add_trace(go.Heatmap(z=tab.values, x=T, y=lbl, colorscale="RdYlGn_r", zmin=0, zmax=100,
                             colorbar=dict(title="%", len=0.28, y=0.12, thickness=12)), 3, 2)

    for r_ in (1, 2, 3):
        for c_ in (1, 2):
            fig.update_xaxes(title_text="hora t", row=r_, col=c_)
    fig.update_layout(height=1100, width=1500, template="plotly_white",
                      title="Dashboard operativo — PV + BESS",
                      legend=dict(orientation="h", y=-0.05), hovermode="x unified")
    fig.update_yaxes(autorange="reversed", row=3, col=2)

    if html_path:
        fig.write_html(str(html_path), include_plotlyjs="cdn")
    return fig


# =============================================================================
# 4. API DE ALTO NIVEL / CLI
# =============================================================================
def plot_all(json_path: Optional[str | Path] = None, out_dir: Optional[str | Path] = None,
             show: bool = False):
    """Genera topología + dashboard.
    json_path=None -> usa el JSON más reciente de la carpeta results (autodetectada).
    out_dir=None   -> guarda los HTML en <results>/figures."""
    json_path = Path(json_path).expanduser() if json_path else latest_results_file()
    if not json_path.is_file():                      # ruta relativa a results/ o a este archivo
        for base in (resolve_results_dir(), Path(__file__).resolve().parent):
            if (base / json_path).is_file():
                json_path = base / json_path
                break
        else:
            raise FileNotFoundError(f"No existe el archivo: {json_path}")
    out_dir = Path(out_dir) if out_dir else json_path.parent / "figures"
    out_dir.mkdir(parents=True, exist_ok=True)
    R = load_results(json_path)
    p1 = out_dir / f"{json_path.stem}_topologia.html"
    p2 = out_dir / f"{json_path.stem}_dashboard.html"
    f1 = plot_topology(R, p1)
    f2 = plot_dashboard(R, p2)
    print(f"Resultados leídos: {json_path}\nTopología: {p1}\nDashboard: {p2}")
    if show:
        import webbrowser
        for p in (p1, p2):
            webbrowser.open(p.resolve().as_uri())
    return f1, f2


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Grafica resultados del MISOCP HC PV+BESS")
    ap.add_argument("json", nargs="?",
                    help="JSON de resultados (por defecto, el más reciente en la carpeta results)")
    ap.add_argument("--out", help="carpeta de salida de los HTML (por defecto <results>/figures)")
    ap.add_argument("--no-show", action="store_true", help="no abrir el navegador")
    a = ap.parse_args()
    plot_all(a.json, a.out, show=not a.no_show)