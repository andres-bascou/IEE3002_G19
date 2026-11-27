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
    local rc=${PIPESTATUS[0]}
    echo "=== $(date '+%F %T') fin ($*): código $rc" | tee -a "$LOG"
    return "$rc"
}
correr experimentos/pregunta1_bess.py || { echo "=== P1 falló: se detiene (los demás dependen de él)" | tee -a "$LOG"; exit 1; }   # P1: cotas horarias + enumeración, barridos A y B; reanudable
correr experimentos/pregunta3_sensibilidad_entrega_final.py --parte bess   # P3: eficiencia, SoC y fp con BESS
correr experimentos/pregunta4_relajacion_entrega_final.py        # P4: exacto vs relajado en 24 h
correr experimentos/pregunta1_verificacion.py      # P1: ¿mover el PV mejora el HC? (15 min por configuración)
echo "=== $(date '+%F %T') listo" | tee -a "$LOG"
