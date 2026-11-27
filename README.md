# Incorporación de BESS en Modelos de Hosting Capacity (IEEE 33-bus)

Proyecto del curso IEE3002 Optimización Avanzada para Ingeniería Eléctrica (PUC), grupo G19.

El objetivo es maximizar la capacidad de alojamiento (*Hosting Capacity*, HC) de generación fotovoltaica en una red de distribución radial, permitiendo instalar baterías (BESS). Se usa un modelo multiperíodo (24 h) basado en el *Branch Flow Model* [6], [7], resuelto con Gurobi sobre la red IEEE 33-bus [12], y se toma como paper base a Blanco-Solano et al. [4]. El informe lo formula como un MISOCP (relajación cónica), pero desde la Etapa 2 el equipo usa por defecto el **MIQCP exacto**; el MISOCP relajado queda para la pregunta 4.

**Preguntas de investigación** (informe, Sec. I.C):
1. ¿Cuánto cambia el HC con y sin BESS?
2. ¿Qué efecto tiene la generación concentrada frente a la distribuida?
3. ¿Cómo cambian las soluciones al variar los parámetros?
4. ¿Cuánto afecta la relajación cónica respecto del problema original MIQCP?

## Estado en una mirada

| Etapa (informe, Sec. III) | Estado |
|---|---|
| Datos: red, perfiles de demanda y PV | ✅ Listos en `data/` |
| Modelo completo (PV + BESS, 24 h) | ✅ Implementado en `modelo/misocp_hc_bess.py`; desde la Etapa 2 es un MIQCP exacto (ver decisiones abajo) |
| **Etapa 1:** replicar el flujo AC del caso base con el modelo | ✅ **Completada:** coincide con pandapower a ~1e-11 p.u. |
| **Etapa 2:** replicar la Tabla 1 de [4] (solo PV) | ✅ **Completada** con el modelo exacto: 9266 vs 9262 kW y 8554 vs 8546 kW, validados con pandapower |
| **Etapa 3:** modelo multiperíodo con BESS y comparación | ✅ Corrida completa (P1–P4, 26–27 nov); faltan figuras e informe (ver §5, Entrega final) |

| Pregunta de investigación | Estado |
|---|---|
| 1. HC con y sin BESS | ✅ De +1.1–1.4 % (2 × 50 kW, óptimo) a +22–25 % (2 × 2 MW, τ = 2 h) y +44 % (τ = 4 h); la energía es lo que limita |
| 2. PV concentrado vs distribuido | ✅ Carga base y 24 h (julio, sin BESS), en dos versiones que coinciden: el óptimo usa 2–3 barras; repartir cuesta hasta 10 % |
| 3. Sensibilidad de parámetros | ✅ Dos versiones complementarias: límites de red, mes y BESS (`pregunta3_sensibilidad.py`); exportación, fp, η y SoC en 24 h (`pregunta3_sensibilidad_entrega_final.py`) |
| 4. Error de la relajación cónica | ✅ +12–36 % en la Tabla 1 de [4] y +13–29 % en 24 h (dos versiones que coinciden); sus soluciones violan los límites en AC |

---

## 1. Dónde encontrar cada cosa

```
├── docs/
│   ├── Informe_Avance_G19.pdf   Informe de avance: formulación completa del modelo (ecs. 1–28)
│   └── papers/                  PDFs de las referencias (NO se suben a git; ver docs/papers/README.md)
├── data/
│   ├── raw/                     Datos crudos: demandas CEN (.xlsx) y serie PV DHC_PV_MX1701.csv
│   ├── grid/                    Red IEEE 33-bus en p.u. (ieee33_branches.csv, ieee33_nodes.csv)
│   ├── demand/                  Perfiles de demanda normalizados (pico / media) y en MW
│   └── pv_profiles/             Perfil solar alpha_t por mes y matriz anual
├── preprocesamiento/            Scripts que generan data/ a partir de data/raw/
├── verificacion/                Validaciones: red, perfiles, Etapa 1 (etapa1_caso_base.py),
│                                Etapa 2 (etapa2_tabla1.py), exacto vs relajado (preliminar_tabla1.py)
│                                y pruebas PRELIMINARES de 24 h con BESS (preliminar_24h_bess/)
├── modelo/                      misocp_hc_bess.py (modelo en Gurobi) y grafico_resultados.py
├── experimentos/                Experimentos de las preguntas de investigación (preguntas 1 a 4)
├── presentacion/                graficos_avance.py: figuras de los avances para presentar
├── exploratorio/                Primera exploración de la instancia (ya no se usa)
└── results/                     JSON de cada corrida y figures/ (figuras y dashboards)
    └── figures/avance/          Figuras de los avances (PNG para diapositivas, PDF para LaTeX)
```

- **Formulación matemática:** `docs/Informe_Avance_G19.pdf`. Es la referencia. Si se cambia el modelo, hay que contrastarlo con el informe.
- **Papers:** `docs/papers/README.md` lista todos con su DOI y el nombre de archivo esperado. Cada integrante descarga los suyos.

## 2. Cómo empezar

```bash
# 1. Entorno (Python 3.10)
python3.10 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt

# 2. Comprobar que todo funciona: debe terminar en "ETAPA 1: PASS"
.venv/bin/python verificacion/etapa1_caso_base.py
```

- **Gurobi:** se necesita la licencia académica gratuita ([gurobi.com/academia](https://www.gurobi.com/academia/academic-program-and-licenses/), activándola con `grbgetkey` desde la red UC). La licencia académica dura un año: si Gurobi dice `License expired`, hay que pedir una nueva en [portal.gurobi.com](https://portal.gurobi.com) (*Licenses → Request → Named-User Academic*).
- **No clonar el repositorio en una carpeta sincronizada con iCloud** (Documentos o Escritorio en macOS) ni con OneDrive o Dropbox. Si el sistema saca archivos del disco para ahorrar espacio, Python y git se traban al leerlos. Usar, por ejemplo, `~/GitHub/`.
  - La licencia limitada que trae el `gurobipy` de pip **no sirve como respaldo**: la de la versión 10.0.3 venció el 2024-10-28, y aun en versiones nuevas acepta solo 200 variables cuando hay restricciones cuadráticas. Alcanza para la Etapa 1 (a) y el escenario 2 de la Etapa 2, pero no para la Etapa 1 (b), el escenario 1 ni el modelo de 24 h.
- **Rutas:** todas se resuelven relativas a cada script, así que los comandos funcionan desde cualquier carpeta. **No usar rutas absolutas** (p.ej. `C:\Users\...`): solo funcionan en un PC.

## 3. Cómo ejecutar

| Qué | Comando | Salida |
|---|---|---|
| Regenerar los datos | `.venv/bin/python preprocesamiento/generacion_red.py` (y `generacion_perfil_carga.py`, `generacion_perfil_pv.py`) | `data/grid`, `data/demand`, `data/pv_profiles` |
| Validar red y perfiles | `.venv/bin/python verificacion/comprobacion_red.py` (y los demás `comprobacion*.py`) | Gráficos en `results/figures/` |
| **Etapa 1** | `.venv/bin/python verificacion/etapa1_caso_base.py` | Tablas por barra y rama, y PASS/FAIL |
| **Etapa 2** (Tabla 1 de [4]) | `.venv/bin/python verificacion/etapa2_tabla1.py [--escenario 1\|2]` | HC vs [4], validación AC y PASS/FAIL; `results/etapa2_tabla1*.json` |
| Pregunta 1: HC con BESS (24 h, cotas) | `.venv/bin/python experimentos/pregunta1_bess_cotas.py [--tamanos 0.05,0.5,1]` (~1 h por tamaño; conserva los tamaños ya guardados) | `results/pregunta1_bess_cotas.json` |
| Pregunta 2: concentrado vs distribuido | `.venv/bin/python experimentos/pregunta2_concentrado_distribuido.py` (~3 min) | `results/pregunta2_concentrado_distribuido.json` y `results/figures/pregunta2/` |
| Pregunta 2 en 24 h | `.venv/bin/python experimentos/pregunta2_24h.py [--exportacion con,sin]` (~1 h) | `results/pregunta2_24h.json` y `results/figures/pregunta2/hc_concentrado_distribuido_24h.*` |
| Pregunta 3: sensibilidad | `.venv/bin/python experimentos/pregunta3_sensibilidad.py [--bloques red,mes,bess]` (red ~15 min, mes ~30 min, bess ~35 min) | `results/pregunta3_sensibilidad.json` y `results/figures/pregunta3/` |
| Pregunta 4: error de la relajación | `.venv/bin/python experimentos/pregunta4_relajacion.py [--bess]` (~15 min) | `results/pregunta4_relajacion.json` |
| Entrega final, todas las corridas (P1–P4) | `caffeinate -dims bash experimentos/correr_experimentos.sh` (~8 h; reanudable) | `results/pregunta1_bess.json`, `results/pregunta1/`, `results/*_entrega_final.json`, `results/logs/` |
| Entrega final, pregunta 2 en 24 h | `.venv/bin/python experimentos/pregunta2_24h_entrega_final.py` (~2 min) | `results/pregunta2_24h_entrega_final.json` |
| Entrega final, pregunta 3 | `.venv/bin/python experimentos/pregunta3_sensibilidad_entrega_final.py --parte sin_bess\|bess` (~45 min sin BESS) | `results/pregunta3_sensibilidad_entrega_final.json` |
| Entrega final, pregunta 4 | `.venv/bin/python experimentos/pregunta4_relajacion_entrega_final.py` | `results/pregunta4_relajacion_entrega_final.json` |
| Tabla 1 de [4] (PRELIMINAR) | `.venv/bin/python verificacion/preliminar_tabla1.py` | HC exacto vs relajado; `results/preliminar_tabla1.json` |
| Pruebas de 24 h con BESS (PRELIMINAR) | Scripts en `verificacion/preliminar_24h_bess/` (ver su `README.md`) | `results/preliminar_24h_bess/*.jsonl` |
| Modelo completo (PV + BESS, 24 h) | `.venv/bin/python modelo/misocp_hc_bess.py` | `results/hc_bess_results_m<mes>_<fecha>.json` |
| Dashboard de una corrida | `.venv/bin/python modelo/grafico_resultados.py [results/<archivo>.json]` | HTML interactivos en `results/figures/` |
| Figuras de los avances | `.venv/bin/python presentacion/graficos_avance.py` | `results/figures/avance/` |

Para probar escenarios desde Python (en la raíz del proyecto):

```python
from modelo.misocp_hc_bess import HCConfig, run_hc_bess
res = run_hc_bess(HCConfig(month=7, n_pv_max=3, n_bess_max=2))
print(res["summary"])
```

Todos los parámetros (límites, tamaños de PV/BESS, eficiencias, tolerancias) están en `HCConfig`, con la fuente de cada valor citada en el docstring del módulo.

## 4. Qué está implementado

### Datos de entrada (`preprocesamiento/` → `data/`)
- **Red:** IEEE 33-bus [12], cargada desde pandapower (`case33bw`). Se usan solo las 32 líneas radiales, sin las 5 *tie-lines*.
  - Bases: 10 MVA y 12.66 kV.
  - Límite térmico: 300 A en todas las líneas, como en [4].
  - Límites de tensión: 0.9–1.1 p.u., como en [4], Sec. 4.1.
- **Demanda:** curvas del Coordinador Eléctrico Nacional del **31 de julio de 2026**, normalizadas para tres tipos de cliente:
  - pequeñas empresas: barras 19–22
  - grandes empresas: barras 24, 25 y 30–32
  - regulados: el resto
- **PV:** perfil horario α_t de Calama, del [Explorador Solar](https://solar.minenergia.cl/fotovoltaico) (lat. −22.3296, lon. −68.9304, 2645 m s.n.m.).
  - Hay un perfil promedio para cada mes y una matriz anual.
  - Por defecto se usa julio, el mismo mes de la demanda.

### Modelo (`modelo/misocp_hc_bess.py`)
Implementa la formulación del informe, con las decisiones del equipo para la Etapa 2 como valores por defecto de `HCConfig`:
- **Decisiones de planificación:** ubicación y tamaño de PV (binaria w_j) y de BESS (binaria z_j).
- **Operación horaria:** despacho PV, carga/descarga y SoC.
- **Red:** *Branch Flow Model* **exacto** (`exact_cone=True`): P² + Q² = v·l como igualdad (ec. (15) de [4]), un MIQCP no convexo que Gurobi resuelve con `NonConvex=2` y `FeasibilityTol=1e-9`. Con `exact_cone=False` se obtiene la relajación cónica (7) del informe, para la pregunta 4.
- **Objetivo** (`objective="pv"`): max ΣP_PV, como la ec. (10) de [4]. Sin vertimiento equivale a maximizar el HC. `objective="informe"` recupera el objetivo (1).
- **Sin vertimiento** (`curtailment_allowed=False`): P_PV = α_t · P_cap.
- **Límites de tensión:** 0.9–1.1 p.u.
- **Exactitud:** `summary["conic_exact"]` usa la brecha relativa (`tol_gap_rel = 1e-4`). Las tolerancias de Gurobi se pasan con `gurobi_params`.
- **Tabla 1 de [4]:** `config_tabla1(escenario)` arma la configuración (T = 1, perfiles planos, sin BESS, P_S ≥ −4.6 MW).
- **Resultados:** se guardan en JSON y se grafican con `grafico_resultados.py`, sin necesidad de Gurobi.

### Etapa 1 (`verificacion/etapa1_caso_base.py`)
Reproduce el flujo de potencia AC de pandapower con el modelo de optimización, en un período, sin PV ni BESS. Sin PV ni BESS, el objetivo (1) se reduce a minimizar pérdidas. Compara cinco soluciones:

| # | Solución | Qué verifica |
|---|---|---|
| 1 | Flujo AC de pandapower (Newton-Raphson) | Es la referencia física |
| 2 | SOCP escrito desde cero a partir de las ecuaciones del informe | Que las ecuaciones del informe sean correctas |
| 3 | Modelo de `modelo/` sin variables binarias | Que el código de producción no tenga errores |
| 4 | Modelo de `modelo/` con las binarias de PV/BESS fijadas en 0 | Que las partes de PV/BESS no alteren la red |
| 5 | Igual a 4, con las tolerancias por defecto de Gurobi | Precisión del solver (solo informativo) |

## 5. Resultados hasta ahora

### Etapa 1: el modelo reproduce la física de la red ✅

| Solución | V_min (barra 18) | Pérdidas | P subestación | Error máx. de corriente | Resultado |
|---|---|---|---|---|---|
| pandapower (AC) | 0.913090 p.u. | 202.677 kW | 3.9177 MW | — | referencia |
| SOCP independiente | 0.913090 | 202.677 kW | 3.9177 MW | 3e-6 | PASS |
| Producción, sin binarias | 0.913090 | 202.677 kW | 3.9177 MW | 4e-7 | PASS |
| Producción, con binarias | 0.913090 | 202.677 kW | 3.9177 MW | 8e-6 | PASS |
| Con binarias y tolerancias por defecto | 0.913090 | 202.684 kW | 3.9177 MW | **1.5 %** | solo informativo |

- Las tensiones coinciden a ~1e-11 p.u. y los valores calzan con los publicados por Baran & Wu (202.67 kW, 0.9131 p.u.).
- La relajación cónica es exacta en el caso base: la brecha relativa es 8e-7.
- **Lección para las etapas siguientes:** con las tolerancias por defecto de Gurobi, las corrientes de las ramas finales quedan hasta 1.5 % por encima del valor real. Aun así, el criterio de brecha absoluta (28) del informe (≤ 1e-4 p.u.²) las da por "exactas", porque en esas ramas P² + Q² es del orden de 5e-5. Por eso la verificación usa la **brecha relativa**, (v·l − P² − Q²)/(v·l).

### Etapa 2: Tabla 1 de [4] con el modelo exacto ✅

`verificacion/etapa2_tabla1.py` resuelve cada escenario con el modelo de producción (`config_tabla1`) y valida la solución con un flujo AC de pandapower. Ambos escenarios toman ~2 s.

| Escenario | [4] | Modelo exacto | Error | Validación AC | Resultado |
|---|---|---|---|---|---|
| 1: todas las barras | 9262 kW (barras 18: 2959, 22: 6291, 9: 12) | **9266 kW** (barras 18: 2991, 22: 6275) | +0.04 % | exporta 4600.0 kW, V 0.957–1.100 p.u., I_max 259 A | ✅ PASS |
| 2: barras 2 y 3 | 8546 kW | **8554 kW** (barra 3) | +0.09 % | exporta 4600.0 kW, V 0.947–1.014 p.u., I_max 252 A | ✅ PASS |

- En el escenario 1 el HC queda limitado a la vez por la exportación (4.6 MW) y por la tensión máxima (1.10 p.u.). En el escenario 2 lo limita solo la exportación.
- En ambos escenarios, el modelo y el flujo AC coinciden a ~1e-10 p.u., y la brecha relativa es ≤ 1e-5. El MIP gap es ≤ 1e-6, así que es el óptimo global.
- [4] reporta para el escenario 1 una exportación de 4600 kW, I_max = 259 A y V_max = 1.0934 p.u. Aquí la exportación y la corriente coinciden, pero V_max llega a 1.10 p.u. Con la ubicación que publica [4] (9: 12 kW, 18: 2959 kW, 22: 6291 kW), nuestro flujo AC da exportación 4600 kW e I_max = 259 A, igual que [4], pero V_max = 1.0987 p.u. en la barra 18, no 1.0934. La diferencia no viene de la ubicación del PV: debe estar en cómo [4] calcula o reporta la tensión. Falta revisarlo en el PDF de [4] (MDPI bloquea la lectura automática).

### Pregunta 1: HC con BESS (24 h) 🟡 (barrido completo; con 1–2 MW el rango entre cotas es amplio)

El modelo exacto de 24 h con BESS no cierra el gap en 10–20 min: tiene 1600 binarias y 768 igualdades no convexas. Por eso `experimentos/pregunta1_bess_cotas.py` no lo resuelve completo, sino que **acota su HC óptimo por los dos lados**:

| Cota | Cómo se obtiene | Por qué es válida |
|---|---|---|
| **Inferior** | El modelo exacto, con sus binarias originales, con el PV solo en las barras del caso sin BESS (18 y 22) y el BESS solo en un par de barras candidatas. Se prueban 4 pares, más las barras que elige la cota superior. | Cada solución es factible para el problema completo |
| **Superior (horaria)** | Sin el estado de carga de la BESS, cada hora es un problema de un solo período (como la Tabla 1), con la BESS como inyección neta en [−P, P]. Se resuelve en las horas de mayor sol (13–15 h) y se toma el mínimo. | Cualquier solución de 24 h, mirada en una sola hora, es factible para ese problema; por eso HC* ≤ HC de cada hora |

Caso: julio, exportación ≤ 4.6 MW, sin topes de PV activos, 2 baterías con autonomía τ = 2 h (energía = 2 × potencia).

| BESS (por batería) | HC con BESS | Frente a sin BESS (12 643 kW) | Mejor ubicación de la BESS |
|---|---|---|---|
| 50 kW / 100 kWh (caso base) | **12 818 kW (óptimo: las dos cotas coinciden)** | +176 kW (+1.39 %) | 32 y 33 |
| 250 kW / 500 kWh | **13 425 – 13 541 kW** (rango 0.9 %) | +783 a +899 kW (+6.2 a +7.1 %) | 32 y 33 |
| 500 kW / 1 MWh | **13 952 – 14 440 kW** (rango 3.5 %) | +1310 a +1797 kW (+10.4 a +14.2 %) | 32 y 33 |
| 1 MW / 2 MWh | **14 613 – 16 136 kW** (rango 10.4 %) | +1970 a +3493 kW (+15.6 a +27.6 %) | 28 y 29 (o 30 y 31: 14 612 kW) |
| 2 MW / 4 MWh | **15 871 – 19 526 kW** (rango 23 %) | +3228 a +6883 kW (+25.5 a +54.4 %) | 9 y 10, con PV en 22 y 33 (gap 5 %, mejorable) |

- **Con el caso base (2 × 50 kW) el HC es 12 818 kW, demostrado óptimo**: la cota horaria de las 14 h coincide con la solución factible. Las baterías del caso base suben el HC solo 1.4 %.
- **Rendimiento decreciente:** cada kW de BESS aporta 1.8 kW de HC con 50 kW, ≥ 1.6 kW con 250 kW, ≥ 1.3 kW con 500 kW, ≥ 1.0 kW con 1 MW y ≥ 0.8 kW con 2 MW (según la cota inferior). Lo que limita es la **energía**: el excedente de PV dura varias horas alrededor del mediodía y con τ = 2 h la batería se llena antes. La cota horaria ignora la energía (sigue en ~1.7–1.8 kW por kW), por eso el rango se abre con baterías grandes: 0 % con 50 kW, 0.9 % con 250 kW, 3.5 % con 500 kW, 10 % con 1 MW y 23 % con 2 MW. Que la cota inferior no suba al probar otros sitios (las barras de la hora crítica dan el mismo HC) sugiere que el óptimo está cerca de la cota inferior.
- **Hasta 1 MW, las baterías rinden más lejos del PV** (32 y 33 con PV en 18 y 22): con el límite de exportación activo, más pérdidas permiten más PV, el mismo efecto de la pregunta 2. Con 2 MW la mejor solución encontrada cambia de forma: BESS en 9 y 10 (a mitad del alimentador) y PV repartido entre 22 y 33 (~7.9 MW cada una). Esa corrida terminó con gap 5 % en 10 min, así que la cota inferior de 2 MW probablemente se puede mejorar.
- Todas las mejores soluciones se verificaron con un flujo AC de pandapower en las 24 horas: cumplen la exportación (4600 kW), V ≤ 1.10, I ≤ 284 A, y coinciden con el modelo a ~4e-10 p.u.
- **Por qué no se quitan las binarias μ.** Sin ellas, las baterías cargan y descargan a la vez a mediodía. Con η = 0.95 eso disipa ~10 % de su potencia, como una carga ficticia que permite instalar más PV. La cota con μ relajadas (`--cota-mu`) también es válida, pero resultó más débil que la horaria en todos los tamaños (12 868, 16 637 y 17 977 kW) y tarda 20 min.
- **Qué no funcionó** para resolver el modelo completo: partir desde la solución sin BESS, `MIPFocus=3`, cotas explícitas en los flujos, una binaria por hora solo con sol y una ventana de horas con estado de carga inicial libre. Los scripts y resultados están en `verificacion/preliminar_24h_bess/` (PRELIMINAR).

### Pregunta 2: PV concentrado vs distribuido ✅ (carga base y 24 h)

`experimentos/pregunta2_concentrado_distribuido.py` parte de la Tabla 1 de [4] (escenario 1: carga base, sin BESS, modelo exacto). Cambia cuánto se puede concentrar el PV de tres formas: limitando el número de barras con PV, poniendo un tope de capacidad por barra, o repartiéndolo igual en las 32 barras. Todo se corre con y sin el límite de exportación de 4.6 MW. Son 30 casos: 22 se resuelven al óptimo y 8 se certifican sin resolver (ver el último punto). Todas las soluciones respetan los límites en el flujo AC de pandapower.

| Caso | Con límite de exportación | Sin límite de exportación |
|---|---|---|
| PV en 1 sola barra | 8892 kW, barra 6 (−4.0 %) | 10 037 kW, barra 2 (−4.7 %) |
| **Óptimo** (sin restringir sitios) | **9266 kW**: 2 barras (22, 18) | **10 536 kW**: 3 barras (25, 18, 2) |
| Tope de 0.5–4 MW por barra (7 a 19 barras) | 9000–9194 kW (−2.9 a −0.8 %) | 10 387–10 496 kW (−1.4 a −0.4 %) |
| PV uniforme en las 32 barras | 8657 kW (−6.6 %) | 9577 kW (−9.1 %) |

- **El HC máximo se alcanza concentrando el PV en 2 o 3 barras.** Permitir más barras no lo aumenta, y obligar a repartirlo lo reduce entre 0.4 y 9 %. Con un tope de 0.25 MW por barra el HC queda en 8000 kW (32 × 0.25 MW): lo limita el tope, no la red.
- **Con el límite de exportación, el HC premia las pérdidas.** Sumando los balances, HC = exportación + carga + pérdidas = 4600 + 3715 + pérdidas [kW]. Por eso al optimizador le conviene poner el PV al final de los ramales (barras 18 y 22), donde las pérdidas son mayores (951 kW). El PV uniforme pierde solo 342 kW y por eso su HC es menor. Este efecto es consecuencia de cómo se define el HC con un límite de intercambio y conviene discutirlo en el informe.
- **Sin el límite de exportación**, lo que limita son la tensión máxima y la corriente, y el óptimo cambia de barras (25, 18 y 2).
- **Optimalidad con pocos sitios:** con 6 a 12 sitios Gurobi no cierra el gap en 2 min. Pero el HC no puede bajar al permitir más sitios, y ya con 2 sitios (3 sin límite de exportación) se alcanza el HC sin restricción de sitios. Por lo tanto esos casos tienen ese mismo HC óptimo, y el script lo certifica así, sin resolverlos.

**En el modelo de 24 h** (`experimentos/pregunta2_24h.py`: julio, sin BESS, mismos tres tipos de concentración) la conclusión se mantiene. Con muchas barras candidatas Gurobi no cierra el gap en 5 min, así que el script consolida: una solución factible de un caso también lo es de cualquier caso menos restrictivo (más sitios o un tope mayor). Por eso algunos casos se reportan como rango [mejor solución, cota superior].

| Caso (24 h, julio) | Con límite de exportación | Sin límite de exportación |
|---|---|---|
| PV en 1 sola barra | 12 147 kW, barra 6 (−3.9 %) | 13 778 kW, barra 2 (−4.9 %) |
| **Óptimo** (sin restringir sitios) | **12 643 kW**: 2 barras (22, 18) | **14 484 – 14 897 kW**: 3 barras (25, 18, 20) |
| 2 barras como máximo | 12 643 kW (el óptimo) | 14 414 kW (óptimo para 2 barras) |
| Tope de 0.5 MW por barra (27–30 barras) | 12 073 kW (−4.5 %) | 14 107 kW (−2.6 %) |
| Tope de 1–4 MW por barra | 12 418 – 12 632 kW (−1.8 a −0.1 %) | 14 336 – 14 897 kW |
| PV uniforme en las 32 barras | 11 833 kW (−6.4 %) | 13 046 kW (−9.9 % o más) |

- Con exportación ≤ 4.6 MW todo está resuelto al óptimo salvo los topes de 1, 2 y 4 MW, que quedan en rangos de 0.2–1 %.
- Sin límite de exportación, el caso sin restricción de sitios queda en un rango de 2.9 %. La mejor solución tiene 3 barras.
- La figura está en `results/figures/pregunta2/hc_concentrado_distribuido_24h.png`.

### Pregunta 3: sensibilidad de los parámetros 🟡

`experimentos/pregunta3_sensibilidad.py` cambia un parámetro a la vez, con el modelo exacto, y valida cada solución con el flujo AC. Figura: `results/figures/pregunta3/sensibilidad.png`.

**Límites de red** (Tabla 1 de [4], escenario 1, carga base; caso base: exportación 4.6 MW, V_max 1.10 p.u., I_max 300 A → 9266 kW):

| Parámetro | Valores → HC |
|---|---|
| Exportación máxima | 0 MW → 4203 kW · 2.3 MW → 6846 · **4.6 MW → 9266** · 6.9 MW o más → 10 536 (deja de estar activa) |
| V_max, con exportación ≤ 4.6 MW | 1.05 → 8861 kW · 1.06 → 8952 · 1.08 → 9103 · **1.10 → 9266** |
| V_max, sin límite de exportación | 1.05 → 10 279 kW · 1.06 → 10 336 · 1.08 → 10 431 · 1.10 → 10 536 |
| I_max, con exportación ≤ 4.6 MW | 200 A → 7765 kW · 250 → 9128 · **300 → 9266** · 400 → 9368 |
| I_max, sin límite de exportación | 200 A → 7765 kW · 250 → ≥ 9183 · 300 → 10 536 · 400 → 13 099 |

- **El límite de exportación es el parámetro dominante.** Cada MW de exportación agrega más de 1 MW de HC (2.3 MW → +2.6 MW), porque también crecen las pérdidas. Sobre ~5.8 MW deja de estar activo y mandan la tensión y la corriente.
- **V_max influye poco**: entre 1.05 y 1.10 p.u. el HC cambia 2.5–4.6 %. Lo que más cambia es dónde se instala el PV.
- **I_max importa mucho sin límite de exportación** (~27 kW de HC por A). Con el límite, pasa a dominar solo si baja de ~250 A.

**Perfil de PV por mes** (24 h, sin BESS, exportación ≤ 4.6 MW; la demanda es siempre la del 31 de julio): el HC va de 11 173 kW (octubre, α máx 0.813) a 13 075 kW (junio, α máx 0.697). En todos los meses se cumple **HC × α_max ≈ 9.1 MW**: el HC lo fija la hora de más sol, en la que la inyección de PV llega al límite. El PV siempre queda en las barras 22 y 18. Para diseñar hay que mirar el mes con el α más alto (octubre), no julio: con el perfil de julio el HC es 13 % mayor que con el de octubre.

**Parámetros de la BESS** (24 h, julio, 2 × 0.5 MW en 32 y 33, PV en 18 y 22; cota inferior con 5 min por caso, gap ≤ 0.2 %; caso base τ = 2 h, η = 0.95, SoC 10–90 % → 13 952 kW):

| Cambio | HC | Frente al caso base |
|---|---|---|
| τ = 1 h (0.5 MWh por batería) | 13 426 kW | −3.8 % |
| τ = 4 h (2 MWh por batería) | 14 110 kW | +1.1 % |
| η = 0.90 | 13 994 kW | +0.3 % |
| η = 1.00 | 13 899 kW | −0.4 % |
| SoC 20–80 % | 13 687 kW | −1.9 % |
| SoC 0–100 % | 14 070 kW | +0.8 % |

- **Lo que importa es la energía útil de la batería, no su potencia.** Con τ = 1 h, la batería de 0.5 MW / 0.5 MWh da 13 426 kW, lo mismo que la de 0.25 MW / 0.5 MWh de la pregunta 1 (13 425 kW). Más energía útil (τ mayor o ventana de SoC más amplia) sube el HC, con rendimiento decreciente.
- **La eficiencia casi no cambia el HC** (< 0.5 %, del orden del gap). Una eficiencia menor lo sube un poco, porque las pérdidas de la batería absorben PV.
- **c_deg no cambia el HC**: con el objetivo max ΣP_PV no aparece en el modelo.
- Falta, si se quiere: repetir el bloque de la BESS con otros tamaños y con más tiempo por caso.

### Pregunta 4: error de la relajación cónica ✅

`experimentos/pregunta4_relajacion.py` resuelve cada caso con el modelo exacto (MIQCP, P² + Q² = v·l) y con la relajación del informe (MISOCP, P² + Q² ≤ v·l), con el mismo objetivo (max ΣP_PV). Luego instala el PV que eligió el relajado en un flujo AC de pandapower para ver si la red real lo soporta. El relajado se resuelve con tolerancias de barrera de 1e-10, para que la brecha medida no sea ruido numérico.

| Caso | HC exacto | HC relajado | Error | Pérdidas ficticias del relajado | El PV del relajado en el flujo AC |
|---|---|---|---|---|---|
| Tabla 1, esc. 1, exportación ≤ 4.6 MW | 9266 kW | 11 818 kW | **+27.6 %** | 2707 kW | exporta 6851 kW, V 1.143 p.u., I 350 A |
| Tabla 1, esc. 1, sin límite | 10 536 kW | 11 818 kW | +12.2 % | 2710 kW | V 1.143 p.u., I 351 A |
| Tabla 1, esc. 2, exportación ≤ 4.6 MW | 8554 kW | 11 663 kW | **+36.3 %** | 2785 kW | exporta 7587 kW, I 366 A |
| Tabla 1, esc. 2, sin límite | 10 096 kW | 11 673 kW | +15.6 % | 2712 kW | I 366 A |
| 24 h julio, sin BESS, exportación ≤ 4.6 MW | 12 643 kW | 16 334 kW | **+29.2 %** | 1827 kW (media) | exporta 6924 kW, V 1.144 p.u., I 352 A |
| 24 h julio, sin BESS, sin límite | 14 484 – 14 897 kW (pregunta 2) | 16 334 kW | +9.6 a +12.8 % | 1939 kW (media) | V 1.144 p.u., I 352 A |
| 24 h julio, 2 BESS de 50 kW | 12 818 kW (pregunta 1) | 16 473 kW | **+28.5 %** | 1531 kW (media) | exporta 6924 kW, V 1.144 p.u., I 352 A |

- **La relajación no es exacta en ningún caso con PV, y su error es grande: entre 10 y 36 %.** La brecha cónica relativa llega a 1, es decir, hay ramas con corriente l > 0 y casi sin flujo: pura corriente ficticia. Solo es exacta sin PV, en el caso base de la Etapa 1, donde el objetivo minimiza las pérdidas.
- **Toda solución relajada viola los límites reales.** En el flujo AC, el PV que elige el relajado lleva la tensión a 1.14 p.u. y la corriente a 350–366 A (límite 300 A), y exporta 6.9–7.6 MW cuando el límite es 4.6 MW.
- **El HC relajado no depende del límite de exportación** (11 818 kW con y sin él; 16 334 kW en 24 h). El relajado disipa el PV sobrante en pérdidas ficticias hasta que lo detiene el límite térmico (l ≤ I_max²). Por eso el error es mayor justo cuando el límite de exportación está activo (28–36 %), que es el caso del proyecto.
- **Tampoco sirve como cota superior útil.** Es una cota válida del HC exacto, pero muy holgada: con 2 × 50 kW da 16 473 kW, frente al óptimo demostrado de 12 818 kW. La cota horaria de la pregunta 1 es mucho más ajustada.
- El exacto de 24 h sin límite de exportación no cerró el gap en 10 min. Con las soluciones de la pregunta 2 en 24 h, su HC óptimo está entre 14 484 y 14 897 kW, así que el error del relajado está entre 9.6 y 12.8 %.

### Entrega final: experimentos de 24 h con BESS ✅ (corridos; faltan figuras e informe)

**Dos versiones en paralelo de las preguntas 2–4.** Las preguntas 2 (24 h), 3 y 4 se hicieron dos veces, por separado. Las de arriba (`pregunta2_24h.py`, `pregunta3_sensibilidad.py`, `pregunta4_relajacion.py`) son una versión; las de esta sección llevan el sufijo `_entrega_final` (scripts y JSON) y usan `experimentos/comun_24h.py` y `sin_bess_24h.py`. Donde se cruzan, coinciden:
- **Pregunta 2 en 24 h:** mismo HC con límite de exportación (12 643 kW en 22 y 18), con PV en una barra (12 147–12 148 kW) y uniforme (11 833 kW). Sin límite, esta versión resuelve el óptimo (14 484 kW, gap 6e-5, resolviendo solo las horas críticas), lo que cierra el rango 14 484 – 14 897 kW de la otra.
- **Pregunta 3:** son complementarias. La otra varía los límites de red (Tabla 1), el mes y τ; esta varía la exportación y el fp en 24 h, y η y el SoC con BESS. Con 2 × 0.5 MW en 32 y 33 coinciden: base 13 952 kW, η = 0.90 → 13 994 vs 14 000 kW, SoC 20–80 % → 13 687 kW en ambas.
- **Pregunta 4:** ambas dan 12 643 → 16 334 kW (+29.2 %) en 24 h sin BESS con límite. Sin límite, el óptimo de esta versión fija el error en +12.8 % (la otra da 9.6–12.8 %). La otra agrega la Tabla 1 y 2 × 50 kW; esta, 2 × 0.5 y 2 × 2 MW.

**Método de la pregunta 1 (decisión del equipo): combinar los dos enfoques** con la configuración de la sección anterior: 2 BESS de tamaño fijo y la restricción (19) del informe para el SoC final.
- **Cota superior:** la cota horaria de `pregunta1_bess_cotas.py` (`comun_24h.cota_horaria`). Es válida para el problema completo, con PV y BESS en cualquier barra, y no depende de τ.
- **Solución (cota inferior):** sitios fijos, cada combinación resuelta exacta y certificada con el flujo AC hora a hora. Se enumeran:
  - los 28 pares de las 8 barras candidatas, con el PV en los sitios del caso sin BESS;
  - todos los casos que probó `pregunta1_bess_cotas.py`;
  - el par de BESS y las barras de PV que sugiere la hora crítica de la cota horaria.
- **Verificación:** la mejor combinación se resuelve también con el PV libre, partiendo de la solución completa (`pregunta1_verificacion.py`, tamaños ≥ 0.5 MW).

**Cómo reproducir:** `caffeinate -dims bash experimentos/correr_experimentos.sh` corre todo (~8 h; cada script salta lo que ya está en `results/`). El registro de la corrida del 26–27 nov queda en `results/logs/`.

**Decisiones del equipo para la entrega final** (aplicadas en `experimentos/comun_24h.py`):
- **D3, tamaño de BESS:** 2 unidades de tamaño fijo, de P ∈ {0.05, 0.25, 0.5, 1, 2} MW y τ·P MWh cada una (los tamaños de `pregunta1_bess_cotas.py`). Sin costo de inversión: el costo se evalúa después con la curva HC vs tamaño.
- **D3a, duración:** τ = E/P = 2 h, más un barrido con τ = 4 h, solo con el límite de exportación.
- **D3b, sitios de BESS:** 8 barras candidatas (6, 9, 13, 18, 22, 25, 29, 33: extremos y puntos medios de los alimentadores), más las barras que proponen las cotas.
- **D5, día de diseño:** julio (perfil PV promedio del mes y demanda CEN del 31-jul).
- **D6, límite de exportación de 4.6 MW:** se corre con y sin él.
- **D7, factor de potencia:** unitario como caso base, más una sensibilidad con fp 0.95 absorbiendo.
- **D9, SoC final:** restricción (19) del informe, SoC_24 ≥ κ_0 E. Con SoC cíclico el HC casi no cambia (ver el registro de abajo).
- **D8 y D10, método:**
  - El MIQCP exacto de 24 h con BESS no cierra el gap si tiene que elegir los sitios (12–24 % en 20 min). Por eso los sitios se fijan y se enumeran, como se explica arriba.
  - Los BESS cargan solo en horas con sol y descargan solo en las demás (`bess_horas_carga`). Esto reemplaza las binarias μ y excluye cargar y descargar a la vez. En la prueba con 2 MWh dio el mismo HC que con binarias y fue 20× más rápido.
- **Sin BESS** las horas no se acoplan. `experimentos/sin_bess_24h.py` resuelve solo las horas críticas y certifica con un flujo AC de 24 h. Da el mismo HC que el modelo completo (12 642.6 kW) en 3 s en vez de 97 s.

**Pregunta 1: HC con 2 BESS de P MW** (`results/pregunta1_bess.json`, julio, 24 h). Todas las soluciones se certificaron con el flujo AC hora a hora. La cota superior horaria es la del problema completo, con PV y BESS en cualquier barra.

| Por batería | 0 | 0.05 MW | 0.25 MW | 0.5 MW | 1 MW | 2 MW |
|---|---|---|---|---|---|---|
| **Exportación ≤ 4.6 MW, τ = 2 h** | 12 643 | 12 818 (+1.4 %) | 13 425 (+6.2 %) | 13 952 (+10.4 %) | 14 613 (+15.6 %) | 15 859 (+25.4 %) |
| Cota superior | — | 12 818 | 13 541 | 14 440 | 16 136 | 19 526 |
| BESS / PV | — / 22, 18 | 32+33 / 22, 18 | 32+33 / 22, 18 | 32+33 / 22, 18 | 28+29 / 22, 17, 16 | 9+10 / 22, 33 |
| **Sin límite, τ = 2 h** | 14 483 | 14 640 (+1.1 %) | 15 233 (+5.2 %) | 15 685 (+8.3 %) | 16 423 (+13.4 %) | 17 670 (+22.0 %) |
| Cota superior | — | 14 641 | 15 242 | 16 023 | 17 637 | 20 715 |
| BESS / PV | — / 25, 18, 2 | 31+33 / 25, 18 | 32+33 / 25, 16, 17 | 32+33 / 25, 16 | 32+33 / 25, 13 | 28+30 / 22, 12 |
| **Exportación ≤ 4.6 MW, τ = 4 h** | 12 643 | 12 818 (+1.4 %) | 13 541 (+7.1 %) | 14 440 (+14.2 %) | 15 963 (+26.3 %) | 18 170 (+43.7 %) |
| Cota superior | — | 12 818 | 13 541 | 14 440 | 16 136 | 19 526 |

Valores en kW.

- **El caso base del informe (2 × 50 kW) sube el HC solo 1.1–1.4 %, y es el óptimo demostrado** (coincide con la cota). Con baterías de MW, el HC sube hasta +22–25 % con τ = 2 h y hasta +44 % con τ = 4 h.
- **Con τ = 2 h limita la energía, no la potencia.** Con τ = 4 h el HC alcanza la cota (que ignora la energía) hasta 0.5 MW, y con 2 MW pasa de +25 % a +44 %. El excedente de PV dura varias horas alrededor del mediodía (2–6 horas activas), y una batería de 2 h se llena antes de que termine.
- **Rendimientos decrecientes:** con el límite de exportación, cada kW de BESS aporta ~1.8 kW de HC con 50 kW, ~1.3 kW con 0.5 MW y ~0.8 kW con 2 MW.
- **Las baterías rinden más lejos del PV.** Hasta 0.5–1 MW, el mejor par es 32 + 33, en el extremo del alimentador 6–33 (sin PV). Con baterías grandes el PV cambia de barras (p.ej. a 22 y 33 con 2 × 2 MW) y la BESS se mueve a mitad de alimentador.
- **Rango entre solución y cota:**
  - ≤ 0.1 % hasta 0.25 MW;
  - 2–3.5 % con 0.5 MW;
  - 4–10 % con 1 MW;
  - 17–23 % con 2 MW y τ = 2 h, porque la cota horaria ignora la energía.
- **Verificación con PV libre** (`results/pregunta1_verificacion.json`, misma ubicación de BESS, arranque desde la solución): en ninguna configuración se encontró un HC mayor. El techo de la mejora por mover el PV es +0.01 % con 0.5 MW (con límite) y de +2 a +7 % con 1–2 MW. Esa cota vale solo para esos sitios de BESS; la cota del problema completo sigue siendo la horaria.
- **Diferencia con `pregunta1_bess_cotas.py` en 2 × 2 MW** (15 871 vs 15 859 kW, 0.08 %): hipótesis, falta revisar su despacho. Las binarias μ impiden cargar y descargar a la vez en *una* batería, pero no que una cargue mientras la otra descarga. Eso disiparía energía en las pérdidas de ida y vuelta. Las ventanas de carga de este barrido lo excluyen.

**Registro, ya superado: barrido con presupuesto de energía y SoC cíclico** (`results/pregunta1_bess_presupuesto.json`, con límite de exportación, τ = 2 h, PV fijo en 18 y 22, certificado en AC):

| Σ E ≤ B [MWh] | 0 | 0.5 | 1 | 2 | 4 | 8 |
|---|---|---|---|---|---|---|
| HC [kW] | 12 643 | 13 086 | 13 426 | 13 954 | 14 653 | 15 801 |

Coincide a ±0.3 % con el barrido de arriba con la misma energía total, así que el SoC cíclico vs (19) casi no cambia el HC.

**Pregunta 2 en 24 h** (`results/pregunta2_24h_entrega_final.json`, `experimentos/pregunta2_24h_entrega_final.py`): mismo patrón que en carga base.

| Caso | Con límite de exportación | Sin límite de exportación |
|---|---|---|
| PV en 1 sola barra | 12 148 kW (−3.9 %) | 13 778 kW (−4.9 %) |
| **Óptimo** | **12 643 kW**: 2 barras (22, 18) | **14 484 kW**: 3 barras (25, 18, 2) |
| PV uniforme en las 32 barras | 11 833 kW (−6.4 %) | 13 047 kW (−9.9 %) |

**Pregunta 3 sin BESS** (`results/pregunta3_sensibilidad_entrega_final.json`, `experimentos/pregunta3_sensibilidad_entrega_final.py`):

| Límite de exportación | 0 MW | 2.3 MW | **4.6 MW** | 6.9 MW | sin límite |
|---|---|---|---|---|---|
| HC [kW] | 5 626 | 9 265 | **12 643** | 14 484 | 14 484 |

- Desde ~6 MW de límite, limitan la corriente y la tensión, no la exportación.
- **Con fp fijo 0.95 absorbiendo, el HC baja a 11 292 kW**, con o sin límite de exportación (gap ≤ 0.3 %). Absorber reactivos baja la tensión, pero sube la corriente, y se activa I_max (300 A). Un fp fijo empeora el HC; un control de reactivos variable podría mejorarlo. Esto responde la pregunta del feedback sobre el fp unitario.

**Pregunta 3 con BESS** (2 × 0.5 MW / 1 MWh, τ = 2 h; base: 13 952 kW con límite y 15 685 kW sin límite):

| Parámetro | Caso | HC [kW] | Cambio |
|---|---|---|---|
| Eficiencia η_ch = η_dis | 0.90 | 14 000 | +0.3 % |
| | 0.98 | 13 920 | −0.2 % |
| Ventana de SoC (energía útil) | [0.20, 0.80] (60 %) | 13 687 | −1.9 % |
| | [0.05, 0.95] (90 %) | 14 049 | +0.7 % |
| fp 0.95 absorbiendo | con límite de exportación | 11 933 (gap 0.7 %) | −14.5 % |
| | sin límite de exportación | 11 877 (gap 3 %) | −24.3 % |

- **La eficiencia casi no importa, y menor eficiencia da un poco más de HC.** Como la energía limita, una batería que pierde más se llena más lento y absorbe PV por más tiempo: las pérdidas actúan como un sumidero.
- **La energía útil sí importa:** el HC cambia de forma casi lineal con la ventana de SoC.
- **El fp fijo 0.95 deja el HC por debajo del caso sin BESS con fp unitario**, porque la corriente llega primero a 300 A.

**Pregunta 4 en 24 h** (`results/pregunta4_relajacion_entrega_final.json`, `experimentos/pregunta4_relajacion_entrega_final.py`): MIQCP exacto vs MISOCP relajado del informe.

| Caso | Exacto | Relajado | Sobreestimación | Pérdidas ficticias | Flujo AC del PV relajado |
|---|---|---|---|---|---|
| Sin BESS, exportación ≤ 4.6 MW | 12 643 kW | 16 334 kW | +29.2 % | 43.8 MWh/día | 1.143 p.u., 352 A, 6.9 MW de exportación (h 10–15) |
| Sin BESS, sin límite | 14 483 kW | 16 334 kW | +12.8 % | 44.0 MWh/día | 1.142 p.u., 353 A (h 11–15) |
| 2 × 0.5 MW, exportación ≤ 4.6 MW | 13 952 kW | 17 514 kW | +25.5 % | 43.0 MWh/día | 1.147 p.u., 352 A (h 10–15) |
| 2 × 2 MW, exportación ≤ 4.6 MW | 15 859 kW | 19 503 kW | +23.0 % | 46.2 MWh/día | 1.155 p.u., 352 A (h 10–16) |

- **La relajación sobreestima el HC en 13–29 % y sus soluciones no son físicamente factibles:** el PV relajado viola tensión, corriente y exportación en todas las horas de sol fuertes.
- **El error es mayor con el límite de exportación**, porque el relajado "disipa" en pérdidas ficticias lo que no puede exportar. Es el mismo efecto de la Tabla 1 de [4] (+28 % y +36 %).

### Hallazgos de la revisión del modelo (motivaron las decisiones de la Etapa 2)

Se revisó la formulación contra [4], [6] y [7], y se probó numéricamente. Las ecuaciones de red (2)–(12) son correctas. Los problemas aparecen cuando se agrega PV:

1. **La relajación deja de ser exacta cuando el PV lleva la red a sus límites.** Con un límite activo, el modelo relajado inventa "pérdidas ficticias" para disipar PV y sobreestima el HC. En el escenario 1 de la Tabla 1 de [4]:

   | Modelo | HC escenario 1 | HC escenario 2 |
   |---|---|---|
   | [4], reportado | 9262 kW | 8546 kW |
   | MIQCP exacto (cono como igualdad, Gurobi `NonConvex=2`) | **9266 kW** (+0.04 %), en barras 18 y 22 | **8554 kW** (+0.09 %) |
   | MISOCP relajado (el del informe) | 11 818 kW (+28 %), con 2723 kW de pérdidas ficticias | 11 663 kW (+36 %) |

   El flujo AC de pandapower confirma que la solución exacta es físicamente válida: exportación de 4600 kW, V_max = 1.10 p.u. e I_max = 258 A. En cambio, el PV de la solución relajada viola los límites reales: exporta 6865 kW, llega a 1.14 p.u. y a 351 A.
2. **El objetivo (1) no mide el HC.**
   - Sumando los balances nodales, ΣP_PV − pérdidas = ΣP_carga − P_S, de modo que (1) maximiza la exportación hacia la red de transmisión.
   - Cuando el límite de exportación está activo, cualquier HC entre **8387 y 11 806 kW** tiene el mismo valor óptimo.
   - [4] maximiza ΣP_PV (su ecuación 10).
3. **Los resultados guardados en `results/hc_bess_results_m7_*.json` (HC = 6 MW) no son una capacidad de alojamiento.**
   - Con vertimiento permitido, el HC resulta siempre n_pv_max × p_pv_max (3 × 2 MW), sin que la red llegue a sus límites.
   - Además, para reproducir [4] se requiere p_pv_max ≥ 6.3 MW y un límite de exportación de 4.6 MW.
4. **El tamaño de los BESS** (2 × 50 kW / 100 kWh, tomado de un problema de vehículos eléctricos) cambia el HC en solo ~0.1 MW. Con ese tamaño, la pregunta 1 tendría una respuesta trivial.

## 6. Figuras para la presentación

Se generan con `.venv/bin/python presentacion/graficos_avance.py` (~7 s) en `results/figures/avance/`. Cada figura está en PNG (para diapositivas) y en PDF (vectorial, para LaTeX).

**A. Contexto y datos**

| Figura | Qué muestra |
|---|---|
| `01_topologia_ieee33` | Red radial IEEE 33-bus (troncal 1–18 y ramales desde las barras 2, 3 y 6), con cada barra coloreada según su tipo de cliente, que determina su perfil horario de demanda. |
| `02_perfiles_demanda` | Perfiles de demanda del CEN (31-jul-2026) normalizados al pico. Los regulados tienen punta a las 19 h y valle a las 4 h (0.48); las grandes empresas son casi planas (≥ 0.95). |
| `03_pv_vs_demanda` | El PV de julio en Calama se concentra entre las 8 y las 17 h (máximo 0.72 a las 13 h), mientras que la punta residencial ocurre a las 19 h, sin sol. Ese desfase es el espacio que puede aprovechar un BESS. |

**B. Etapa 1 (resultado principal)**

| Figura | Qué muestra |
|---|---|
| `04_etapa1_tensiones` | El modelo reproduce las tensiones de pandapower en las 33 barras (máx \|ΔV\| = 3.3×10⁻¹² p.u.). El mínimo es 0.9131 p.u. en la barra 18, sobre el límite de 0.90. |
| `05_etapa1_corrientes` | El modelo reproduce las corrientes de las 32 ramas (máx \|ΔI\|/I = 3.8×10⁻⁷). La cabecera lleva 210.4 A, bajo el límite térmico de 300 A. |
| `06_etapa1_resumen_errores` | Los tres modelos verificados reproducen el flujo AC con errores muy inferiores a la tolerancia. Con las tolerancias por defecto de Gurobi, la corriente (1.5 %) y la brecha relativa (3 %) quedan fuera. |
| `07_etapa1_brecha_relativa` | El umbral absoluto (28) no detecta errores en las ramas donde P² + Q² < 10⁻⁴ (ramas 18, 22 y 33). Con tolerancias por defecto, la corriente llega a errar 1.5 % aunque (28) "pase"; por eso se propone la brecha relativa. |

**C. Etapa 2: hallazgos PRELIMINARES** (calculados con `verificacion/preliminar_tabla1.py`)

| Figura | Qué muestra |
|---|---|
| `08_preliminar_tabla1_hc` | El MIQCP exacto replica la Tabla 1 de [4] (9266 vs 9262 kW y 8554 vs 8546 kW). La relajación del informe la sobreestima en 28 % y 36 %, mediante unos 2700–2800 kW de pérdidas ficticias. |
| `09_preliminar_validacion_ac` | Al simular en un flujo AC el PV de la solución relajada, la red exporta 6865 kW (límite: 4600), llega a 1.1408 p.u. y a 351 A. La solución exacta queda justo en el límite de exportación, sin violar ningún límite. |
| `10_preliminar_indeterminacion_obj1` | Con el objetivo (1) del informe, que equivale a maximizar la exportación, cualquier HC entre 8387 y 11 806 kW alcanza el mismo óptimo. El objetivo (10) de [4] sí determina el HC. |
| `11_preliminar_ubicacion_pv` | El MIQCP exacto ubica el PV en las mismas barras que [4]: la 22 (6275 vs 6291 kW) y la 18 (2991 vs 2959 kW). |

## 7. Trabajo remanente

**Decisiones del equipo** (tomadas para la Etapa 2, ya aplicadas en `HCConfig`):
- [x] **Modelo para los resultados de HC:** MIQCP exacto (`NonConvex=2`). El MISOCP relajado queda para responder la pregunta 4. Esto cambia lo que dice el informe.
- [x] **Objetivo:** maximizar ΣP_PV, como [4], en vez de (1).
- [x] **Vertimiento:** el HC se define sin vertimiento.
- [x] **BESS:** se mantiene la escala actual (2 × 50 kW / 100 kWh).
- [x] **Límites de tensión oficiales:** 0.9–1.1 p.u., como [4] y los CSV.
- [x] **Límite de exportación de 4.6 MW también en 24 h** (`p_s_ref_pu = -0.46` por defecto), como el intercambio máximo de [4]. Así los resultados de 24 h se comparan con la Etapa 2, y es el límite que la BESS ayuda a levantar. Hay que declarar en el informe que con este límite el HC premia las pérdidas (ver pregunta 2), y en la pregunta 3 variarlo (4.6 MW, uno mayor y sin límite). Para correr sin límite: `HCConfig(p_s_ref_pu=None)`.
- [x] **Barrido de tamaños de BESS (pregunta 1):** 2 baterías con τ = 2 h y potencias 0.05 (caso base), 0.25, 0.5, 1 y 2 MW cada una. El caso base sigue siendo 2 × 50 kW.

**Etapa 2: replicar la Tabla 1 de [4]**
- [x] Agregar al modelo una configuración "Tabla 1": `config_tabla1(escenario)`.
- [x] Escenario 2 (solo barras 2 y 3), validado con pandapower: 8554 kW, PASS.
- [x] Escenario 1 (todas las barras), validado con pandapower: 9266 kW, PASS.
- [ ] Actualizar las figuras 08–11 de `presentacion/` (todavía dicen PRELIMINAR) con los resultados de la Etapa 2.

**Ajustes al código**
- [x] Exponer las tolerancias de Gurobi en `HCConfig` (`gurobi_params`) y usar la brecha relativa en `summary["conic_exact"]`.
- [x] Cambiar los valores por defecto de `HCConfig` a 0.90/1.10 p.u.
- [ ] Corregir comentarios desactualizados (numeración de restricciones, I_base).

**Etapa 3 y análisis**
- [x] Modelo multiperíodo (24 h) con BESS, y comparar el HC con y sin baterías (pregunta 1): con 2 × 50 kW el HC es 12 818 kW (+1.4 %, óptimo); con 2 × 0.25, 0.5, 1 y 2 MW, +6–7 %, +10–14 %, +16–28 % y +26–54 %. Ver resultados arriba.
- [x] Barrido de tamaños de BESS con `experimentos/pregunta1_bess_cotas.py --tamanos ...` (~1 h por tamaño; el JSON conserva los tamaños ya calculados): 0.05, 0.25, 0.5, 1 y 2 MW.
- [ ] Cerrar el rango entre cotas con baterías grandes (10 % con 1 MW, 23 % con 2 MW): haría falta una cota superior que considere la energía de la BESS, y una cota inferior mejor para 2 MW (la mejor corrida terminó con gap 5 %).
- [x] Generación concentrada vs distribuida (pregunta 2), en carga base: ver resultados arriba.
- [x] Pregunta 2 en el modelo de 24 h, sin BESS: la conclusión de carga base se mantiene (2–3 barras; uniforme −6 a −10 %).
- [x] Análisis de sensibilidad (pregunta 3): límites de red, perfil de PV por mes y parámetros de la BESS (τ, η, SoC; c_deg no influye).
- [ ] Pregunta 3, opcional: el bloque de la BESS con otros tamaños y más tiempo por caso; la pregunta 2 con BESS.
- [x] Cuantificar el error de la relajación frente al MIQCP (pregunta 4): +10 a +36 %, y toda solución relajada viola los límites en el flujo AC. Ver resultados arriba.
- [ ] Gráficos de despacho, perfiles de tensión y ciclado de baterías.
- [ ] Decidir qué versión de las preguntas 2–4 va al informe, o cómo combinarlas (ver §5, Entrega final).

**Informe**
- [ ] Reflejar las decisiones de la Etapa 2: modelo exacto (MIQCP), objetivo ΣP_PV, sin vertimiento y V 0.9–1.1 p.u.
- [ ] Corregir el argumento de exactitud de la Sec. II.G: la relajación no es exacta solo porque las cargas sean constantes.
- [ ] Cambiar el umbral de (28) a una brecha relativa.
- [ ] Notación: l = |I|² (no |l|²), Q_PV ∈ ℝ vs (16), y el texto de la restricción 15 ("= 1" vs ≤ z_j).
- [ ] Indicar los valores usados de V_min, V_max y P_S,ref, y el significado y las unidades de c_deg.

## 8. Cómo colaborar

Para no pisarnos el trabajo, cada tarea va en su propia rama y entra a `main` mediante un *pull request* (PR) que otro integrante revisa:

```bash
git switch main && git pull           # partir desde main actualizado
git switch -c nombre-de-la-tarea      # una rama por tarea
# ... cambios y commits ...
git push -u origin nombre-de-la-tarea
gh pr create                          # o el botón "Compare & pull request" en GitHub
```

Después del merge, actualizar `main` con `git switch main && git pull` y borrar la rama con `git branch -d nombre-de-la-tarea`.

## Referencias

Los PDFs se guardan en `docs/papers/`; ver `docs/papers/README.md`.

[1] S. Landl, K. Harald. "Mitigating Overvoltage in Power Grids with Photovoltaic Systems by Energy Storage," *Environmental and Climate Technologies*, 470-483, Jul. 2022, doi: 10.2478/rtuect-2022-0036.

[2] R. Mishan, X. Fu, C. Hingu, M. Ben-Idris, "Impacts of Inertia and Photovoltaic Integration on Existing and Proposed Power System Transient Stability Parameters," *Energies*, 18, no. 11: 2915, June, 2025, doi: 10.3390/en18112915.

[3] S. Kulkarni, K. Duan, G. Pang, A. Bhatti, "Recent advancements and perspectives in lithium-ion battery technology," *Energy Strategy Reviews*, vol. 64, Mar. 2026.

[4] J. Blanco-Solano, D. J. Chacón Molina, and D. L. Chaustre Cárdenas, "Enhanced optimization-based PV hosting capacity method for improved planning of real distribution networks," *Electricity*, vol. 7, no. 1, Art. no. 12, Feb. 2026, doi: 10.3390/electricity7010012.

[5] U. Datta, A. Kalam, J. Shi, "Smart control of BESS in PV integrated EV charging station for reducing transformer overloading and providing battery-to-grid service," *Journal of Energy Storage*, vol. 28, Apr. 2020, doi: 10.1016/j.est.2020.101224.

[6] R. A. Jabr, "Radial distribution load flow using conic programming," *IEEE Trans. Power Syst.*, vol. 21, no. 3, pp. 1458--1459, Aug. 2006, doi: 10.1109/TPWRS.2006.879214.

[7] M. Farivar and S. H. Low, "Branch flow model: Relaxations and convexification," in *Proc. 51st IEEE Conf. Decision Control (CDC)*, Maui, HI, USA, Dec. 2012, pp. 3672--3679, doi: 10.1109/CDC.2012.6425823.

[8] N. Zheng, J. Jaworski, and B. Xu, "Arbitraging variable efficiency energy storage using analytical stochastic dynamic programming," *IEEE Trans. Power Syst.*, vol. 37, no. 6, pp. 4785--4795, Nov. 2022, doi: 10.1109/TPWRS.2022.3154353.

[9] M. Moradi-Sepahvand and T. Amraee, "Hybrid AC/DC transmission expansion planning considering HVAC to HVDC conversion under renewable penetration," *IEEE Trans. Power Syst.*, vol. 38, no. 5, pp. 4112--4123, Sep. 2023, doi: 10.1109/TPWRS.2022.3218579.

[10] X. Dong, C. Liu, J. Li, Q. Zhu, Y. Wang, J. Zhu, "Assessment of Distributed PV Hosting Capacity in Distribution Areas Based on Operating Region Analysis," *Algorithms*, vol 19, no. 4: 320. doi: 10.3390/a19040320.

[11] C. Bustos, E. Sauma, S. de la Torre, J. A. Aguado, J. Contreras, and D. Pozo, "Energy storage and transmission expansion planning: Substitutes or complements?," *IET Gener. Transm. Distrib.*, vol. 12, no. 8, pp. 1738--1746, Apr. 2018, doi: 10.1049/iet-gtd.2017.0759.

[12] M. E. Baran and F. F. Wu, "Network reconfiguration in distribution systems for loss reduction and load balancing," *IEEE Trans. Power Del.*, vol. 4, no. 2, pp. 1401--1407, Apr. 1989, doi: 10.1109/61.25627.
