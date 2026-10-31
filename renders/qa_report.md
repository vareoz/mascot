# Informe de control de calidad (automático)

Generado por `blender/qa_check.py` sobre las mallas deformadas (cada 2 fotogramas).

Columnas: altura mínima de la suela respecto al suelo; profundidad máxima de manos/dedos y del teléfono dentro del cuerpo; pares de triángulos que se cruzan **entre dedos distintos**; pares que se solapan dentro del pliegue interior de una articulación flexionada (piel comprimida, no visible); variación máxima de escala del cuerpo (respiración / squash).

| Animación | Suela mín. (mm) | Mano en cuerpo (mm) | Teléfono en cuerpo (mm) | Mano en teléfono (mm) | Choques entre dedos | Solapes en pliegues | Escala cuerpo |
|---|---|---|---|---|---|---|---|
| Idle | 0.2 | 0.0 | 0.0 | 0.0 | 0 | 0 | 1.6% |
| Wave | 0.2 | 0.0 | 0.0 | 0.0 | 0 | 21 | 1.0% |
| Celebrate | 0.2 | 0.0 | 0.0 | 0.0 | 78 | 182 | 8.0% |
| Walk | 0.5 | 0.0 | 0.0 | 0.0 | 0 | 0 | 1.2% |
| Phone | 0.2 | 0.0 | 0.0 | 0.0 | 0 | 187 | 1.0% |
| Fist | 0.2 | 0.0 | 0.0 | 0.0 | 21 | 17 | 0.8% |
| Present | 0.2 | 0.4 | 0.0 | 0.0 | 1 | 54 | 0.8% |

| Pose de mano | Choques entre dedos | Solapes en pliegues |
|---|---|---|
| fist | 21 | 67 |
| open | 0 | 50 |
| phone | 0 | 133 |
| point | 1 | 51 |
| relaxed | 0 | 50 |
| wave | 0 | 50 |
