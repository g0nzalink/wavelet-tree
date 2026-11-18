#!/usr/bin/env bash
# Instala SDSL-lite (solo la biblioteca) en un prefijo local, sin sudo.
#   bash scripts/install_sdsl.sh              -> instala en ~/.local
#   bash scripts/install_sdsl.sh /otra/ruta   -> instala en /otra/ruta
set -euo pipefail

PREFIX="${1:-$HOME/.local}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo ">> Clonando sdsl-lite en $WORK"
git clone --recursive --depth 1 https://github.com/simongog/sdsl-lite.git "$WORK/sdsl-lite"

echo ">> Configurando"
cmake -S "$WORK/sdsl-lite" -B "$WORK/build" \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
  -DCMAKE_INSTALL_PREFIX="$PREFIX" \
  -DCMAKE_CXX_FLAGS="-include cstdint -w -Wno-template-body" \
  -DCMAKE_C_FLAGS="-w"

echo ">> Compilando (solo las bibliotecas)"
if ! cmake --build "$WORK/build" --target sdsl divsufsort divsufsort64 -j"$(nproc)" >/dev/null 2>&1; then
  echo ">> Fallo la compilacion. Repitiendo en serie para mostrar el error real:"
  cmake --build "$WORK/build" --target sdsl divsufsort divsufsort64 -j1 2>&1 | grep -E -B3 -A12 "error" | head -80
  exit 1
fi

echo ">> Copiando a $PREFIX"
mkdir -p "$PREFIX/include" "$PREFIX/lib"
cp -r "$WORK/sdsl-lite/include/sdsl" "$PREFIX/include/"
cp "$WORK/build/external/libdivsufsort/include/"divsufsort*.h "$PREFIX/include/"
cp "$WORK/build/lib/libsdsl.a" "$PREFIX/lib/"
cp "$WORK/build/external/libdivsufsort/lib/"libdivsufsort*.a "$PREFIX/lib/"

echo ">> Listo. SDSL-lite instalado en $PREFIX"
echo "   Ahora: cmake -S . -B build -DSDSL_PREFIX=$PREFIX && cmake --build build -j"
