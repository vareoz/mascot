# Informe de control de calidad (automático)

Generado por `blender/qa_check.py` sobre las mallas deformadas (cada 2 fotogramas).

Columnas: altura mínima de la suela respecto al suelo; profundidad máxima de manos/dedos y del teléfono dentro del cuerpo; pares de triángulos que se cruzan **entre dedos distintos**; pares que se solapan dentro del pliegue interior de una articulación flexionada (piel comprimida, no visible); variación máxima de escala del cuerpo (respiración / squash).

| Animación | Suela mín. (mm) | Mano en cuerpo (mm) | Teléfono en cuerpo (mm) | Mano en teléfono (mm) | Choques entre dedos | Solapes en pliegues | Escala cuerpo |
|---|---|---|---|---|---|---|---|
| Idle | 0.7 | 0.0 | 0.0 | 0.0 | 0 | 8 | 1.6% |
| Wave | 0.7 | 0.0 | 0.0 | 0.0 | 0 | 97 | 1.0% |
| Celebrate | 0.6 | 0.0 | 0.0 | 0.0 | 56 | 244 | 8.0% |
| Walk | 0.4 | 0.0 | 0.0 | 0.0 | 0 | 8 | 1.2% |
| Phone | 0.7 | 0.0 | 0.0 | 0.2 | 0 | 211 | 1.0% |
| Fist | 0.7 | 0.0 | 0.0 | 0.0 | 20 | 85 | 0.8% |
| Present | 0.7 | 0.0 | 0.0 | 0.0 | 0 | 123 | 0.8% |

| Pose de mano | Choques entre dedos | Solapes en pliegues |
|---|---|---|
| fist | 20 | 100 |
| open | 0 | 79 |
| phone | 0 | 162 |
| point | 0 | 123 |
| relaxed | 0 | 80 |
| wave | 0 | 79 |
