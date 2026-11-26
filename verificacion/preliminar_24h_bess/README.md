# PRELIMINAR: pruebas del modelo de 24 h con BESS

Pruebas exploratorias que llevaron al método de cotas de la pregunta 1 (`experimentos/pregunta1_bess_cotas.py`). **No son resultados oficiales**: se guardan para documentar qué se probó y por qué se descartó.

Configuración común: julio, modelo exacto (MIQCP, `NonConvex=2`), objetivo max ΣP_PV, PV hasta 20 MW en cualquier barra (tope no activo), BESS de 2 × 50 kW / 100 kWh. Salvo el caso A, exportación ≤ 4.6 MW.

Cada script agrega una línea a `results/preliminar_24h_bess/<script>.jsonl`. Los `.jsonl` versionados son las corridas originales (noviembre 2026, Gurobi 10.0.3, MacBook).

```bash
.venv/bin/python verificacion/preliminar_24h_bess/medir_24h.py                 # ~17 min
.venv/bin/python verificacion/preliminar_24h_bess/acelerar.py C_cand            # 10 min por variante
.venv/bin/python verificacion/preliminar_24h_bess/sin_mu.py                     # 20 min
.venv/bin/python verificacion/preliminar_24h_bess/una_binaria.py                # 20 min
.venv/bin/python verificacion/preliminar_24h_bess/fijar_sitios.py 32,33 21,22   # hasta 10 min por par
.venv/bin/python verificacion/preliminar_24h_bess/ventana.py 1 13-15             # 5 min por ventana
```

## 0. `medir_24h.py`: cuánto tarda el modelo de 24 h

| Caso | Relajado (MISOCP) | Exacto (MIQCP) |
|---|---|---|
| A: sin BESS, sin límite de exportación | 16 334 kW en 0.2 s | 14 381 kW, gap 3.2 % a los 300 s |
| B: sin BESS, exportación ≤ 4.6 MW | 16 334 kW en 0.1 s | **12 643 kW, óptimo en 122 s** (PV en 18 y 22) |
| C: con BESS, exportación ≤ 4.6 MW | 16 473 kW en 0.6 s | 12 670 kW, gap 5.3 % a los 600 s |

- **El relajado no sirve**: tiene ~44 MWh/día de pérdidas ficticias (brecha cónica relativa ≈ 1). Infla el HC en 29 %, igual que en la Tabla 1 de [4].
- **Sin BESS, el exacto se resuelve en 2 min. Con BESS no cierra**: pasa de 32 a 1600 binarias (μ_ch, μ_dis por batería y hora).

## 1. `acelerar.py`: variantes para que cierre el caso C

| Variante | Resultado (600 s) |
|---|---|
| `B_cotas`: caso B con cotas explícitas en flujos y P_S, Q_S | Óptimo en 207 s, más lento que sin cotas (122 s) |
| `C_start`: arranque en la solución sin BESS | Gap 7.0 % |
| `C_start_focus`: + `MIPFocus=3` | Sin solución factible |
| `C_cand`: BESS candidata solo en 18 y 22 | Gap 4.5 % |
| `C_cand_start`: + arranque | Gap 5.7 % |

Ninguna variante sirvió.

## 2. `sin_mu.py`: μ_ch, μ_dis relajadas a [0, 1]

- HC 12 817 kW, cota 12 866 kW, gap 0.38 % a los 20 min. Esta relajación sí da una **cota superior** útil.
- Pero la solución carga y descarga a la vez en 7 batería-horas y disipa 42 kWh/día. Con η = 0.95, eso es ~10 % de la potencia: una carga ficticia que permite más PV. **No es una solución real.**

## 3. `una_binaria.py`: una binaria por batería y hora, solo con sol

- 416 binarias en vez de 1600.
- Gap 6.5 % a los 20 min, con un HC de 12 629 kW, **peor que sin BESS**.
- De noche, sin binarias, la BESS carga y descarga a la vez en 21 batería-horas.
- Peor que el original.

## 4. `fijar_sitios.py`: PV en 18 y 22, BESS en un par fijo (cota inferior)

| BESS en | HC | Estado |
|---|---|---|
| 32, 33 | **12 818 kW** | Óptimo, 593 s |
| 21, 22 | 12 785 kW | Óptimo, 21 s |
| 17, 18 | 12 783 kW | Óptimo, 26 s |
| 18, 22 | 12 781 kW | Gap 2e-5 a los 610 s |

- Cada solución es factible para el problema completo, así que es una **cota inferior**.
- Ninguna carga y descarga a la vez.

## 5. `ventana.py`: cota superior con energía, en una ventana de horas

- Solo se modelan las horas de la ventana, con el estado de carga inicial libre y sin estado final. Es una relajación válida que, a diferencia de la cota horaria, sí considera la energía de la BESS.
- Con las binarias μ el solver no cierra en 5–20 min. La cota quedó peor que la horaria: por ejemplo, 18 056 kW con 1 MW y la ventana 13–15, frente a 16 136 kW de la horaria. Se descartó.

## Conclusión

Junto con la cota superior de la prueba 2, el HC con 2 × 50 kW queda acotado en **[12 818, 12 866] kW**. `experimentos/pregunta1_bess_cotas.py` formaliza la cota inferior: calcula los sitios de PV, acepta varios tamaños de BESS y verifica con un flujo AC. Además, reemplaza la cota de la prueba 2 por una cota horaria, que con 50 kW coincide con la inferior (12 818 kW, óptimo).
