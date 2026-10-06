import numpy as np
import networkx as nx
import pandapower as pp
import pandapower.networks as pn
import plotly.graph_objects as go
from plotly.colors import sample_colorscale

# ---------------------------------------------------------------- 1. Red radial
net = pn.case33bw()
net.line = net.line.iloc[:32].copy()          # quitar tie-lines
pp.runpp(net, numba=False)

slack = int(net.ext_grid.bus.iloc[0])
G = nx.Graph()
G.add_nodes_from(net.bus.index)
G.add_edges_from((int(l.from_bus), int(l.to_bus)) for l in net.line.itertuples())


# ---------------------------------------------------------------- 2. Layout de árbol
def tree_layout(G, root):
    """x = profundidad; el troncal (rama más larga) va en y=0 y los ramales
    laterales se colocan arriba/abajo en la fila libre más cercana."""
    parent, depth, order = {root: None}, {root: 0}, [root]
    for u in order:
        for v in G[u]:
            if v not in parent:
                parent[v], depth[v] = u, depth[u] + 1
                order.append(v)
    children = {u: [v for v in G[u] if parent.get(v) == u] for u in G}
    height = {}
    for u in reversed(order):
        height[u] = 1 + max((height[c] for c in children[u]), default=0)

    pos, occupied, queue = {}, {}, []

    def free(row, x0, x1):
        return all(x1 < a - 0.5 or x0 > b + 0.5 for a, b in occupied.get(row, []))

    def place_chain(start, row):
        occupied.setdefault(row, []).append((depth[start], depth[start] + height[start] - 1))
        u = start
        while True:
            pos[u] = (depth[u], row)
            kids = sorted(children[u], key=lambda c: -height[c])
            if not kids:
                break
            queue.extend((c, row) for c in kids[1:])     # ramales laterales
            u = kids[0]                                  # el troncal sigue recto

    place_chain(root, 0)
    while queue:
        start, prow = queue.pop(0)
        x0, x1 = depth[start], depth[start] + height[start] - 1
        for k in [1, -1, 2, -2, 3, -3, 4, -4]:
            if free(prow + k, x0, x1):
                place_chain(start, prow + k)
                break
    return pos


pos = tree_layout(G, slack)
x = {b: pos[b][0] for b in G}
y = {b: pos[b][1] * 1.6 for b in G}          # separar un poco las filas


# ---------------------------------------------------------------- 3. Figura
def colors(vals, vmin, vmax, scale="RdYlGn_r"):
    f = np.clip((np.asarray(vals, float) - vmin) / (vmax - vmin), 0, 1)
    return sample_colorscale(scale, list(f))

res_l = net.res_line
if net.line["max_i_ka"].notna().all():
    load_pct = res_l["loading_percent"]
else:
    load_pct = 100 * res_l["i_ka"] / res_l["i_ka"].max()

lcol = colors(load_pct.values, 0, 100)
fig = go.Figure()

# Ramas (una traza por rama para colorearlas individualmente)
for k, (idx, l) in enumerate(net.line.iterrows()):
    a, b = int(l.from_bus), int(l.to_bus)
    fig.add_trace(go.Scatter(x=[x[a], x[b]], y=[y[a], y[b]], mode="lines",
                             line=dict(color=lcol[k], width=4),
                             hoverinfo="skip", showlegend=False))

# Puntos medios de rama: hover + barra de color
xm = [(x[int(l.from_bus)] + x[int(l.to_bus)]) / 2 for _, l in net.line.iterrows()]
ym = [(y[int(l.from_bus)] + y[int(l.to_bus)]) / 2 for _, l in net.line.iterrows()]
fig.add_trace(go.Scatter(
    x=xm, y=ym, mode="markers", showlegend=False,
    marker=dict(size=7, symbol="diamond", color=load_pct.values, colorscale="RdYlGn_r",
                cmin=0, cmax=100, line=dict(width=0.5, color="white"),
                colorbar=dict(title="Cargabilidad [%]", x=1.01, len=0.45, y=0.2, thickness=12)),
    hovertext=[f"<b>Rama {int(l.from_bus)+1}→{int(l.to_bus)+1}</b><br>"
               f"{load_pct[i]:.1f}% · I = {res_l.i_ka[i]*1000:.0f} A"
               for i, l in net.line.iterrows()], hoverinfo="text"))

# Barras coloreadas por tensión
non_slack = [b for b in net.bus.index if b != slack]
vm = net.res_bus.vm_pu
fig.add_trace(go.Scatter(
    x=[x[b] for b in non_slack], y=[y[b] for b in non_slack],
    mode="markers+text", name="Barras",
    text=[str(b + 1) for b in non_slack], textposition="middle center",
    textfont=dict(size=8, color="black"),
    marker=dict(size=19, color=[vm[b] for b in non_slack],
                colorscale=[[0, "#d73027"], [0.25, "#fdae61"], [0.5, "#1a9850"],
                            [0.75, "#fdae61"], [1, "#d73027"]],
                cmin=1 - 0.1, cmax=1 + 0.1,
                line=dict(width=1.2, color="#333"),
                colorbar=dict(title="Tensión [p.u.]", x=1.01, len=0.45, y=0.75, thickness=12)),
    hovertext=[f"<b>Barra {b+1}</b><br>V = {vm[b]:.4f} p.u." for b in non_slack],
    hoverinfo="text"))

# Subestación
fig.add_trace(go.Scatter(
    x=[x[slack]], y=[y[slack]], mode="markers+text", name="Subestación (slack)",
    text=[str(slack + 1)], textposition="middle center",
    textfont=dict(color="white", size=9),
    marker=dict(size=28, symbol="square", color="#d62728", line=dict(width=1.5, color="#333"))))

xs, ys = list(x.values()), list(y.values())
fig.update_layout(
    title="Topología Radial IEEE 33-bus",
    plot_bgcolor="white", paper_bgcolor="white", width=1500, height=600,
    xaxis=dict(visible=False, range=[min(xs) - 0.7, max(xs) + 0.9]),
    yaxis=dict(visible=False, range=[min(ys) - 1.2, max(ys) + 1.2]),
    legend=dict(orientation="h", y=1.0, x=0.0, yanchor="bottom"),
    margin=dict(l=20, r=20, t=80, b=20), hovermode="closest")

fig.show()