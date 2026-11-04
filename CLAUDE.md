# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

University course project (PUC IEE3002, Optimización Avanzada, group G19): **PV Hosting Capacity with BESS** on the radial IEEE 33-bus distribution network, formulated as a multi-period (T = 24 h) **MISOCP** using the conic relaxation of the Branch Flow Model (Jabr / Farivar & Low), solved with Gurobi. Code, comments, output and commit messages are in Spanish.

`docs/Informe_Avance_G19.pdf` is the source of truth for the formulation. It defines the sets, parameters, variables, objective (1) and constraints (2)–(27), plus the conic-gap check (28), where Gap ≤ 1e-4 means the relaxation is exact. `modelo/misocp_hc_bess.py` implements it; check any change to the model against the informe. Research questions: (1) how much BESS changes the HC, (2) concentrated vs. distributed PV, (3) parameter sensitivity, (4) the error of the SOCP relaxation vs. the original MIQCP. Implementation plan: (1) replicate the base case without PV/BESS against a pandapower AC power flow, (2) replicate Table 1 of Blanco-Solano et al. 2026 (PV only), (3) run the full multi-period model with BESS.

## Commands

Use `python3.10`. Every script resolves its paths relative to its own file, so it can run from any working directory. There is no test suite or linter; the `verificacion/` scripts are the validation.

```bash
python3.10 preprocesamiento/generacion_red.py          # pandapower case33bw -> data/grid/*.csv
python3.10 preprocesamiento/generacion_perfil_pv.py    # data/raw/DHC_PV_MX1701.csv -> data/pv_profiles/
python3.10 preprocesamiento/generacion_perfil_carga.py # data/raw/*.xlsx (CEN) -> data/demand/
python3.10 verificacion/comprobacion_red.py            # AC power flow + interactive topology
python3.10 verificacion/comprobaciones_cargas.py       # demand vs PV consistency -> results/figures/
python3.10 verificacion/comprobacion_perfiles.py       # PV seasonal plot + heatmap -> results/figures/
python3.10 modelo/misocp_hc_bess.py                    # solve with HCConfig() defaults -> results/*.json
python3.10 modelo/grafico_resultados.py [results/<f>.json] [--no-show]   # -> results/figures/*.html
```

Run a custom scenario from the repo root (`modelo/` is a namespace package):
```python
from modelo.misocp_hc_bess import HCConfig, run_hc_bess
res = run_hc_bess(HCConfig(month=7, n_pv_max=3, n_bess_max=2, time_limit=120))
```

Environment notes: the system `python3.10` has gurobipy (academic license), pandapower, plotly and openpyxl, but its matplotlib is broken (compiled against NumPy 1.x, while NumPy 2.2 is installed). The `.venv` only has what `requirements.txt` lists, which omits `gurobipy`, `plotly`, `matplotlib` and `openpyxl`.

## Rules

- **Never use absolute paths** (e.g. `C:\Users\...`, `/Users/...`). Teammates run on different machines. Scripts compute the project root with `os.path.dirname(os.path.dirname(os.path.abspath(__file__)))` (or `Path(__file__).resolve().parents[1]`) and carry an `# OJO: NO usar rutas absolutas` comment. Keep that pattern in new scripts.
- Regenerated `data/` CSVs should be byte-identical to the committed ones unless the change is intentional.

## Architecture

**Pipeline:** `data/raw/` → `preprocesamiento/` → `data/{grid,demand,pv_profiles}/` → `modelo/misocp_hc_bess.py` → `results/*.json` → `modelo/grafico_resultados.py` → `results/figures/*.html`.

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
