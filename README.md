# Benchmarks: Wavelet Tree propio vs SDSL-lite (`wt_blcd`)

Compara la implementación simple del proyecto (`src/wavelet_tree.hpp`: `bitvector` con `vector<int>`, nodos con punteros)
contra `sdsl::wt_blcd<>` de SDSL-lite (con `rank_support_v` y `select_support_mcl`, la configuración por defecto).
Solo Linux.

```
src/wavelet_tree.hpp      tu implementación (sin tocar)
src/bench.cpp             un proceso = una configuración; imprime una fila CSV
scripts/install_sdsl.sh   instala SDSL-lite en ~/.local (sin sudo)
scripts/run_benchmarks.py recorre la grilla de configuraciones -> results/results.csv
scripts/plot_results.py   results.csv -> gráficas + summary.csv
CMakeLists.txt
```

## 1. Preparar (Arch Linux)

```bash
sudo pacman -S --needed base-devel cmake git python perf
python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt

bash scripts/install_sdsl.sh                       # instala SDSL-lite en ~/.local
cmake -S . -B build && cmake --build build -j      # genera build/bench
```

> Si vienes de Windows: el repo incluye `.gitattributes` para que los `.sh` y `.py` lleguen con saltos de línea LF.
> Si aun así ves `^M: bad interpreter`, ejecuta `sed -i 's/\r$//' scripts/*.sh scripts/*.py`.
> Los scripts se invocan con `bash ...` / `python3 ...`, así que no necesitas permisos de ejecución.

Si SDSL no compila con tu GCC (es una biblioteca de 2017), el error suele ser un `#include` faltante;
`CMakeLists.txt` ya fuerza `-include cstdint`. Si persiste, pega el error y lo revisamos.

## 2. Comprobar que funciona

```bash
./build/bench --impl mine --op select --sigma 16 --n 1000000
./build/bench --impl sdsl --op select --sigma 16 --n 1000000
python3 scripts/run_benchmarks.py --quick
```

Cada ejecución **verifica la corrección** antes de medir (resultados exactos contra la respuesta conocida, y un checksum
en cada pasada). Si tu implementación devuelve algo incorrecto, el proceso falla con `ERROR de correccion` y
queda registrado en `results/errors.log`. Las dos implementaciones deben imprimir el mismo `checksum`.

## 3. Medir en serio

```bash
sudo cpupower frequency-set -g performance         # evita que la CPU cambie de frecuencia
python3 scripts/run_benchmarks.py --pin 2          # fija el proceso al núcleo 2
python3 scripts/plot_results.py
```

- Cierra navegador y demás programas; en laptop, enchufada.
- La grilla por defecto es: `n ∈ {1e5, 1e6, 1e7}`, `σ ∈ {4, 16, 64, 256}`, 3 patrones, 3 operaciones + construcción,
  2 implementaciones, 5 repeticiones. Puede tardar de decenas de minutos a un par de horas (el `select` propio es
  lento). Es **reanudable**: con Ctrl+C y volviendo a lanzar el mismo comando continúa donde quedó (`--force` repite todo).
- Opciones útiles: `--sizes`, `--sigmas`, `--ops`, `--patterns`, `--dists uniform zipf`, `--queries`, `--reps`.
- Datos reales (Pizza & Chili): `--files data/dna:20000000 data/proteins:20000000` (ruta:bytes de prefijo).
  Usa un **prefijo** (10–50 MB): la implementación propia usa ~4 bytes por bit de cada nivel
  (n=1e7 con σ=256 ya son ~320 MB). Ambas implementaciones miden el mismo prefijo.
- `results/environment.txt` guarda CPU, caché, RAM, kernel, compilador y gobernador: inclúyelo en el informe.

## 4. Qué mide cada columna

| Columna | Significado |
|---|---|
| `ns_median/min/max` | nanosegundos por consulta (mediana, mínimo y máximo de las repeticiones) |
| `build_s*` | tiempo de construcción en segundos (en la op `build`: mediana/mín/máx de las repeticiones) |
| `struct_bytes`, `bpc` | tamaño de la estructura (`bytes()` propio vs `size_in_bytes` de SDSL) y bits por carácter |
| `peak_rss_kb`, `rss_delta_kb` | pico de RSS y pico sobre el texto cargado. **Solo es interpretable en filas `build`** (en las de consulta incluye los arreglos de consultas) |
| `cycles_q`, `instr_q`, `l1d_miss_q`, `ll_miss_q` | contadores de hardware **por consulta**, solo del bucle medido y en espacio de usuario. `-1` si no hay acceso |
| `checksum` | suma de los resultados; debe coincidir entre implementaciones |

Patrones de consulta: `uniform` (posiciones al azar), `sequential` (posiciones consecutivas, buena localidad) y
`hotspot` (80 % de las consultas en el 1 % de las posiciones).
`select(c, j)` y `rank(c, i)` usan el símbolo del texto en una posición aleatoria, así siempre hay respuesta válida.

## 5. Contadores de caché (perf)

Se leen dentro de `bench` con `perf_event_open`, por lo que no hace falta `perf stat` y se mide solo el bucle de consultas.
En Arch el valor por defecto de `kernel.perf_event_paranoid` (2) alcanza para medir espacio de usuario.
En WSL o máquinas virtuales los contadores normalmente no existen y verás `-1` (se omite esa gráfica).
Alternativa sin contadores: `valgrind --tool=cachegrind ./build/bench --impl mine --op rank --n 100000 --queries 100000 --reps 1`.

## 6. Cosas a tener en cuenta al interpretar

- `select` propio incluye lo que hace tu código: dos `vector` por llamada y una llamada a `rank` para validar `j`.
  Es parte de la implementación «simple»; decláralo en el informe.
- SDSL usa el orden `rank(i, c)` y `select(j, c)`; los wrappers de `bench.cpp` ya lo adaptan.
- Compilado con `-O3 -march=native`: el binario solo es válido en la CPU donde se compiló. Mide todo en la misma máquina.
- La memoria de SDSL en construcción incluye una copia temporal del texto (`construct_im`).
