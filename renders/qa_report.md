# Informe de control de calidad (automático)

Generado por `blender/qa_check.py` sobre las mallas deformadas (cada 2 fotogramas).

Columnas: altura mínima de la suela respecto al suelo; profundidad máxima de manos/dedos y del teléfono dentro del cuerpo; pares de triángulos que se cruzan **entre dedos distintos**; pares que se solapan dentro del pliegue interior de una articulación flexionada (piel comprimida, no visible); variación máxima de escala del cuerpo (respiración / squash).

| Animación | Suela mín. (mm) | Mano en cuerpo (mm) | Teléfono en cuerpo (mm) | Choques entre dedos | Solapes en pliegues | Escala cuerpo |
|---|---|---|---|---|---|---|
| Idle | 2.2 | 0.0 | 0.0 | 0 | 0 | 1.6% |
| Wave | 2.2 | 0.0 | 0.0 | 0 | 43 | 1.0% |
| Celebrate | 2.2 | 0.0 | 0.0 | 26 | 303 | 8.0% |
| Walk | 0.5 | 0.0 | 0.0 | 0 | 0 | 1.2% |
| Phone | 2.2 | 0.0 | 0.0 | 0 | 164 | 1.0% |
| Fist | 2.2 | 0.0 | 0.0 | 31 | 391 | 0.8% |
| Present | 2.2 | 0.0 | 0.0 | 0 | 317 | 0.8% |

| Pose de mano | Choques entre dedos | Solapes en pliegues |
|---|---|---|
| fist | 16 | 252 |
| open | 0 | 0 |
| phone | 0 | 43 |
| point | 0 | 277 |
| relaxed | 0 | 0 |
| wave | 0 | 0 |
