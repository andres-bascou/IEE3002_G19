# Incorporación de BESS en Modelos de Hosting Capacity (IEEE 33-bus)

Proyecto del curso IEE3002 Optimización Avanzada para Ingeniería Eléctrica (PUC), grupo G19.

El objetivo es maximizar la capacidad de alojamiento (*Hosting Capacity*, HC) de generación fotovoltaica en una red de distribución radial, permitiendo instalar baterías (BESS). Se usa un modelo MISOCP multiperíodo (24 h) basado en la relajación cónica del *Branch Flow Model* [6], [7], resuelto con Gurobi sobre la red IEEE 33-bus [12], y se toma como paper base a Blanco-Solano et al. [4].

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
| **Etapa 3:** modelo multiperíodo con BESS y comparación | ⬜ Pendiente |

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
├── experimentos/                Experimentos de las preguntas de investigación (preguntas 1 y 2)
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
| Pregunta 1: HC con BESS (24 h, cotas) | `.venv/bin/python experimentos/pregunta1_bess_cotas.py [--tamanos 0.05,0.5,1]` (~45 min por tamaño) | `results/pregunta1_bess_cotas.json` |
| Pregunta 2: concentrado vs distribuido | `.venv/bin/python experimentos/pregunta2_concentrado_distribuido.py` (~3 min) | `results/pregunta2_concentrado_distribuido.json` y `results/figures/pregunta2/` |
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
- [4] reporta para el escenario 1 una exportación de 4600 kW, I_max = 259 A y V_max = 1.0934 p.u. Aquí la exportación y la corriente coinciden, pero V_max llega a 1.10 p.u. Queda por revisar en el PDF de [4] si su V_max se mide en otro punto o con otra ubicación del PV (ellos asignan 12 kW a la barra 9).

### Pregunta 1: HC con BESS (24 h, 2 × 50 kW / 100 kWh) 🟡 (falta el barrido de tamaños)

El modelo exacto de 24 h con BESS no cierra el gap en 10–20 min: tiene 1600 binarias y 768 igualdades no convexas. Por eso `experimentos/pregunta1_bess_cotas.py` no lo resuelve completo, sino que **acota su HC óptimo por los dos lados**:

| Cota | Cómo se obtiene | Por qué es válida |
|---|---|---|
| **Inferior** | El modelo exacto, con sus binarias originales, con el PV solo en las barras del caso sin BESS (18 y 22) y el BESS solo en un par de barras candidatas. Se prueban 4 pares. | Cada solución es factible para el problema completo |
| **Superior** | El problema completo con las binarias de carga y descarga (μ) relajadas a [0, 1] | Es una relajación del original |

Caso: julio, exportación ≤ 4.6 MW, sin topes de PV activos.

| | HC | Frente a sin BESS (12 643 kW) |
|---|---|---|
| Sin BESS (óptimo, ~2 min) | 12 643 kW, PV en 18 y 22 | — |
| Cota inferior: BESS en 32 y 33 (óptimo con sitios fijos) | **12 818 kW** | +176 kW (+1.39 %) |
| Cota superior (20 min) | **12 868 kW** | +226 kW (+1.78 %) |

- **El HC óptimo con 2 × 50 kW de BESS está entre 12 818 y 12 868 kW**, un rango de solo 0.4 %. Las baterías aumentan el HC entre 1.4 y 1.8 %.
- La mejor solución se verificó con un flujo AC de pandapower en las 24 horas. Cumple todos los límites (exportación 4600 kW, V ≤ 1.10, I ≤ 259 A) y coincide con el modelo a 3e-10 p.u.
- **Las baterías rinden más lejos del PV**: con BESS en 32 y 33 el HC es 12 818 kW; con BESS en 17–18, 21–22 o 18–22, cerca de 12 783 kW. Es el mismo efecto de la pregunta 2: con el límite de exportación activo, más pérdidas permiten más PV.
- **Por qué no se quitan las binarias μ.** Sin ellas, las baterías cargan y descargan a la vez a mediodía (36 casos en la cota superior). Con η = 0.95, eso disipa ~10 % de su potencia, como una carga ficticia que permite instalar más PV. Con 2 × 50 kW el efecto es chico, pero con baterías de MW inflaría el HC. Por eso esa versión sirve solo como cota.
- **Qué no funcionó:** partir desde la solución sin BESS, `MIPFocus=3`, cotas explícitas en los flujos, y reformular con una binaria por hora solo en las horas de sol (416 binarias). Con esta última el gap quedó en 6.5 % a los 20 min. Los scripts y resultados de estas pruebas están en `verificacion/preliminar_24h_bess/` (PRELIMINAR).

### Pregunta 2: PV concentrado vs distribuido 🟡 (carga base; falta 24 h)

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
- [ ] **Pendiente:** ¿el límite de exportación de 4.6 MW se usa también en el modelo de 24 h? Por ahora solo lo impone `config_tabla1` (`p_s_ref_pu` sigue en `None` por defecto).

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
- [x] Modelo multiperíodo (24 h) con BESS, y comparar el HC con y sin baterías (pregunta 1) para 2 × 50 kW: HC entre 12 818 y 12 868 kW (+1.4 a +1.8 %), ver resultados arriba.
- [ ] Barrido de tamaños de BESS con `experimentos/pregunta1_bess_cotas.py --tamanos ...` (~45 min por tamaño). Con baterías más grandes la ubicación del PV podría cambiar: conviene agregar a `--pares` los sitios que elija la cota superior. Falta que el grupo decida el rango de tamaños.
- [x] Generación concentrada vs distribuida (pregunta 2), en carga base: ver resultados arriba.
- [ ] Pregunta 2 en el modelo de 24 h (sin BESS, ~2 min por corrida).
- [ ] Análisis de sensibilidad de los parámetros (pregunta 3): eficiencias, DoD, τ, c_deg, tamaño de BESS, límites de exportación.
- [ ] Cuantificar el error de la relajación frente al MIQCP (pregunta 4); los resultados preliminares de arriba ya lo adelantan.
- [ ] Gráficos de despacho, perfiles de tensión y ciclado de baterías.

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
