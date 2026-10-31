# Informe de control de calidad (automático)

Generado por `blender/qa_check.py` sobre las mallas deformadas (cada 2 fotogramas).

Columnas: altura mínima de la suela respecto al suelo; profundidad máxima de manos/dedos y del teléfono dentro del cuerpo; pares de triángulos que se cruzan **entre dedos distintos**; pares que se solapan dentro del pliegue interior de una articulación flexionada (piel comprimida, no visible); variación máxima de escala del cuerpo (respiración / squash).

| Animación | Suela mín. (mm) | Mano en cuerpo (mm) | Teléfono en cuerpo (mm) | Mano en teléfono (mm) | Choques entre dedos | Solapes en pliegues | Escala cuerpo |
|---|---|---|---|---|---|---|---|
| Idle | 0.7 | 0.0 | 0.0 | 0.0 | 6 | 13 | 1.6% |
| Wave | 0.7 | 5.4 | 0.0 | 0.0 | 6 | 76 | 1.0% |
| Celebrate | 0.6 | 0.0 | 0.0 | 0.0 | 66 | 229 | 8.0% |
| Walk | 0.4 | 4.0 | 0.0 | 0.0 | 6 | 13 | 1.2% |
| Phone | 0.7 | 46.8 | 0.0 | 0.0 | 3 | 177 | 1.0% |
| Fist | 0.7 | 0.0 | 0.0 | 0.0 | 34 | 99 | 0.8% |
| Present | 0.7 | 5.5 | 0.0 | 0.0 | 6 | 121 | 0.8% |

| Pose de mano | Choques entre dedos | Solapes en pliegues |
|---|---|---|
| fist | 34 | 108 |
| open | 0 | 66 |
| phone | 0 | 142 |
| point | 0 | 121 |
| relaxed | 6 | 74 |
| wave | 0 | 66 |
