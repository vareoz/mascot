#!/usr/bin/env bash
# Full pipeline: build -> numerical QA -> QA renders -> contact sheets -> web copy.
# Usage: tools/build_all.sh [path/to/blender]
set -euo pipefail
cd "$(dirname "$0")/.."
BLENDER="${1:-${BLENDER:-blender}}"
"$BLENDER" -b --factory-startup -P blender/build_mascot.py
"$BLENDER" -b export/mascot.blend -P blender/qa_check.py
for mode in turnaround hands anims hero; do
  "$BLENDER" -b export/mascot.blend -P blender/render_qa.py -- "$mode"
done
python3 tools/make_sheets.py
cp export/mascot.glb web/mascot.glb
echo "done"
