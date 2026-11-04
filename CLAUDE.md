# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

University course project (PUC IEE3002, Optimización Avanzada, group G19): **PV Hosting Capacity with BESS** on the radial IEEE 33-bus distribution network, formulated as a multi-period (T = 24 h) **MISOCP** using the conic relaxation of the Branch Flow Model (Jabr / Farivar & Low), solved with Gurobi. Code, comments, output and commit messages are in Spanish.

`docs/Informe_Avance_G19.pdf` is the source of truth for the formulation. It defines the sets, parameters, variables, objective (1) and constraints (2)–(27), plus the conic-gap check (28). Its absolute 1e-4 p.u.² threshold is too loose (see Status). `modelo/misocp_hc_bess.py` implements it; check any change to the model against the informe. Research questions: (1) how much BESS changes the HC, (2) concentrated vs. distributed PV, (3) parameter sensitivity, (4) the error of the SOCP relaxation vs. the original MIQCP. Implementation plan: (1) replicate the base case without PV/BESS against a pandapower AC power flow, (2) replicate Table 1 of Blanco-Solano et al. 2026 (PV only), (3) run the full multi-period model with BESS.

Cited papers live in `docs/papers/` as `NN_primer-autor_año.pdf`. They are gitignored and each contributor downloads their own, so check which ones exist locally. `docs/papers/README.md` lists all of them with DOI and access. When a question depends on a source (formulation, parameter values, the 33-bus benchmark setup), read the PDF with `pdftotext -layout <pdf> -` instead of relying on memory. In particular, `04_blanco-solano_2026.pdf` Sec. 4.1 defines the benchmark (V 0.9–1.1 p.u., ≤ 4.6 MW exchange with the upstream grid, 300 A lines, PV at unity power factor, base load), and its Table 1 is the Etapa 2 target (HC 9262 kW with all buses as candidates, 8546 kW with only buses 2–3).

## Commands

Use the project venv, `.venv/bin/python` (Python 3.10). Every script resolves its paths relative to its own file, so it can run from any working directory. There is no test suite or linter; the `verificacion/` scripts are the validation.

```bash
.venv/bin/python preprocesamiento/generacion_red.py          # pandapower case33bw -> data/grid/*.csv
.venv/bin/python preprocesamiento/generacion_perfil_pv.py    # data/raw/DHC_PV_MX1701.csv -> data/pv_profiles/
.venv/bin/python preprocesamiento/generacion_perfil_carga.py # data/raw/*.xlsx (CEN) -> data/demand/
.venv/bin/python verificacion/comprobacion_red.py            # AC power flow + interactive topology
.venv/bin/python verificacion/comprobaciones_cargas.py       # demand vs PV consistency -> results/figures/
.venv/bin/python verificacion/comprobacion_perfiles.py       # PV seasonal plot + heatmap -> results/figures/
.venv/bin/python modelo/misocp_hc_bess.py                    # solve with HCConfig() defaults -> results/*.json
.venv/bin/python modelo/grafico_resultados.py [results/<f>.json] [--no-show]   # -> results/figures/*.html
.venv/bin/python verificacion/etapa1_caso_base.py      # Etapa 1: SOCP vs pandapower, exits 0 on PASS
.venv/bin/python verificacion/preliminar_tabla1.py     # PRELIMINAR: [4] Table 1, exact MIQCP vs relaxed MISOCP
.venv/bin/python presentacion/graficos_avance.py       # progress figures -> results/figures/avance/
```

Run a custom scenario from the repo root (`modelo/` is a namespace package):
```python
from modelo.misocp_hc_bess import HCConfig, run_hc_bess
res = run_hc_bess(HCConfig(month=7, n_pv_max=3, n_bess_max=2, time_limit=120))
```

Environment notes: `.venv` has everything in `requirements.txt` (gurobipy 10.0.3, pandapower, plotly, matplotlib 3.10, openpyxl). Don't use the system `python3.10` for plotting: its matplotlib 3.7 is compiled against NumPy 1.x and breaks under NumPy 2.2. Solve SOCP/MISOCP comparisons with tight Gurobi tolerances (BarQCPConvTol = BarConvTol = 1e-10) and judge exactness by the relative conic gap (v·l − P² − Q²)/(v·l). With default tolerances, end-branch currents come out about 1.5 % high while the informe's absolute criterion (28) still passes.

## Status and known modeling issues

`README.md` (Spanish, for the team) is the status document: what's done, results and the *trabajo remanente* checklist. Update it when the status changes.

- **Etapa 1 is done.** `verificacion/etapa1_caso_base.py` reproduces the pandapower base case with an independent SOCP and with the production model (|ΔV| ≈ 1e-11 p.u.). Equations (2)–(12) are correct in both the informe and the code.
- **Findings that affect Etapas 2–3** (PRELIMINAR; the team hasn't decided yet, so don't change the model's method unilaterally):
  - **The relaxation is not exact once PV pushes a limit to bind.** The model inflates `l` (fictitious losses) to dump PV. On [4] Table 1 the relaxed MISOCP gives 11 818 / 11 663 kW, while the exact MIQCP (cone as equality, Gurobi `NonConvex=2`) gives 9266 / 8554 kW against [4]'s 9262 / 8546. The informe's exactness argument in Sec. II.G is wrong.
  - **Objective (1) doesn't measure HC.** Summing the nodal balances gives ΣP^PV − losses = ΣP^L − P_S, so it maximizes export, and with the export limit binding any HC from 8387 to 11 806 kW is optimal. [4] maximizes ΣP^PV (its eq. 10).
  - **The old results don't show a real HC.** With `curtailment_allowed=True` the network never limits HC, so it equals n_pv_max × p_pv_max. The 6 MW in the old `results/hc_bess_results_m7_*.json` runs is that artifact.
  - **The BESS defaults (2 × 50 kW / 100 kWh) come from an EV problem** and barely change HC.
  - **The `HCConfig` defaults are wrong in two places.** The voltage fallback (0.95/1.05) contradicts [4] and the CSV (0.90/1.10). `summary["conic_exact"]` still uses the absolute gap.
- **Keep preliminary or exploratory model variants out of `modelo/`.** Put them in `verificacion/` and label them PRELIMINAR, as `preliminar_tabla1.py` is.

## Rules

- **Never use absolute paths** (e.g. `C:\Users\...`, `/Users/...`). Teammates run on different machines. Scripts compute the project root with `os.path.dirname(os.path.dirname(os.path.abspath(__file__)))` (or `Path(__file__).resolve().parents[1]`) and carry an `# OJO: NO usar rutas absolutas` comment. Keep that pattern in new scripts.
- Regenerated `data/` CSVs should be byte-identical to the committed ones unless the change is intentional.

## Architecture

**Pipeline:** `data/raw/` → `preprocesamiento/` → `data/{grid,demand,pv_profiles}/` → `modelo/misocp_hc_bess.py` → `results/*.json` → `modelo/grafico_resultados.py` → `results/figures/*.html`. Progress figures: `presentacion/graficos_avance.py` → `results/figures/avance/` (PNG and PDF). It reuses functions from `verificacion/etapa1_caso_base.py` and `verificacion/preliminar_tabla1.py`, so changing their signatures breaks it.

**`modelo/misocp_hc_bess.py`:**
- `HCConfig` dataclass holds every parameter (bases, voltage/current limits, PV/BESS sizes and counts, efficiencies, SoC bounds, solver settings). Each default cites its source as `[R1]..[R6]` in the module docstring; keep those references when you change a value.
- `build_network()` orients the tree by BFS from the slack bus and builds parent `pi(j)` and children `C(j)`. Branch quantities (`r`, `x`, `l`, `Pf`, `Qf`, `i_max`) are **indexed by the downstream node j**, not by line id. Load is `P_L(j,t) = P0_pu(j) * lambda_<customer_type>(t)`.
- `build_model()` builds the Gurobi model. Voltage and current limits are variable bounds, not constraints. `Qpv` is fixed to 0 (unity power factor, constraint 16).
- `extract_results()` computes the conic gap per branch. `save_results()` writes a JSON with `config`, `summary`, `topology` and `results`. `grafico_resultados.py` depends only on that JSON (no Gurobi needed), so changing the keys breaks the plotting script.
- `data/` is located through the argument, then `$HC_DATA_DIR`, then `<root>/data`, then `./data`. `results/` is located through the argument, then `$HC_RESULTS_DIR`, then `<root>/results`.

**Conventions shared by every file:**
- Bus numbering is 1-based (bus 1 = substation/slack). pandapower uses 0-based indices, so convert with `+1`.
- Per-unit bases: S_base = 10 MVA, V_base = 12.66 kV, I_max = 300 A ≈ 0.658 p.u.
- Only the first 32 lines of `case33bw` are used. The 5 tie-lines are dropped so the network is radial.
- Customer types per bus are set in `generacion_red.py` (19–22 `pequenas`, 24/25/30/31/32 `grandes`, the rest `regulados`) and map to the `lambda_*` demand columns.
- Profiles have 24 rows with `periodo_t` = 1..24 and `hora` = 0..23. PV `alpha_t` is in [0, 1] (Calama, 1 kW nominal). Demand is the CEN 31-Jul-2026 data, normalized by peak (default) or by mean.

`exploratorio/` holds the early exploratory script and its CSVs. The model does not use them.
