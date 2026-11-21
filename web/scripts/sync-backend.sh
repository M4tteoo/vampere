#!/bin/sh
# Copia gli output della pipeline (python -m pipeline.run → output/) nel frontend (web/public/data/real/).
# Uso: sh web/scripts/sync-backend.sh   (da qualsiasi cartella)
set -e
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
mkdir -p "$ROOT/web/public/data/real"
cp "$ROOT"/output/*.json "$ROOT/web/public/data/real/"
echo "Copied $(ls "$ROOT"/output/*.json | wc -l | tr -d ' ') files to web/public/data/real/"
# File di consegna (CSV) per il pulsante «Export».
mkdir -p "$ROOT/web/public/data/real/submission"
cp "$ROOT"/output/submission/*.csv "$ROOT/web/public/data/real/submission/"
