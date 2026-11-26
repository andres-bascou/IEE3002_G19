"""
verificacion/preliminar_24h_bess/_comun.py
==========================================
*** PRELIMINAR ***  Utilidades comunes de las pruebas de 24 h con BESS (ver README.md de esta carpeta).

Importar este módulo ANTES que `modelo.*`: agrega la raíz del proyecto a sys.path.
"""
import json
import os
import sys
from pathlib import Path

# OJO: NO usar rutas absolutas (p.ej. r"C:\Users\..." o "/Users/..."): solo funcionan en un PC.
# Se resuelve la raíz del proyecto relativa a este archivo (<raíz>/verificacion/preliminar_24h_bess/).
BASE_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE_DIR))

# Igual que el modelo: $HC_RESULTS_DIR si existe, si no <raíz>/results
RESULTS_DIR = Path(os.environ.get("HC_RESULTS_DIR", BASE_DIR / "results")) / "preliminar_24h_bess"

# Configuración común de las pruebas: julio, PV hasta 20 MW por barra en cualquier barra (tope no activo)
BASE_KW = dict(month=7, p_pv_max_mw=20.0, n_pv_max=32, output_flag=0)
P_S_REF_PU = -0.46          # exportación <= 4.6 MW, como en la Tabla 1 de [4]


def guardar(nombre, out):
    """Imprime el resultado y lo agrega como una línea a results/preliminar_24h_bess/<nombre>.jsonl."""
    linea = json.dumps(out, ensure_ascii=False)
    print(linea, flush=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_DIR / f"{nombre}.jsonl", "a", encoding="utf-8") as f:
        f.write(linea + "\n")


def sitios_pv_kw(r):
    """Barras con PV instalado (> 0.1 kW) y su capacidad en kW."""
    return {int(b): round(p * 1000, 1) for b, p in zip(r["pv_sites"]["bus"], r["pv_sites"]["P_cap_MW"])
            if p > 1e-4}


def simultaneas(X, cfg, tol_kw=0.1):
    """Batería-horas en que la BESS carga y descarga a la vez (más de tol_kw en ambas)."""
    S = cfg.s_base_mva * 1000.0                              # p.u. -> kW
    out = []
    for j in X["G_b"]:
        if X["z"][j].X < 0.5:
            continue
        for t in X["T"]:
            ch, dis = X["Pch"][j, t].X * S, X["Pdis"][j, t].X * S
            if min(ch, dis) > tol_kw:
                out.append({"bus": int(j), "t": int(t), "Pch_kW": round(ch, 2), "Pdis_kW": round(dis, 2)})
    return out
