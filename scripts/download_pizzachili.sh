#!/usr/bin/env bash
# Descarga prefijos del corpus Pizza&Chili a data/pizzachili/ (esa carpeta esta en .gitignore).
#   bash scripts/download_pizzachili.sh                 -> dna proteins english sources dblp.xml (50 MB c/u)
#   bash scripts/download_pizzachili.sh dna proteins    -> solo esos
#   SIZE=100 bash scripts/download_pizzachili.sh dna    -> prefijo de 100 MB (existen 50, 100 y 200)
#
# El corpus publica <archivo>.<X>MB.gz en https://pizzachili.dcc.uchile.cl/texts/<carpeta>/
# Si un archivo da 404, revisa la carpeta en el navegador: https://pizzachili.dcc.uchile.cl/texts.html
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

OUT="data/pizzachili"
SIZE="${SIZE:-50}"
MIRRORS="${PIZZA_MIRRORS:-https://pizzachili.dcc.uchile.cl http://pizzachili.di.unipi.it}"

# archivo local -> carpeta en el servidor
declare -A DIR=([dna]=dna [proteins]=protein [english]=nlang [sources]=code [dblp.xml]=xml)

if [ "$#" -gt 0 ]; then NAMES=("$@"); else NAMES=(dna proteins english sources dblp.xml); fi
mkdir -p "$OUT"

for name in "${NAMES[@]}"; do
  dir="${DIR[$name]:-}"
  if [ -z "$dir" ]; then
    echo "Corpus desconocido: $name (opciones: ${!DIR[*]})" >&2
    exit 1
  fi
  if [ -s "$OUT/$name" ]; then
    echo ">> $name ya existe, se omite"
    continue
  fi
  ok=0
  for m in $MIRRORS; do
    url="$m/texts/$dir/$name.${SIZE}MB.gz"
    echo ">> $url"
    if curl -fL --retry 3 --connect-timeout 20 -o "$OUT/$name.gz" "$url"; then ok=1; break; fi
  done
  if [ "$ok" != 1 ]; then
    echo "No se pudo descargar $name. Revisa la carpeta en https://pizzachili.dcc.uchile.cl/texts/$dir/" >&2
    rm -f "$OUT/$name.gz"
    exit 1
  fi
  gunzip -f "$OUT/$name.gz"
done

echo ">> Listo:"
ls -l "$OUT"
