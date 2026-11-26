#!/usr/bin/env bash
# experimentos/correr_experimentos.sh
# Corre (o reanuda) todos los experimentos de la entrega final, en orden. Cada script guarda su
# avance en results/ y salta lo que ya está resuelto, así que se puede cortar y volver a lanzar.
# OJO: NO usar rutas absolutas: todo se resuelve relativo a la raíz del proyecto.
#
# Uso (desde cualquier carpeta; caffeinate evita que el Mac se duerma con la tapa abierta):
#     caffeinate -dims bash experimentos/correr_experimentos.sh
# El registro queda en results/logs/experimentos_<fecha>.txt.
set -u
cd "$(dirname "$0")/.." || exit 1
PY=.venv/bin/python
mkdir -p results/logs
LOG="results/logs/experimentos_$(date +%Y%m%d_%H%M%S).txt"
correr() {
    echo "=== $(date '+%F %T') $*" | tee -a "$LOG"
    "$PY" -u "$@" 2>&1 | grep --line-buffered -v -E "^(Set parameter|Academic license)" | tee -a "$LOG"
    echo "=== $(date '+%F %T') fin ($*): código ${PIPESTATUS[0]}" | tee -a "$LOG"
}
correr experimentos/pregunta1_bess.py              # P1: barridos A (con/sin límite) y B (tau = 4 h); reanudable
correr experimentos/pregunta1_verificacion.py      # P1: ¿mover el PV mejora el HC? (15 min por configuración)
correr experimentos/pregunta3_sensibilidad.py --parte bess   # P3: eficiencia, SoC y fp con BESS
correr experimentos/pregunta4_relajacion.py        # P4: exacto vs relajado en 24 h
echo "=== $(date '+%F %T') listo" | tee -a "$LOG"
