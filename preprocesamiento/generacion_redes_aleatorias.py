"""Generador de redes de distribución radiales aleatorias, a partir de la IEEE 33-bus.

Genera N redes distintas y reproducibles (semilla S), con el mismo formato que
'data/grid/ieee33_nodes.csv' y 'data/grid/ieee33_branches.csv', y las guarda en
'data/grid_tests/<nombre_red>/'. Cada red se arma así:

  1. Topología: árbol radial. Cada red sortea su número de barras en [n_barras_min, n_barras_max]
     (y por tanto de líneas = barras - 1) y su propio p_cadena en [p_cadena_min, p_cadena_max],
     así que las redes difieren en tamaño y en forma (alimentador largo vs. muy ramificada).
     La barra 1 es la subestación y tiene un único hijo (barra 2), como en la IEEE 33-bus.
     Cada barra j >= 3 se conecta, con probabilidad p_cadena, a la barra j-1 (alimentador
     largo, como el troncal 1-18 de la IEEE 33-bus) y, si no, a una barra anterior elegida
     al azar (ramales laterales, como los 19-22, 23-25 y 26-33). Siempre pi(j) < j.
     Se garantiza que no haya dos redes con el mismo árbol (isomorfismo: la misma forma aunque
     las barras estén numeradas distinto); si sale una repetida se vuelve a sortear.
  2. Impedancias: cada rama toma el (r, x) de una rama de la IEEE 33-bus elegida al azar,
     multiplicado por un factor lognormal (sigma_z). Así se conserva la relación x/r y el
     rango de magnitudes de la red original. El límite térmico (300 A) se mantiene.
  3. Cargas: cada barra de carga toma (P0, Q0) y el tipo de cliente (regulados / pequenas /
     grandes) de una barra de la IEEE 33-bus elegida al azar, con un factor lognormal
     (sigma_carga) sobre la potencia (el factor de potencia de esa barra se conserva).
  4. Validación: el caso base (carga pico, sin PV ni BESS) debe cumplir tensiones >= v_min_base
     y corrientes <= I_max, con un flujo radial exacto (barrido backward/forward). Si no
     cumple, se vuelve a sortear la red (mismo generador de números aleatorios, así que
     sigue siendo determinista). Sin esto el modelo de optimización sería infactible.

La red k de la semilla S es siempre la misma, sin importar cuántas redes se pidan (N)
(depende solo de S, k y de las redes anteriores 1..k-1, por la regla de no repetir topología).

Uso (desde cualquier carpeta):
    python preprocesamiento/generacion_redes_aleatorias.py --n 20 --semilla 1
    python preprocesamiento/generacion_redes_aleatorias.py --n 5 --semilla 42 --n-barras-min 15 --n-barras-max 60
    python preprocesamiento/generacion_redes_aleatorias.py --n 5 --semilla 3 --n-barras 33   # todas de 33 barras

Salida (por red): data/grid_tests/red_s<S>_<kkk>/{nodes.csv, branches.csv, meta.json}
y un índice data/grid_tests/indice_s<S>.csv con las características de cada red.
"""
import argparse
import hashlib
import json
import os
import shutil

import numpy as np
import pandas as pd

# OJO: NO usar rutas absolutas (p.ej. r"C:\Users\..." o "/Users/..."): solo funcionan en un PC.
# Se resuelve la raíz del proyecto relativa a este archivo (<raíz>/<carpeta>/este_script.py).
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # raíz del proyecto
GRID_REF_DIR = os.path.join(BASE_DIR, "data", "grid")
GRID_TESTS_DIR = os.path.join(BASE_DIR, "data", "grid_tests")

S_BASE_MVA = 10.0   # igual que preprocesamiento/generacion_red.py
V_BASE_KV = 12.66


# =============================================================================
# Red de referencia
# =============================================================================
def cargar_referencia(grid_dir=GRID_REF_DIR):
    nodos = pd.read_csv(os.path.join(grid_dir, "ieee33_nodes.csv"))
    ramas = pd.read_csv(os.path.join(grid_dir, "ieee33_branches.csv"))
    return nodos, ramas


# =============================================================================
# Generación de una red
# =============================================================================
def generar_padres(rng, n_barras, p_cadena):
    """Árbol radial: devuelve padre[j] para j = 2..n_barras (barras numeradas desde 1)."""
    padre = {2: 1}                                   # la subestación alimenta una sola barra
    for j in range(3, n_barras + 1):
        if rng.random() < p_cadena:
            padre[j] = j - 1                         # sigue el alimentador
        else:
            padre[j] = int(rng.integers(2, j))       # ramal lateral desde una barra previa (>= 2)
    return padre


def forma_canonica(padre):
    """Cadena canónica del árbol (AHU): dos árboles tienen la misma cadena si y solo si son
    isomorfos, es decir, la misma topología aunque las barras se numeren distinto."""
    hijos = {}
    for j, p in padre.items():
        hijos.setdefault(p, []).append(j)

    def f(u):
        return "(" + "".join(sorted(f(c) for c in hijos.get(u, []))) + ")"
    return f(1)


def generar_red(rng, nodos_ref, ramas_ref, n_barras, p_cadena, sigma_z, sigma_carga):
    padre = generar_padres(rng, n_barras, p_cadena)

    # --- Ramas: (r, x) remuestreados de la IEEE 33-bus con ruido lognormal ---------------
    filas = []
    for k, j in enumerate(range(2, n_barras + 1), start=1):
        base = ramas_ref.iloc[int(rng.integers(len(ramas_ref)))]
        f = float(rng.lognormal(0.0, sigma_z))
        filas.append({"line_id": k, "i": padre[j], "j": j,
                      "r_pu": float(base["r_pu"]) * f, "x_pu": float(base["x_pu"]) * f,
                      "length_km": float(base["length_km"]), "i_max_pu": float(base["i_max_pu"])})
    ramas = pd.DataFrame(filas)

    # --- Nodos: cargas y tipo de cliente remuestreados --------------------------------------
    cargas_ref = nodos_ref[nodos_ref["bus_id"] != 1].reset_index(drop=True)
    v_min_ref, v_max_ref = cargas_ref["v_min_pu"].iloc[0], cargas_ref["v_max_pu"].iloc[0]
    filas = [{"bus_id": 1, "tipo": "slack", "v_min_pu": 1.0, "v_max_pu": 1.0,
              "P0_MW": 0.0, "Q0_MVAR": 0.0, "P0_pu": 0.0, "Q0_pu": 0.0, "customer_type": "none"}]
    for b in range(2, n_barras + 1):
        base = cargas_ref.iloc[int(rng.integers(len(cargas_ref)))]
        f = float(rng.lognormal(0.0, sigma_carga))
        p_mw, q_mvar = float(base["P0_MW"]) * f, float(base["Q0_MVAR"]) * f
        filas.append({"bus_id": b, "tipo": "load", "v_min_pu": v_min_ref, "v_max_pu": v_max_ref,
                      "P0_MW": p_mw, "Q0_MVAR": q_mvar,
                      "P0_pu": p_mw / S_BASE_MVA, "Q0_pu": q_mvar / S_BASE_MVA,
                      "customer_type": base["customer_type"]})
    nodos = pd.DataFrame(filas)
    return nodos, ramas


# =============================================================================
# Validación del caso base: flujo radial exacto (backward/forward sweep)
# =============================================================================
def flujo_caso_base(nodos, ramas, escala=1.0, tol=1e-12, max_iter=200):
    """Flujo de potencia AC de la red a carga `escala` * pico. Devuelve (v_pu, i_pu por rama)."""
    n = len(nodos)
    pl = nodos.set_index("bus_id")
    s_carga = {int(b): escala * complex(pl.at[b, "P0_pu"], pl.at[b, "Q0_pu"]) for b in pl.index}
    padre = {int(r.j): int(r.i) for r in ramas.itertuples()}
    z = {int(r.j): complex(r.r_pu, r.x_pu) for r in ramas.itertuples()}
    # orden topológico: como pi(j) < j, basta recorrer las barras en orden
    orden = sorted(padre)
    v = {b: 1.0 + 0j for b in range(1, n + 1)}
    corriente = {j: 0j for j in orden}
    for _ in range(max_iter):
        # backward: corriente de cada rama = carga propia + ramas hijas
        inj = {b: np.conj(s_carga[b] / v[b]) for b in v}
        acum = dict(inj)
        for j in reversed(orden):
            corriente[j] = acum[j]
            acum[padre[j]] += acum[j]
        # forward: tensiones desde la subestación
        v_nuevo = {1: 1.0 + 0j}
        for j in orden:
            v_nuevo[j] = v_nuevo[padre[j]] - z[j] * corriente[j]
        err = max(abs(v_nuevo[b] - v[b]) for b in v)
        v = v_nuevo
        if err < tol:
            break
    else:
        return None, None            # no converge: red inviable (colapso de tensión)
    return ({b: abs(x) for b, x in v.items()}, {j: abs(c) for j, c in corriente.items()})


def es_viable(nodos, ramas, v_min_base):
    v, i = flujo_caso_base(nodos, ramas)
    if v is None:
        return False, {}
    i_lim = ramas.set_index("j")["i_max_pu"]
    info = {"v_min_base_pu": min(v.values()),
            "carga_max_rama_pct": 100.0 * max(i[j] / i_lim[j] for j in i)}
    ok = info["v_min_base_pu"] >= v_min_base and info["carga_max_rama_pct"] <= 100.0
    return ok, info


# =============================================================================
# Características de la red (para el índice y para analizar la robustez)
# =============================================================================
def caracteristicas(nodos, ramas):
    padre = {int(r.j): int(r.i) for r in ramas.itertuples()}
    prof = {1: 0}
    for j in sorted(padre):
        prof[j] = prof[padre[j]] + 1
    hijos = {}
    for j, p in padre.items():
        hijos.setdefault(p, []).append(j)
    z_total = {}
    for j in sorted(padre):                          # impedancia acumulada desde la subestación
        r = ramas.set_index("j").loc[j]
        z_total[j] = z_total.get(padre[j], 0.0) + complex(r["r_pu"], r["x_pu"])
    firma = hashlib.sha1(json.dumps(sorted(padre.items())).encode()).hexdigest()[:10]
    return {
        "n_barras": int(len(nodos)),
        "profundidad_max": int(max(prof.values())),
        "n_hojas": int(sum(1 for b in prof if b != 1 and b not in hijos)),
        "n_ramales": int(sum(1 for p, h in hijos.items() if len(h) > 1)),
        "P_total_MW": float(nodos["P0_MW"].sum()),
        "Q_total_MVAR": float(nodos["Q0_MVAR"].sum()),
        "r_total_pu": float(ramas["r_pu"].sum()),
        "x_total_pu": float(ramas["x_pu"].sum()),
        "z_max_a_subestacion_pu": float(max(abs(z) for z in z_total.values())),
        "firma_topologia": firma,
    }


# =============================================================================
# Generación de N redes
# =============================================================================
def nombre_red(semilla, k):
    return f"red_s{semilla}_{k:03d}"


def generar_redes(n, semilla, n_barras_min=20, n_barras_max=45, p_cadena_min=0.5,
                  p_cadena_max=0.9, sigma_z=0.25, sigma_carga=0.30, v_min_base=0.905,
                  max_intentos=2000, out_dir=GRID_TESTS_DIR, sobrescribir=True, verbose=True):
    if n_barras_min < 4 or n_barras_max < n_barras_min:
        raise ValueError("Se requiere 4 <= n_barras_min <= n_barras_max.")
    nodos_ref, ramas_ref = cargar_referencia()
    os.makedirs(out_dir, exist_ok=True)
    params = {"n_barras_min": n_barras_min, "n_barras_max": n_barras_max,
              "p_cadena_min": p_cadena_min, "p_cadena_max": p_cadena_max,
              "sigma_z": sigma_z, "sigma_carga": sigma_carga, "v_min_base": v_min_base}
    indice, vistas = [], {}
    for k in range(1, n + 1):
        nombre = nombre_red(semilla, k)
        carpeta = os.path.join(out_dir, nombre)
        # Generador propio de (semilla, k): la red k no depende de N.
        rng = np.random.default_rng([semilla, k])
        n_barras = int(rng.integers(n_barras_min, n_barras_max + 1))
        for intento in range(1, max_intentos + 1):
            p_cadena = float(rng.uniform(p_cadena_min, p_cadena_max))
            nodos, ramas = generar_red(rng, nodos_ref, ramas_ref, n_barras, p_cadena,
                                       sigma_z, sigma_carga)
            forma = forma_canonica({int(r.j): int(r.i) for r in ramas.itertuples()})
            if forma in vistas:                      # misma topología que una red anterior
                continue
            ok, info = es_viable(nodos, ramas, v_min_base)
            if ok:
                break
        else:
            raise RuntimeError(f"{nombre}: ninguna red viable en {max_intentos} intentos con "
                               f"{n_barras} barras. Baja sigma_z / sigma_carga / p_cadena_max, "
                               "reduce n_barras_max o baja v_min_base.")
        vistas[forma] = nombre
        car = caracteristicas(nodos, ramas)
        car["n_lineas"] = int(len(ramas))
        car["p_cadena"] = p_cadena

        if os.path.isdir(carpeta):
            if not sobrescribir:
                raise FileExistsError(carpeta)
            shutil.rmtree(carpeta)
        os.makedirs(carpeta)
        nodos.to_csv(os.path.join(carpeta, "nodes.csv"), index=False)
        ramas.to_csv(os.path.join(carpeta, "branches.csv"), index=False)
        meta = {"red": nombre, "semilla": semilla, "k": k, "intentos": intento,
                "parametros": params, "referencia": "IEEE 33-bus (data/grid)",
                **car, **info}
        with open(os.path.join(carpeta, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
        indice.append(meta | {"parametros": None})
        if verbose:
            print(f"  {nombre}: {car['n_barras']:>2} barras / {car['n_lineas']:>2} líneas, "
                  f"prof. {car['profundidad_max']:>2}, hojas {car['n_hojas']:>2}, "
                  f"ramales {car['n_ramales']:>2}, P = {car['P_total_MW']:.2f} MW, "
                  f"Vmin base = {info['v_min_base_pu']:.3f} p.u. (intentos: {intento})")

    df = pd.DataFrame(indice).drop(columns=["parametros"])
    df.to_csv(os.path.join(out_dir, f"indice_s{semilla}.csv"), index=False)
    return df


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--n", type=int, required=True, help="número de redes a generar (N)")
    ap.add_argument("--semilla", type=int, required=True, help="semilla (S)")
    ap.add_argument("--n-barras", type=int, default=None,
                    help="mismo número de barras para todas las redes (equivale a min = max)")
    ap.add_argument("--n-barras-min", type=int, default=20, help="mínimo de barras por red (default 20)")
    ap.add_argument("--n-barras-max", type=int, default=45, help="máximo de barras por red (default 45)")
    ap.add_argument("--p-cadena-min", type=float, default=0.5,
                    help="p_cadena mínimo: prob. de que la barra j cuelgue de j-1 (default 0.5)")
    ap.add_argument("--p-cadena-max", type=float, default=0.9,
                    help="p_cadena máximo; cada red sortea el suyo: alto => alimentador largo, "
                         "bajo => muy ramificada (default 0.9)")
    ap.add_argument("--sigma-z", type=float, default=0.25,
                    help="sigma lognormal del factor sobre (r, x) (default 0.25)")
    ap.add_argument("--sigma-carga", type=float, default=0.30,
                    help="sigma lognormal del factor sobre las cargas (default 0.30)")
    ap.add_argument("--v-min-base", type=float, default=0.905,
                    help="tensión mínima exigida al caso base a carga pico (default 0.905 p.u.)")
    ap.add_argument("--out-dir", default=GRID_TESTS_DIR, help="carpeta de salida")
    args = ap.parse_args()

    print(f"Generando {args.n} redes (semilla {args.semilla}) en {args.out_dir}")
    nmin = nmax = args.n_barras if args.n_barras else None
    df = generar_redes(args.n, args.semilla, nmin or args.n_barras_min, nmax or args.n_barras_max,
                       args.p_cadena_min, args.p_cadena_max, args.sigma_z, args.sigma_carga,
                       args.v_min_base, out_dir=args.out_dir)
    print(f"\nListo: {len(df)} redes. Índice: {os.path.join(args.out_dir, f'indice_s{args.semilla}.csv')}")
    print(df[["n_barras", "profundidad_max", "n_hojas", "P_total_MW", "v_min_base_pu"]].describe().loc[
        ["mean", "min", "max"]].round(3).to_string())


if __name__ == "__main__":
    main()
