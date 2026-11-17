#!/usr/bin/env bash
# Instala SDSL-lite (solo la biblioteca) en un prefijo local, sin sudo.
#   bash scripts/install_sdsl.sh              -> instala en ~/.local
#   bash scripts/install_sdsl.sh /otra/ruta   -> instala en /otra/ruta
#
# Requisitos (Arch): sudo pacman -S --needed base-devel cmake git
#
# Por que no se usa el install.sh del repo de SDSL: es de 2017, pide CMake 2.8 (CMake >= 4
# lo rechaza) y ademas compila y instala los tests de googletest, que fallan al instalar.
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
  -DCMAKE_INSTALL_PREFIX="$PREFIX"

echo ">> Compilando (solo las bibliotecas)"
cmake --build "$WORK/build" --target sdsl divsufsort divsufsort64 -j"$(nproc)"

echo ">> Copiando a $PREFIX"
mkdir -p "$PREFIX/include" "$PREFIX/lib"
cp -r "$WORK/sdsl-lite/include/sdsl" "$PREFIX/include/"
cp "$WORK/build/external/libdivsufsort/include/"divsufsort*.h "$PREFIX/include/"
cp "$WORK/build/lib/libsdsl.a" "$PREFIX/lib/"
cp "$WORK/build/external/libdivsufsort/lib/"libdivsufsort*.a "$PREFIX/lib/"

echo ">> Listo. SDSL-lite instalado en $PREFIX"
echo "   Ahora: cmake -S . -B build -DSDSL_PREFIX=$PREFIX && cmake --build build -j"
