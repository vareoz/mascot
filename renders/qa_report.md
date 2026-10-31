# Informe de control de calidad (automático)

Generado por `blender/qa_check.py` sobre las mallas deformadas (cada 2 fotogramas).

Columnas: altura mínima de la suela respecto al suelo; profundidad máxima de manos/dedos y del teléfono dentro del cuerpo; pares de triángulos que se cruzan **entre dedos distintos**; pares que se solapan dentro del pliegue interior de una articulación flexionada (piel comprimida, no visible); variación máxima de escala del cuerpo (respiración / squash).

| Animación | Suela mín. (mm) | Mano en cuerpo (mm) | Teléfono en cuerpo (mm) | Mano en teléfono (mm) | Choques entre dedos | Solapes en pliegues | Escala cuerpo |
|---|---|---|---|---|---|---|---|
| Idle | 0.7 | 0.0 | 0.0 | 0.0 | 0 | 0 | 1.6% |
| Wave | 0.7 | 0.0 | 0.0 | 0.0 | 0 | 93 | 1.0% |
| Celebrate | 0.6 | 0.0 | 0.0 | 0.0 | 27 | 67 | 8.0% |
| Walk | 0.4 | 0.0 | 0.0 | 0.0 | 0 | 0 | 1.2% |
| Phone | 0.7 | 0.0 | 0.0 | 0.0 | 0 | 250 | 1.0% |
| Fist | 0.7 | 0.0 | 0.0 | 0.0 | 19 | 100 | 0.8% |
| Present | 0.7 | 0.0 | 0.0 | 0.0 | 0 | 116 | 0.8% |

| Pose de mano | Choques entre dedos | Solapes en pliegues |
|---|---|---|
| fist | 19 | 119 |
| open | 0 | 54 |
| phone | 0 | 135 |
| point | 0 | 114 |
| relaxed | 0 | 54 |
| wave | 0 | 54 |
