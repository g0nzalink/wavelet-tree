cmake_minimum_required(VERSION 3.10)
project(wavelet_bench CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()

# Donde instalo SDSL-lite scripts/install_sdsl.sh (cambiar con -DSDSL_PREFIX=/otra/ruta)
set(SDSL_PREFIX "$ENV{HOME}/.local" CACHE PATH "Prefijo donde esta instalado SDSL-lite")

find_path(SDSL_INCLUDE sdsl/wavelet_trees.hpp HINTS ${SDSL_PREFIX}/include)
find_library(SDSL_LIB sdsl HINTS ${SDSL_PREFIX}/lib)
find_library(DIVSUFSORT_LIB divsufsort HINTS ${SDSL_PREFIX}/lib)
find_library(DIVSUFSORT64_LIB divsufsort64 HINTS ${SDSL_PREFIX}/lib)
if(NOT SDSL_INCLUDE OR NOT SDSL_LIB OR NOT DIVSUFSORT_LIB OR NOT DIVSUFSORT64_LIB)
  message(FATAL_ERROR "No encuentro SDSL-lite en ${SDSL_PREFIX}. Ejecuta: bash scripts/install_sdsl.sh")
endif()

add_executable(bench src/bench.cpp)
target_include_directories(bench PRIVATE src ${SDSL_INCLUDE})
target_link_libraries(bench PRIVATE ${SDSL_LIB} ${DIVSUFSORT_LIB} ${DIVSUFSORT64_LIB})

# -march=native: el binario solo corre en la CPU donde se compilo (normal para benchmarks).
# -include cstdint: SDSL-lite es antiguo y con GCC recientes a veces le falta ese include.
target_compile_options(bench PRIVATE
  -O3 -march=native -DNDEBUG -g -fno-omit-frame-pointer
  -Wno-deprecated-declarations "SHELL:-include cstdint")
