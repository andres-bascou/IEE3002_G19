"""
presentacion/graficos_avance.py
===============================
Genera las figuras para presentar el avance del proyecto (datos, Etapa 1 y hallazgos
PRELIMINARES de la Etapa 2) en results/figures/avance/, en PNG (200 dpi, diapositivas)
y PDF (vectorial, informe LaTeX).

Todo se recalcula desde el repositorio:
  * datos de data/grid, data/demand y data/pv_profiles;
  * Etapa 1 con las funciones de verificacion/etapa1_caso_base.py;
  * Etapa 2 (PRELIMINAR) con verificacion/preliminar_tabla1.py.

Uso (desde cualquier carpeta; requiere el entorno del proyecto, ver README):
    .venv/bin/python presentacion/graficos_avance.py
"""
import os
import sys
from collections import defaultdict, deque

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import FancyBboxPatch, Rectangle  # noqa: E402

# OJO: NO usar rutas absolutas (p.ej. r"C:\Users\..." o "/Users/..."): solo funcionan en un PC.
# Se resuelve la raíz del proyecto relativa a este archivo (<raíz>/<carpeta>/este_script.py).
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # raíz del proyecto
DATA_DIR = os.path.join(BASE_DIR, "data")
OUT_DIR = os.path.join(BASE_DIR, "results", "figures", "avance")
sys.path.insert(0, BASE_DIR)

from verificacion import preliminar_tabla1 as pt1  # noqa: E402
from verificacion.etapa1_caso_base import (I_BASE_KA, S_BASE, TOL_GAP_ABS_INFORME,  # noqa: E402
                                           TOL_GAP_REL, TOL_I_REL, TOL_LOSS_REL, TOL_V_PU,
                                           modelo_produccion, referencia_pandapower,
                                           socp_independiente)

# =============================================================================
# ESTILO (paleta validada con el validador de la skill dataviz; modo claro)
# =============================================================================
SUP = "#fcfcfb"        # superficie del gráfico
TINTA = "#0b0b0b"      # texto principal
TINTA2 = "#52514e"     # texto secundario / referencia neutra
TENUE = "#898781"      # etiquetas de ejes, contexto
GRILLA = "#e1e0d9"     # líneas de grilla
EJE = "#c3c2b7"        # ejes y ramas de la red
CRITICO = "#d03b3b"    # estado "fuera de tolerancia" (siempre con etiqueta)

AZUL, NARANJA, AQUA, AMARILLO = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"   # slots 1-4
COLOR_TIPO = {"regulados": AZUL, "pequenas": NARANJA, "grandes": AQUA}
NOMBRE_TIPO = {"regulados": "Clientes regulados", "pequenas": "Pequeñas empresas",
               "grandes": "Grandes empresas"}
C_MODELO, C_PROBLEMA, C_REF = AZUL, NARANJA, TINTA2   # modelo verificado / caso problemático / referencia

plt.rcParams.update({
    "font.family": "sans-serif", "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
    "mathtext.fontset": "custom", "mathtext.rm": "Arial", "mathtext.it": "Arial:italic",
    "mathtext.bf": "Arial:bold",
    "font.size": 12, "axes.titlesize": 13, "axes.labelsize": 12, "legend.fontsize": 11,
    "xtick.labelsize": 11, "ytick.labelsize": 11,
    "figure.facecolor": SUP, "axes.facecolor": SUP, "savefig.facecolor": SUP,
    "axes.edgecolor": EJE, "axes.linewidth": 0.8, "axes.labelcolor": TINTA2,
    "axes.titlecolor": TINTA, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRILLA, "grid.linewidth": 0.7, "grid.linestyle": "-",
    "axes.axisbelow": True, "xtick.color": EJE, "ytick.color": EJE,
    "xtick.labelcolor": TINTA2, "ytick.labelcolor": TINTA2,
    "legend.frameon": False, "text.color": TINTA,
    "lines.linewidth": 2.0, "lines.solid_capstyle": "round", "lines.solid_joinstyle": "round",
    "pdf.fonttype": 42,
})
FIG_ANCHO = (11.0, 6.0)   # proporción de diapositiva


def encabezado(fig, titulo: str, subtitulo: str = "", preliminar: bool = False):
    """Título como afirmación (la conclusión) + subtítulo con el contexto."""
    if preliminar:
        titulo = "PRELIMINAR · " + titulo
    fig.text(0.02, 0.975, titulo, ha="left", va="top", fontsize=16, fontweight="bold", color=TINTA)
    if subtitulo:
        fig.text(0.02, 0.918, subtitulo, ha="left", va="top", fontsize=11.5, color=TINTA2,
                 linespacing=1.35)


def nota(fig, texto: str):
    fig.text(0.02, 0.012, texto, ha="left", va="bottom", fontsize=9.5, color=TENUE)


def guardar(fig, nombre: str):
    os.makedirs(OUT_DIR, exist_ok=True)
    fig.savefig(os.path.join(OUT_DIR, f"{nombre}.png"), dpi=200)
    fig.savefig(os.path.join(OUT_DIR, f"{nombre}.pdf"))
    plt.close(fig)
    print(f"  {nombre}.png / .pdf")


def kw(x: float) -> str:
    """Formato de potencia con separador de miles fino: 11818 -> '11 818'."""
    return f"{x:,.0f}".replace(",", "\u2009")


def sci(x: float) -> str:
    """Notación científica en mathtext: 3.2e-12 -> 3.2×10⁻¹²."""
    if x == 0:
        return "0"
    e = int(np.floor(np.log10(abs(x))))
    m = x / 10 ** e
    return rf"${m:.1f}\times10^{{{e}}}$" if round(m, 1) != 1.0 else rf"$10^{{{e}}}$"


def linea_limite(ax, valor, texto, orient="h", pos=0.99, ha="right", va="bottom", **kw_):
    """Línea de límite técnico (discontinua, porque ES un umbral) con su etiqueta."""
    est = dict(color=TINTA2, lw=1.2, ls=(0, (5, 3)), zorder=2)
    est.update(kw_)
    if orient == "h":
        ax.axhline(valor, **est)
        ax.text(pos, valor, " " + texto + " ", transform=ax.get_yaxis_transform(), ha=ha,
                va=va, fontsize=10.5, color=TINTA2)
    else:
        ax.axvline(valor, **est)
        ax.text(valor, pos, " " + texto, transform=ax.get_xaxis_transform(), ha="left",
                va="top", fontsize=10.5, color=TINTA2)


def barras_redondeadas(ax, xs, hs, ancho, color, radio_px=4.0):
    """Barras verticales con extremo de datos redondeado (4 px) y base recta (spec dataviz).
    Llamar después de fijar los límites de los ejes."""
    ax.figure.canvas.draw()
    bb = ax.get_window_extent()
    (x0, x1), (y0, y1) = ax.get_xlim(), ax.get_ylim()
    dx, dy = (x1 - x0) / bb.width, (y1 - y0) / bb.height     # unidades de datos por pixel
    r = radio_px * dx
    for x, h in zip(xs, hs):
        ax.add_patch(FancyBboxPatch((x - ancho / 2, 0), ancho, h, mutation_aspect=dy / dx,
                                    boxstyle=f"round,pad=0,rounding_size={r}",
                                    fc=color, ec="none", zorder=3))
        ax.add_patch(Rectangle((x - ancho / 2, 0), ancho, max(h - radio_px * dy, 0),
                               fc=color, ec="none", zorder=3))


# =============================================================================
# TOPOLOGÍA: layout de árbol (troncal recto, ramales en filas libres)
# =============================================================================
def _arbol(ramas: pd.DataFrame, raiz: int = 1):
    adj = defaultdict(list)
    for _, b in ramas.iterrows():
        adj[int(b.i)].append(int(b.j))
        adj[int(b.j)].append(int(b.i))
    padre, prof, orden = {raiz: None}, {raiz: 0}, [raiz]
    for u in orden:
        for v in adj[u]:
            if v not in padre:
                padre[v], prof[v] = u, prof[u] + 1
                orden.append(v)
    hijos = {u: [v for v in adj[u] if padre.get(v) == u] for u in adj}
    return padre, prof, orden, hijos


def layout_arbol(ramas: pd.DataFrame, raiz: int = 1) -> dict:
    """x = profundidad; el troncal (rama más larga) va en y = 0 y los ramales en la fila libre
    más cercana (mismo dibujo que verificacion/comprobacion_red.py)."""
    padre, prof, orden, hijos = _arbol(ramas, raiz)
    altura = {}
    for u in reversed(orden):
        altura[u] = 1 + max((altura[c] for c in hijos[u]), default=0)
    pos, ocupado, cola = {}, {}, []

    def libre(fila, a, b):
        return all(b < c - 0.5 or a > d + 0.5 for c, d in ocupado.get(fila, []))

    def cadena(ini, fila):
        ocupado.setdefault(fila, []).append((prof[ini], prof[ini] + altura[ini] - 1))
        u = ini
        while True:
            pos[u] = (prof[u], fila)
            hs = sorted(hijos[u], key=lambda c: -altura[c])
            if not hs:
                break
            cola.extend((c, fila) for c in hs[1:])
            u = hs[0]

    cadena(raiz, 0)
    while cola:
        ini, pf = cola.pop(0)
        a, b = prof[ini], prof[ini] + altura[ini] - 1
        for k in (1, -1, 2, -2, 3, -3):
            if libre(pf + k, a, b):
                cadena(ini, pf + k)
                break
    return {n: (x, 1.6 * y) for n, (x, y) in pos.items()}


def _red():
    nodos = pd.read_csv(os.path.join(DATA_DIR, "grid", "ieee33_nodes.csv")).set_index("bus_id")
    ramas = pd.read_csv(os.path.join(DATA_DIR, "grid", "ieee33_branches.csv"))
    return nodos, ramas, layout_arbol(ramas)


def _dibujar_ramas(ax, ramas, pos, color=EJE, lw=2.5):
    for _, b in ramas.iterrows():
        (xa, ya), (xb, yb) = pos[int(b.i)], pos[int(b.j)]
        ax.plot([xa, xb], [ya, yb], color=color, lw=lw, zorder=1, solid_capstyle="round")


def _ejes_red(ax, pos):
    ax.set_axis_off()
    xs, ys = [p[0] for p in pos.values()], [p[1] for p in pos.values()]
    ax.set_xlim(min(xs) - 0.8, max(xs) + 0.8)
    ax.set_ylim(min(ys) - 1.0, max(ys) + 1.0)


# =============================================================================
# A. CONTEXTO Y DATOS
# =============================================================================
def fig01_topologia():
    nodos, ramas, pos = _red()
    fig, ax = plt.subplots(figsize=(11.0, 4.6))
    _dibujar_ramas(ax, ramas, pos)
    for b, fila in nodos.iterrows():
        x, y = pos[b]
        if fila.tipo == "slack":
            ax.plot(x, y, marker="s", ms=22, color=TINTA, mec=SUP, mew=2, zorder=3)
        else:
            ax.plot(x, y, marker="o", ms=19, color=COLOR_TIPO[fila.customer_type], mec=SUP,
                    mew=2, zorder=3)
        ax.text(x, y, str(b), ha="center", va="center", fontsize=8.5, fontweight="bold",
                color="#ffffff", zorder=4)
    x1, y1 = pos[1]
    ax.annotate("Subestación\n(slack, 1.0 p.u.)", (x1, y1), xytext=(x1, y1 - 1.25),
                ha="center", va="top", fontsize=10, color=TINTA2,
                arrowprops=dict(arrowstyle="-", color=TENUE, lw=0.8))
    _ejes_red(ax, pos)
    ax.set_ylim(ax.get_ylim()[0] - 0.2, ax.get_ylim()[1] + 0.3)
    n = nodos.customer_type.value_counts()
    manejadores = [Line2D([], [], marker="o", ls="", ms=11, color=COLOR_TIPO[t], mec=SUP,
                          label=f"{NOMBRE_TIPO[t]} ({n[t]} barras)")
                   for t in ("regulados", "pequenas", "grandes")]
    manejadores.append(Line2D([], [], marker="s", ls="", ms=11, color=TINTA, mec=SUP,
                              label="Subestación"))
    ax.legend(handles=manejadores, loc="upper center", bbox_to_anchor=(0.5, 1.02), ncol=4,
              handletextpad=0.3, columnspacing=1.6)
    encabezado(fig, "Red de distribución IEEE 33-bus (radial)",
               "33 barras y 32 ramas · 12.66 kV, S_base = 10 MVA · color = tipo de cliente, "
               "que define el perfil horario de demanda")
    nota(fig, "Datos: Baran & Wu (1989), vía pandapower case33bw; se excluyen las 5 líneas de "
              "enlace (abiertas). Troncal 1–18 y ramales desde las barras 2, 3 y 6.")
    fig.subplots_adjust(left=0.02, right=0.98, top=0.82, bottom=0.08)
    guardar(fig, "01_topologia_ieee33")


def _demanda():
    d = pd.read_csv(os.path.join(DATA_DIR, "demand", "demand_profiles_norm_peak.csv"))
    return d.sort_values("hora").reset_index(drop=True)


def _alpha():
    return pd.read_csv(os.path.join(DATA_DIR, "pv_profiles", "alpha_t_mensual_anual.csv"),
                       index_col="t")


def _eje_horas(ax):
    ax.set_xlim(-0.5, 23.5)
    ax.set_xticks(range(0, 24, 3))
    ax.set_xticklabels([f"{h} h" for h in range(0, 24, 3)])
    ax.set_xlabel("Hora del día")


def fig02_demanda():
    d = _demanda()
    fig, ax = plt.subplots(figsize=FIG_ANCHO)
    cols = {"regulados": "lambda_regulados", "pequenas": "lambda_pequenas",
            "grandes": "lambda_grandes"}
    for t, c in cols.items():
        ax.plot(d.hora, d[c], color=COLOR_TIPO[t], label=NOMBRE_TIPO[t], zorder=3)
        ax.text(23.3, d[c].iloc[-1], "  " + NOMBRE_TIPO[t], va="center", fontsize=10.5,
                color=TINTA2, clip_on=False)
    reg = d["lambda_regulados"]
    hp, hv = int(d.hora[reg.idxmax()]), int(d.hora[reg.idxmin()])
    ax.plot([hp, hv], [reg.max(), reg.min()], ls="", marker="o", ms=8, color=AZUL, mec=SUP,
            mew=2, zorder=4)
    ax.annotate(f"punta {hp} h", (hp, reg.max()), xytext=(0, 9), textcoords="offset points",
                ha="center", fontsize=10.5, color=TINTA2)
    ax.annotate(f"valle {hv} h ({reg.min():.2f})", (hv, reg.min()), xytext=(0, -16),
                textcoords="offset points", ha="center", fontsize=10.5, color=TINTA2)
    _eje_horas(ax)
    ax.set_ylim(0, 1.1)
    ax.set_ylabel("Demanda / máxima del día [p.u.]")
    ax.legend(loc="lower left", ncol=3)
    g = d["lambda_grandes"]
    encabezado(fig, "Perfiles de demanda por tipo de cliente",
               f"Coordinador Eléctrico Nacional, 31-jul-2026, normalizados al pico diario · "
               f"regulados: punta {hp} h y valle {hv} h; grandes empresas casi planos "
               f"(≥ {g.min():.2f})")
    nota(fig, "Uso en el modelo: P_L(j,t) = P0(j) · λ_tipo(j)(t), con factor de potencia "
              "constante. Fuente: data/demand/demand_profiles_norm_peak.csv")
    fig.subplots_adjust(left=0.08, right=0.83, top=0.83, bottom=0.14)
    guardar(fig, "02_perfiles_demanda")


def fig03_pv_vs_demanda():
    d, a = _demanda(), _alpha()
    h = np.arange(24)
    jul, ene = a["Julio"].values, a["Enero"].values
    reg = d["lambda_regulados"].values
    sol = h[jul > 1e-3]
    hpv, hd = int(np.argmax(jul)), int(np.argmax(reg))
    fig, ax = plt.subplots(figsize=FIG_ANCHO)
    ax.plot(h, ene, color=TENUE, lw=1.6, label="PV enero (verano, contexto)", zorder=2)
    ax.fill_between(h, jul, color=AMARILLO, alpha=0.10, lw=0, zorder=1)
    ax.plot(h, jul, color=AMARILLO, label=r"PV julio  $\alpha_t$ (mes del caso)", zorder=3)
    ax.plot(h, reg, color=AZUL, label=r"Demanda regulados  $\lambda_t$", zorder=3)
    ax.plot([hpv], [jul[hpv]], marker="o", ms=8, color=AMARILLO, mec=SUP, mew=2, zorder=4)
    ax.plot([hd], [reg[hd]], marker="o", ms=8, color=AZUL, mec=SUP, mew=2, zorder=4)
    ax.plot([hd], [jul[hd]], marker="o", ms=8, color=AMARILLO, mec=SUP, mew=2, zorder=4)
    ax.text(hpv, 0.56, f"máx. PV julio\n{jul[hpv]:.2f} a las {hpv} h", ha="center", va="center",
            fontsize=10.5, color=TINTA2)
    ax.annotate(f"punta de demanda ({hd} h)", (hd, reg[hd]), xytext=(0, 10),
                textcoords="offset points", ha="center", fontsize=10.5, color=TINTA2)
    ax.annotate(f"PV = 0 en la punta", (hd, jul[hd]), xytext=(8, 10),
                textcoords="offset points", ha="left", fontsize=10.5, color=TINTA2)
    ax.annotate("", xy=(hd, 0.82), xytext=(hpv, 0.82),
                arrowprops=dict(arrowstyle="<->", color=TINTA2, lw=1.2))
    ax.text((hpv + hd) / 2, 0.80, f"desfase de {hd - hpv} h", ha="center", va="top",
            fontsize=10.5, color=TINTA2)
    _eje_horas(ax)
    ax.set_ylim(0, 1.12)
    ax.set_ylabel("Factor [p.u.]")
    ax.legend(loc="upper left", ncol=1)
    encabezado(fig, f"La punta de demanda ({hd} h) ocurre sin sol: el PV se concentra entre "
                    f"{sol[0]} y {sol[-1]} h",
               r"Calama (Explorador Solar, Min. Energía): $\alpha_t$ = generación por kW "
               r"instalado · $\lambda_t$ = demanda de clientes regulados (CEN), normalizada al pico"
               "\nUn BESS puede cargar con el excedente solar del mediodía y descargar en la "
               "punta vespertina")
    nota(fig, "Fuentes: data/pv_profiles/alpha_t_mensual_anual.csv y "
              "data/demand/demand_profiles_norm_peak.csv")
    fig.subplots_adjust(left=0.08, right=0.97, top=0.80, bottom=0.14)
    guardar(fig, "03_pv_vs_demanda")


# =============================================================================
# B. ETAPA 1: caso base sin PV ni BESS
# =============================================================================
SEGMENTOS = [(1, 18, "Troncal 1–18"), (19, 22, "Ramal desde 2"), (23, 25, "Ramal\ndesde 3"),
             (26, 33, "Ramal desde 6")]


def _sombrear_segmentos(ax, primero=1):
    for k, (a, b, txt) in enumerate(SEGMENTOS):
        a = max(a, primero)
        if k % 2 == 1:
            ax.axvspan(a - 0.5, b + 0.5, color=GRILLA, alpha=0.45, lw=0, zorder=0)
        ax.text((a + b) / 2, 0.985, txt, transform=ax.get_xaxis_transform(), ha="center",
                va="top", fontsize=10, color=TENUE)


def _marcadores_ref_modelo(ax, x, y_ref, y_mod, etiqueta_mod):
    ax.plot(x, y_ref, ls="", marker="o", ms=12, mfc="none", mec=C_REF, mew=1.5, zorder=3,
            label="pandapower (flujo AC, referencia)")
    ax.plot(x, y_mod, ls="", marker="o", ms=5.5, color=C_MODELO, mec=C_MODELO, zorder=4,
            label=etiqueta_mod)


def fig04_tensiones(E):
    ref, prod = E["ref"], E["prod_a"]
    barras = ref["V"].index.values
    fig, ax = plt.subplots(figsize=FIG_ANCHO)
    _sombrear_segmentos(ax)
    _marcadores_ref_modelo(ax, barras, ref["V"].values, prod["V"].loc[barras].values,
                           "Modelo de optimización (SOCP, código de producción)")
    linea_limite(ax, 0.90, r"$V_{min}$ = 0.90 p.u.", pos=0.005, ha="left", va="bottom")
    bmin = int(ref["V"].idxmin())
    ax.annotate(f"mínimo {ref['V'].min():.4f} p.u. (barra {bmin})", (bmin, ref["V"].min()),
                xytext=(0, -22), textcoords="offset points", ha="center", fontsize=10.5,
                color=TINTA2)
    ax.set_xlim(0.3, 33.7)
    ax.set_xticks([1, 5, 10, 15, 18, 19, 22, 23, 25, 26, 30, 33])
    ax.set_xlabel("Barra")
    ax.set_ylim(0.885, 1.012)
    ax.set_ylabel("Magnitud de tensión [p.u.]")
    ax.legend(loc="lower left", bbox_to_anchor=(0.0, 1.0), ncol=2, columnspacing=2.0)
    dv = (prod["V"] - ref["V"]).abs().max()
    encabezado(fig, "El modelo reproduce las tensiones del flujo AC",
               f"Caso base IEEE 33-bus sin PV ni BESS, un período · máx |ΔV| = {sci(dv)} p.u. "
               f"(tolerancia {sci(TOL_V_PU)})")
    nota(fig, "Generado con verificacion/etapa1_caso_base.py (producción (a): candidatos PV/BESS "
              "vacíos, tolerancias de barrera 1e-10).")
    fig.subplots_adjust(left=0.08, right=0.97, top=0.78, bottom=0.14)
    guardar(fig, "04_etapa1_tensiones")


def fig05_corrientes(E):
    ref, prod = E["ref"], E["prod_a"]
    j = ref["ramas"].index.values
    fig, ax = plt.subplots(figsize=FIG_ANCHO)
    _sombrear_segmentos(ax, primero=2)
    _marcadores_ref_modelo(ax, j, ref["ramas"]["I_A"].values,
                           prod["ramas"].loc[j, "I_A"].values,
                           "Modelo de optimización (SOCP, código de producción)")
    linea_limite(ax, 300, r"$I_{max}$ = 300 A (límite térmico)", pos=0.005, ha="left")
    i12 = ref["ramas"].loc[2, "I_A"]
    ax.annotate(f"cabecera 1→2: {i12:.1f} A", (2, i12), xytext=(12, 4),
                textcoords="offset points", ha="left", fontsize=10.5, color=TINTA2)
    ax.set_xlim(1.3, 33.7)
    ax.set_xticks([2, 5, 10, 15, 18, 19, 22, 23, 25, 26, 30, 33])
    ax.set_xlabel(r"Rama $\pi(j) \rightarrow j$ (barra receptora $j$)")
    ax.set_ylim(0, 335)
    ax.set_ylabel("Corriente [A]")
    ax.legend(loc="lower left", bbox_to_anchor=(0.0, 1.0), ncol=2, columnspacing=2.0)
    di = ((prod["ramas"]["I_A"] - ref["ramas"]["I_A"]).abs() / ref["ramas"]["I_A"]).max()
    encabezado(fig, "El modelo reproduce las corrientes de rama del flujo AC",
               f"Caso base sin PV ni BESS · máx |ΔI|/I = {sci(di)} (tolerancia {sci(TOL_I_REL)}) "
               f"· todas las ramas bajo el límite de 300 A")
    nota(fig, r"Corriente del modelo: I = $\sqrt{l}$ · I_base, con I_base = S_base/($\sqrt{3}$ "
              f"V_base) = {I_BASE_KA * 1000:.2f} A. Generado con verificacion/etapa1_caso_base.py.")
    fig.subplots_adjust(left=0.08, right=0.97, top=0.78, bottom=0.14)
    guardar(fig, "05_etapa1_corrientes")


def _errores(ref, sol) -> dict:
    return {"V": (sol["V"] - ref["V"]).abs().max(),
            "I": ((sol["ramas"]["I_A"] - ref["ramas"]["I_A"]).abs() / ref["ramas"]["I_A"]).max(),
            "perd": abs(sol["perdidas_kW"] - ref["perdidas_kW"]) / ref["perdidas_kW"],
            "gap": sol["gap_rel"]}


def fig06_resumen_errores(E):
    ref = E["ref"]
    modelos = [("SOCP independiente\n(ecuaciones del informe)", E["ind"], C_MODELO),
               ("Producción (a)\nSOCP puro", E["prod_a"], C_MODELO),
               ("Producción (b)\nMISOCP, binarias en 0", E["prod_b"], C_MODELO),
               ("(b) con tolerancias\npor defecto de Gurobi", E["prod_def"], C_PROBLEMA)]
    errs = [_errores(ref, s) for _, s, _ in modelos]
    metricas = [("V", r"máx |ΔV| [p.u.]", TOL_V_PU),
                ("I", r"máx |ΔI| / I  (corriente por rama)", TOL_I_REL),
                ("perd", "error relativo de pérdidas totales", TOL_LOSS_REL),
                ("gap", "brecha cónica relativa máxima", TOL_GAP_REL)]
    fig, axs = plt.subplots(2, 2, figsize=(11.0, 6.4), sharey=True)
    y = np.arange(len(modelos))[::-1]
    for ax, (k, txt, tol) in zip(axs.flat, metricas):
        ax.set_xscale("log")
        ax.set_xlim(1e-13, 1.0)
        ax.axvspan(tol, 1.0, color=CRITICO, alpha=0.06, lw=0, zorder=0)
        ax.axvline(tol, color=TINTA2, lw=1.2, ls=(0, (5, 3)), zorder=2)
        ax.text(tol, 1.0, f" tolerancia {sci(tol)}", transform=ax.get_xaxis_transform(),
                ha="left", va="bottom", fontsize=10, color=TINTA2)
        for yi, (nombre, _, c), e in zip(y, modelos, errs):
            ax.plot(e[k], yi, marker="o", ms=10, color=c, mec=SUP, mew=2, zorder=4, ls="")
            if c == C_PROBLEMA:
                fuera = e[k] > tol
                ax.annotate(sci(e[k]), (e[k], yi), xytext=(0, 11), textcoords="offset points",
                            ha="center", va="bottom", fontsize=10.5,
                            color=CRITICO if fuera else TINTA2,
                            fontweight="bold" if fuera else "normal")
        ax.text(0.985, 0.97, "fuera de\ntolerancia", transform=ax.transAxes, ha="right",
                va="top", fontsize=9.5, color=CRITICO)
        ax.set_title(txt, loc="left", fontsize=12, color=TINTA, pad=16)
        ax.set_xticks([1e-12, 1e-9, 1e-6, 1e-3, 1])
        ax.grid(axis="y", visible=False)
    for ax in axs[:, 0]:
        ax.set_yticks(y)
        ax.set_yticklabels([m[0] for m in modelos], fontsize=10.5)
    for ax in axs[:, 1]:
        ax.tick_params(axis="y", length=0)
    for ax in axs.flat:
        ax.set_ylim(-0.6, len(modelos) - 0.4)
    encabezado(fig, "Los tres modelos verificados quedan muy por debajo de la tolerancia",
               "Error máximo de cada modelo respecto del flujo AC de pandapower (escala log) · "
               "con las tolerancias por defecto de Gurobi,\nla corriente y la brecha relativa "
               "quedan fuera de tolerancia")
    nota(fig, "Generado con verificacion/etapa1_caso_base.py.")
    fig.subplots_adjust(left=0.19, right=0.97, top=0.79, bottom=0.11, hspace=0.6, wspace=0.08)
    guardar(fig, "06_etapa1_resumen_errores")


def _brecha_por_rama(sol) -> pd.Series:
    """Brecha absoluta (28) por rama, v_pi*l - P^2 - Q^2 [p.u.^2], desde la solución en unidades físicas."""
    r = sol["ramas"]
    v_pi = sol["V"].loc[r["i"].values].values ** 2
    l_ = (r["I_A"].values / (I_BASE_KA * 1000.0)) ** 2
    p, q = r["P_MW"].values / S_BASE, r["Q_MVAr"].values / S_BASE
    return pd.Series(v_pi * l_ - p ** 2 - q ** 2, index=r.index)


def fig07_brecha_relativa(E):
    ref, ajust, defe = E["ref"], E["prod_b"], E["prod_def"]
    j = ref["ramas"].index.values
    pq2 = ((ref["ramas"]["P_MW"] / S_BASE) ** 2 + (ref["ramas"]["Q_MVAr"] / S_BASE) ** 2).loc[j]
    piso = 1e-14
    gap_aj = _brecha_por_rama(ajust).loc[j].abs().clip(lower=piso)
    gap_de = _brecha_por_rama(defe).loc[j].abs().clip(lower=piso)
    dI_aj = ((ajust["ramas"]["I_A"] - ref["ramas"]["I_A"]).abs() / ref["ramas"]["I_A"]).loc[j]
    dI_de = ((defe["ramas"]["I_A"] - ref["ramas"]["I_A"]).abs() / ref["ramas"]["I_A"]).loc[j]

    fig, (a1, a2) = plt.subplots(2, 1, figsize=(11.0, 6.6), sharex=True)
    chicas = j[pq2.values < TOL_GAP_ABS_INFORME]
    for ax in (a1, a2):
        for jj in chicas:
            ax.axvspan(jj - 0.5, jj + 0.5, color=GRILLA, alpha=0.6, lw=0, zorder=0)
        ax.set_yscale("log")
    # Panel 1: magnitudes absolutas [p.u.^2]
    for k, (a, b, _) in enumerate(SEGMENTOS):          # sin unir ramas que no son contiguas
        sel = [x for x in j if max(a, 2) <= x <= b]
        a1.plot(sel, pq2.loc[sel].values, color=TENUE, lw=1.6, marker="o", ms=4, zorder=2,
                label=r"$P^2+Q^2$ de la rama (pandapower)" if k == 0 else None)
    a1.axhline(TOL_GAP_ABS_INFORME, color=TINTA2, lw=1.2, ls=(0, (5, 3)), zorder=2,
               label="umbral absoluto (28) del informe: " + sci(TOL_GAP_ABS_INFORME)
               + r" p.u.$^2$")
    a1.plot(j, gap_de.values, ls="", marker="o", ms=8, color=C_PROBLEMA, mec=SUP, mew=2,
            zorder=4, label="brecha |v·l − P² − Q²|, tolerancias por defecto")
    a1.plot(j, gap_aj.values, ls="", marker="o", ms=8, color=C_MODELO, mec=SUP, mew=2,
            zorder=4, label="brecha |v·l − P² − Q²|, tolerancias ajustadas")
    a1.set_ylim(1e-21, 3.0)
    a1.set_yticks([1e-12, 1e-9, 1e-6, 1e-3, 1])
    a1.set_ylabel(r"[p.u.$^2$]")
    a1.legend(loc="lower left", ncol=2, fontsize=10, columnspacing=1.5, handletextpad=0.4)
    a1.set_title(f"Criterio absoluto: en las ramas sombreadas ({len(chicas)}) P²+Q² es menor que "
                 "el propio umbral, así que no puede detectar errores", loc="left",
                 fontsize=11.5, color=TINTA)
    # Panel 2: error relativo de corriente
    a2.plot(j, dI_de.values, ls="", marker="o", ms=8, color=C_PROBLEMA, mec=SUP, mew=2, zorder=4,
            label="tolerancias por defecto")
    a2.plot(j, dI_aj.values.clip(min=piso), ls="", marker="o", ms=8, color=C_MODELO, mec=SUP,
            mew=2, zorder=4, label="tolerancias ajustadas (1e-10)")
    a2.axhline(TOL_I_REL, color=TINTA2, lw=1.2, ls=(0, (5, 3)), zorder=2)
    a2.text(2, TOL_I_REL * 1.5, "tolerancia " + sci(TOL_I_REL), fontsize=10.5, color=TINTA2)
    jm = int(dI_de.idxmax())
    a2.annotate(f"{100 * dI_de.max():.1f} % en la rama → {jm}", (jm, dI_de.max()),
                xytext=(-12, -2), textcoords="offset points", ha="right", va="center",
                fontsize=10.5, color=CRITICO)
    a2.set_ylim(1e-10, 3.0)
    a2.set_yticks([1e-10, 1e-8, 1e-6, 1e-4, 1e-2, 1])
    a2.set_ylabel("|ΔI| / I  vs pandapower")
    a2.legend(loc="upper left", ncol=2, fontsize=10)
    a2.set_title("Error de corriente: con tolerancias por defecto supera la tolerancia aunque (28) "
                 "\"pase\"", loc="left", fontsize=11.5, color=TINTA)
    a2.set_xlim(1.3, 33.7)
    a2.set_xticks([2, 5, 10, 15, 18, 19, 22, 23, 25, 26, 30, 33])
    a2.set_xlabel(r"Rama $\pi(j) \rightarrow j$ (barra receptora $j$)")
    for ax in (a1, a2):
        ax.grid(axis="x", visible=False)
    encabezado(fig, "La exactitud de la relajación debe medirse con la brecha relativa",
               "Modelo de producción (b), caso base · se propone (v·l − P² − Q²)/(v·l) ≤ "
               + sci(TOL_GAP_REL) + " en lugar del umbral absoluto (28)")
    fig.subplots_adjust(left=0.08, right=0.97, top=0.81, bottom=0.1, hspace=0.45)
    guardar(fig, "07_etapa1_brecha_relativa")


# =============================================================================
# C. ETAPA 2: hallazgos PRELIMINARES (Tabla 1 de [4])
# =============================================================================
NOTA_PRELIM = ("PRELIMINAR: el equipo aún no decide adoptar el MIQCP exacto ni el objetivo (10). "
               "Generado con verificacion/preliminar_tabla1.py.")


def fig08_tabla1(P):
    ref = P["referencia_4"]
    grupos = [("Escenario 1\ntodas las barras candidatas", 1),
              ("Escenario 2\nsolo barras 2 y 3", 2)]
    series = [("[4] Blanco-Solano et al. (2026), Tabla 1", TENUE),
              ("MIQCP exacto (este trabajo)", C_MODELO),
              ("MISOCP relajado (modelo del informe)", C_PROBLEMA)]
    fig, ax = plt.subplots(figsize=FIG_ANCHO)
    ax.set_xlim(-0.6, 1.6)
    ax.set_ylim(0, 14500)
    ancho, sep = 0.1, 0.115
    for g, (_, esc) in enumerate(grupos):
        r4 = ref[str(esc)]["HC_kW"] if str(esc) in ref else ref[esc]["HC_kW"]
        ex = P[f"escenario_{esc}"]["exacto"]
        rl = P[f"escenario_{esc}"]["relajado"]
        valores = [r4, ex["HC_kW"], rl["HC_kW"]]
        for k, ((_, c), v) in enumerate(zip(series, valores)):
            x = g + (k - 1) * sep
            barras_redondeadas(ax, [x], [v], ancho, c)
            ax.text(x, v + 180, kw(v), ha="center", va="bottom", fontsize=11, color=TINTA,
                    fontweight="bold" if k == 1 else "normal")
        ax.text(g + sep, rl["HC_kW"] + 900,
                f"+{100 * (rl['HC_kW'] / r4 - 1):.0f} % · incluye\n{kw(rl['perdidas_ficticias_kW'])} kW "
                "de pérdidas ficticias", ha="center", va="bottom", fontsize=10, color=TINTA2)
    ax.set_xticks([0, 1])
    ax.set_xticklabels([g[0] for g in grupos])
    ax.tick_params(axis="x", length=0)
    ax.set_ylabel("Hosting capacity de PV [kW]")
    ax.grid(axis="x", visible=False)
    ax.legend(handles=[Rectangle((0, 0), 1, 1, fc=c, ec="none", label=n) for n, c in series],
              loc="lower left", bbox_to_anchor=(0.0, 1.0), ncol=3, columnspacing=1.4,
              handlelength=1.2)
    encabezado(fig, "El MIQCP exacto replica la Tabla 1 de [4]; la relajación la sobreestima",
               "IEEE 33-bus, carga base, PV con fp = 1 · tensiones 0.9–1.1 p.u., 300 A, "
               r"exportación ≤ 4.6 MW · objetivo (10) de [4]: máx $\Sigma_j\, P^{PV}_j$",
               preliminar=True)
    nota(fig, NOTA_PRELIM)
    fig.subplots_adjust(left=0.09, right=0.97, top=0.78, bottom=0.15)
    guardar(fig, "08_preliminar_tabla1_hc")


def fig09_validacion_ac(P):
    ref = P["referencia_4"]["1"] if "1" in P["referencia_4"] else P["referencia_4"][1]
    ex = P["escenario_1"]["exacto"]["ac"]
    rl = P["escenario_1"]["relajado"]["ac"]
    lim = P["limites"]
    filas = [("[4] Blanco-Solano\n(AC de los autores)", ref, TENUE, True),
             ("MIQCP exacto", ex, C_MODELO, False),
             ("MISOCP relajado", rl, C_PROBLEMA, False)]
    paneles = [("export_kW", "Exportación a la red aguas arriba [kW]", lim["export_kW"],
                lambda v: kw(v), (3500, 7600), kw(lim["export_kW"])),
               ("Vmax_pu", "Tensión máxima [p.u.]", lim["Vmax_pu"], lambda v: f"{v:.4f}",
                (1.0, 1.16), f"{lim['Vmax_pu']:.2f}"),
               ("Imax_A", "Corriente máxima de rama [A]", lim["Imax_A"], lambda v: f"{v:.0f}",
                (200, 390), f"{lim['Imax_A']:.0f}")]
    fig, axs = plt.subplots(1, 3, figsize=(11.0, 4.8), sharey=True)
    y = np.arange(len(filas))[::-1]
    for ax, (k, titulo, li, fmt, xl, txt_li) in zip(axs, paneles):
        ax.set_xlim(*xl)
        ax.axvspan(li, xl[1], color=CRITICO, alpha=0.06, lw=0, zorder=0)
        ax.axvline(li, color=TINTA2, lw=1.2, ls=(0, (5, 3)), zorder=2)
        ax.text(li, 1.0, " límite " + txt_li, transform=ax.get_xaxis_transform(), ha="left",
                va="bottom", fontsize=10, color=TINTA2)
        for yi, (_, d, c, hueco) in zip(y, filas):
            v = d[k]
            if hueco:
                ax.plot(v, yi, marker="o", ms=11, mfc="none", mec=c, mew=1.8, ls="", zorder=4)
            else:
                ax.plot(v, yi, marker="o", ms=10, color=c, mec=SUP, mew=2, ls="", zorder=4)
            viola = v > li * (1 + 1e-4)
            en_limite = abs(v - li) <= 0.01 * li           # no tapar la línea del límite
            izq = en_limite and v < li * (1 - 1e-4)
            ax.annotate(fmt(v), (v, yi),
                        xytext=((-8, 9) if izq else (8, 9)) if en_limite else (0, 11),
                        textcoords="offset points",
                        ha=("right" if izq else "left") if en_limite else "center",
                        va="bottom", fontsize=10.5,
                        color=CRITICO if viola else TINTA2,
                        fontweight="bold" if viola else "normal")
        ax.set_title(titulo, loc="left", fontsize=11.5, color=TINTA, pad=18)
        ax.grid(axis="y", visible=False)
        ax.set_ylim(-0.6, len(filas) - 0.2)
    axs[0].set_yticks(y)
    axs[0].set_yticklabels([f[0] for f in filas], fontsize=10.5)
    for ax in axs[1:]:
        ax.tick_params(axis="y", length=0)
    rel = P["escenario_1"]["relajado"]
    encabezado(fig, "Validada en AC, la solución relajada viola los límites de la red",
               f"Escenario 1: el PV de cada solución se inyecta en un flujo AC de pandapower · "
               f"la relajación ubica {kw(rel['HC_kW'])} kW, que en la red real\nexportan "
               f"{kw(rl['export_kW'])} kW (límite {kw(lim['export_kW'])})", preliminar=True)
    nota(fig, "Sombreado rojo = fuera del límite. " + NOTA_PRELIM)
    fig.subplots_adjust(left=0.16, right=0.97, top=0.72, bottom=0.12, wspace=0.12)
    guardar(fig, "09_preliminar_validacion_ac")


def fig10_indeterminacion(P):
    ind = P["indeterminacion_obj1"]
    r4 = P["referencia_4"]["1"]["HC_kW"] if "1" in P["referencia_4"] else P["referencia_4"][1]["HC_kW"]
    ex = P["escenario_1"]["exacto"]["HC_kW"]
    fig, ax = plt.subplots(figsize=(11.0, 4.6))
    filas = [("Objetivo (1) del informe\n(MISOCP relajado)", 2),
             ("Objetivo (10) de [4]\n(MIQCP exacto)", 1),
             ("[4] Tabla 1", 0)]
    lo, hi = ind["HC_min_kW"], ind["HC_max_kW"]
    ax.plot([lo, hi], [2, 2], color=C_PROBLEMA, lw=12, alpha=0.22, solid_capstyle="butt", zorder=2)
    for x in (lo, hi):
        ax.plot([x, x], [1.8, 2.2], color=C_PROBLEMA, lw=2, zorder=3)
        ax.text(x, 2.28, kw(x), ha="center", va="bottom", fontsize=10.5, color=TINTA2)
    ax.text((lo + hi) / 2, 2.28, "mismo valor óptimo del objetivo", ha="center", va="bottom",
            fontsize=10.5, color=TINTA2)
    ax.plot(ind["HC_solucion_kW"], 2, marker="o", ms=10, color=C_PROBLEMA, mec=SUP, mew=2, zorder=4)
    ax.annotate(f"solución entregada por Gurobi: {kw(ind['HC_solucion_kW'])} kW",
                (ind["HC_solucion_kW"], 2), xytext=(0, -20), textcoords="offset points",
                ha="center", va="top", fontsize=10.5, color=TINTA2)
    ax.plot(ex, 1, marker="o", ms=10, color=C_MODELO, mec=SUP, mew=2, zorder=4)
    ax.annotate(f"{kw(ex)} kW", (ex, 1), xytext=(12, 0), textcoords="offset points",
                ha="left", va="center", fontsize=10.5, color=TINTA2)
    ax.plot(r4, 0, marker="o", ms=11, mfc="none", mec=TENUE, mew=1.8, zorder=4)
    ax.annotate(f"{kw(r4)} kW", (r4, 0), xytext=(12, 0), textcoords="offset points",
                ha="left", va="center", fontsize=10.5, color=TINTA2)
    ax.axvline(r4, color=GRILLA, lw=1.2, zorder=1)
    ax.set_yticks([f[1] for f in filas])
    ax.set_yticklabels([f[0] for f in filas], fontsize=10.5)
    ax.set_ylim(-0.6, 2.8)
    ax.set_xlim(7800, 12400)
    ax.set_xlabel("Hosting capacity de PV [kW] (escenario 1)")
    ax.grid(axis="y", visible=False)
    ax.tick_params(axis="y", length=0)
    encabezado(fig, "El objetivo (1) del informe no determina el hosting capacity",
               r"Sumando los balances nodales, $\Sigma P^{PV}$ − pérdidas = $\Sigma P^{L} - P_S$: "
               "el objetivo (1) maximiza la exportación. Con la exportación\nen su límite, "
               r"cualquier HC del rango da el mismo óptimo; el objetivo (10) de [4] "
               r"(máx $\Sigma P^{PV}$) sí lo determina",
               preliminar=True)
    nota(fig, NOTA_PRELIM)
    fig.subplots_adjust(left=0.2, right=0.97, top=0.75, bottom=0.17)
    guardar(fig, "10_preliminar_indeterminacion_obj1")


def fig11_ubicacion_pv(P):
    nodos, ramas, pos = _red()
    ref = P["referencia_4"]["1"] if "1" in P["referencia_4"] else P["referencia_4"][1]
    sit_ref = {int(k): v for k, v in ref["sitios_kW"].items()}
    sit_ex = {int(k): v for k, v in P["escenario_1"]["exacto"]["sitios_kW"].items() if v >= 1}
    fig, axs = plt.subplots(1, 2, figsize=(11.0, 4.6))
    for ax, titulo, sitios in ((axs[0], "[4] Blanco-Solano et al. (2026)", sit_ref),
                               (axs[1], f"MIQCP exacto (este trabajo): {kw(sum(sit_ex.values()))} kW",
                                sit_ex)):
        if titulo.startswith("[4]"):
            titulo += f": {kw(sum(sitios.values()))} kW"
        _dibujar_ramas(ax, ramas, pos, lw=2.0)
        xs, ys = zip(*[pos[b] for b in nodos.index])
        ax.plot(xs, ys, ls="", marker="o", ms=4.5, color=TENUE, zorder=2)
        x1, y1 = pos[1]
        ax.plot(x1, y1, marker="s", ms=10, color=TINTA, mec=SUP, mew=1.5, zorder=3)
        for b, p in sitios.items():
            x, y = pos[b]
            ax.scatter([x], [y], s=max(p * 0.22, 40), color=AMARILLO, alpha=0.9, edgecolors=SUP,
                       linewidths=2, zorder=4)
            dy = -1.05 if y <= 0 else 1.05
            borde = x >= max(q[0] for q in pos.values()) - 1.5
            ax.annotate(f"barra {b}: {kw(p)} kW", (x, y), xytext=(x + (0.4 if borde else 0), y + dy),
                        ha="right" if borde else "center",
                        va="center", fontsize=10.5, color=TINTA,
                        arrowprops=dict(arrowstyle="-", color=TENUE, lw=0.8))
        _ejes_red(ax, pos)
        ax.set_ylim(ax.get_ylim()[0] - 0.1, ax.get_ylim()[1] + 0.5)
        ax.set_title(titulo, loc="left", fontsize=12, color=TINTA)
    encabezado(fig, "El MIQCP exacto ubica el PV en las mismas barras que [4]",
               "Escenario 1 (todas las barras candidatas) · área del círculo proporcional a la "
               "potencia PV instalada\nEn ambos casos la restricción activa es la exportación "
               "(4.6 MW)",
               preliminar=True)
    nota(fig, NOTA_PRELIM)
    fig.subplots_adjust(left=0.02, right=0.98, top=0.76, bottom=0.08, wspace=0.05)
    guardar(fig, "11_preliminar_ubicacion_pv")


# =============================================================================
def main() -> int:
    print("Figuras de avance ->", os.path.relpath(OUT_DIR, BASE_DIR))
    print("A. Contexto y datos")
    fig01_topologia()
    fig02_demanda()
    fig03_pv_vs_demanda()

    print("B. Etapa 1 (resolviendo pandapower y los modelos SOCP/MISOCP...)")
    E = {"ref": referencia_pandapower(), "ind": socp_independiente(),
         "prod_a": modelo_produccion(sin_binarias=True),
         "prod_b": modelo_produccion(sin_binarias=False),
         "prod_def": modelo_produccion(sin_binarias=False, ajustar_tolerancias=False)}
    fig04_tensiones(E)
    fig05_corrientes(E)
    fig06_resumen_errores(E)
    fig07_brecha_relativa(E)

    print("C. Etapa 2, PRELIMINAR (resolviendo la Tabla 1 de [4]...)")
    P = pt1.ejecutar()
    fig08_tabla1(P)
    fig09_validacion_ac(P)
    fig10_indeterminacion(P)
    fig11_ubicacion_pv(P)
    return 0


if __name__ == "__main__":
    sys.exit(main())
