#!/usr/bin/env python3
"""Ejecuta el binario `bench` sobre una grilla de configuraciones y junta todo en un CSV.

Un proceso por configuracion (asi el pico de memoria de cada una es independiente).
Es reanudable: si el CSV ya existe, salta las configuraciones ya medidas.

Ejemplos:
  python3 scripts/run_benchmarks.py --quick                      # prueba rapida
  python3 scripts/run_benchmarks.py --pin 2                      # grilla completa fijada al nucleo 2
  python3 scripts/run_benchmarks.py --files data/dna:20000000 --sizes 1000000
"""
import argparse
import csv
import hashlib
import itertools
import os
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUERY_OPS = ("access", "rank", "select")
# Archivos del corpus Pizza&Chili que baja scripts/download_pizzachili.sh (en data/pizzachili/)
PIZZA = ["dna", "proteins", "english", "sources", "dblp.xml"]


def sh(cmd):
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=20).stdout.strip()
    except Exception as e:  # noqa: BLE001
        return f"(no disponible: {e})"


def write_environment(path):
    """Guarda los datos del equipo: sin esto los resultados no se pueden interpretar."""
    parts = {
        "fecha": time.strftime("%Y-%m-%d %H:%M:%S"),
        "uname": sh("uname -a"),
        "lscpu": sh("lscpu"),
        "memoria": sh("free -h"),
        "compilador": sh("g++ --version | head -1"),
        "cmake": sh("cmake --version | head -1"),
        "perf_event_paranoid": sh("cat /proc/sys/kernel/perf_event_paranoid"),
        "gobernador_cpu": sh("cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null"),
        "turbo_intel_no_turbo": sh("cat /sys/devices/system/cpu/intel_pstate/no_turbo 2>/dev/null"),
        "commit": sh(f"git -C '{ROOT}' rev-parse --short HEAD 2>/dev/null"),
    }
    with open(path, "w") as f:
        for k, v in parts.items():
            f.write(f"== {k} ==\n{v}\n\n")
    gov = parts["gobernador_cpu"]
    if gov and gov != "performance":
        print(f"[aviso] gobernador de CPU = '{gov}'. Para medir mejor: "
              "sudo cpupower frequency-set -g performance", file=sys.stderr)
    try:
        if int(parts["perf_event_paranoid"]) >= 3:
            print("[aviso] perf_event_paranoid >= 3: no habra contadores de cache. "
                  "Prueba: sudo sysctl kernel.perf_event_paranoid=2", file=sys.stderr)
    except ValueError:
        pass
    print("[info] datos del equipo guardados en", path)


def describe_datasets(specs, path):
    """Guarda en results/datasets.txt que archivos reales (y cuantos bytes) se midieron + su sha256."""
    with open(path, "w") as f:
        f.write("archivo\tbytes_usados\tsha256_del_prefijo\n")
        for spec in specs:
            p, _, pre = spec.partition(":")
            if not os.path.exists(p):
                sys.exit(f"No existe el archivo {p}. Para Pizza&Chili: bash scripts/download_pizzachili.sh")
            size = os.path.getsize(p)
            use = min(int(pre), size) if pre else size
            h, left = hashlib.sha256(), use
            with open(p, "rb") as fh:
                while left > 0:
                    chunk = fh.read(min(1 << 20, left))
                    if not chunk:
                        break
                    h.update(chunk)
                    left -= len(chunk)
            f.write(f"{os.path.basename(p)}\t{use}\t{h.hexdigest()}\n")
    print("[info] datasets reales registrados en", path)


def make_key(impl, op, pattern, source, dist, n, sigma):
    return "|".join(map(str, (impl, op, pattern, source, dist, n, sigma)))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bench", default=os.path.join(ROOT, "build", "bench"))
    ap.add_argument("--out", default=os.path.join(ROOT, "results", "results.csv"))
    ap.add_argument("--impls", nargs="+", default=["mine", "sdsl"])
    ap.add_argument("--ops", nargs="+", default=["build", *QUERY_OPS])
    ap.add_argument("--sigmas", nargs="+", type=int, default=[4, 16, 64, 256])
    ap.add_argument("--sizes", nargs="+", type=int, default=[100_000, 1_000_000, 10_000_000])
    ap.add_argument("--patterns", nargs="+", default=["uniform", "sequential", "hotspot"])
    ap.add_argument("--dists", nargs="+", default=["uniform"], help="distribucion de simbolos: uniform y/o zipf")
    ap.add_argument("--queries", type=int, default=1_000_000)
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--files", nargs="*", default=[],
                    help="archivos reales, formato ruta[:bytes_de_prefijo] (ej. data/dna:20000000)")
    ap.add_argument("--pizza", action="store_true",
                    help="medir SOLO los archivos de data/pizzachili/ (omite los sinteticos)")
    ap.add_argument("--pizza-dir", default=os.path.join(ROOT, "data", "pizzachili"))
    ap.add_argument("--prefix-mb", type=float, default=20,
                    help="MB de cada archivo real que se usan con --pizza (default 20)")
    ap.add_argument("--pin", type=int, default=None, help="fijar el proceso a este nucleo (taskset)")
    ap.add_argument("--timeout", type=int, default=3600, help="segundos maximos por configuracion")
    ap.add_argument("--quick", action="store_true", help="grilla pequena para probar que todo funciona")
    ap.add_argument("--force", action="store_true", help="ignorar resultados previos y repetir todo")
    args = ap.parse_args()

    if args.quick:
        args.sizes, args.queries, args.reps = [100_000, 1_000_000], 200_000, 3

    synthetic = True
    if args.pizza:
        synthetic = False
        found = [os.path.join(args.pizza_dir, f) for f in PIZZA if os.path.exists(os.path.join(args.pizza_dir, f))]
        if not found:
            sys.exit(f"No hay archivos en {args.pizza_dir}. Ejecuta: bash scripts/download_pizzachili.sh")
        pre = int(args.prefix_mb * 1_000_000)
        args.files += [f"{p}:{pre}" for p in found]

    if not os.path.exists(args.bench):
        sys.exit(f"No existe {args.bench}. Compila primero: cmake -S . -B build && cmake --build build -j")
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    write_environment(os.path.join(os.path.dirname(args.out), "environment.txt"))

    header = subprocess.run([args.bench, "--header"], capture_output=True, text=True, check=True).stdout.strip()
    columns = header.split(",") + ["key"]

    done = set()
    if os.path.exists(args.out) and not args.force:
        with open(args.out, newline="") as f:
            done = {row["key"] for row in csv.DictReader(f)}
    elif os.path.exists(args.out):
        os.remove(args.out)
    new_file = not os.path.exists(args.out)

    # ---- armar la lista de configuraciones
    jobs = []  # (key, argv_extra)
    datasets = []
    if synthetic:
        datasets = [("synthetic", dist, n, sigma) for dist in args.dists for n in args.sizes for sigma in args.sigmas]
    for spec in args.files:
        path, _, pre = spec.partition(":")
        datasets.append((path, "-", int(pre) if pre else 0, 0))
    for (src, dist, n, sigma), impl, op in itertools.product(datasets, args.impls, args.ops):
        patterns = ["-"] if op == "build" else args.patterns
        for pat in patterns:
            extra = ["--impl", impl, "--op", op, "--queries", str(args.queries), "--reps", str(args.reps),
                     "--seed", str(args.seed)]
            if pat != "-":
                extra += ["--pattern", pat]
            if src == "synthetic":
                extra += ["--n", str(n), "--sigma", str(sigma), "--dist", dist]
                source = "synthetic"
            else:
                extra += ["--file", src] + (["--prefix", str(n)] if n else [])
                source = os.path.basename(src)
            # n y sigma reales de archivos se conocen al medir; la clave usa el prefijo pedido
            key = make_key(impl, op, pat, source, dist, n, sigma)
            if key not in done:
                jobs.append((key, extra))

    if args.files:
        describe_datasets(args.files, os.path.join(os.path.dirname(args.out), "datasets.txt"))
    print(f"[info] {len(jobs)} configuraciones por ejecutar ({len(done)} ya hechas)")
    prefix = []
    if args.pin is not None:
        if shutil.which("taskset"):
            prefix = ["taskset", "-c", str(args.pin)]
        else:
            print("[aviso] taskset no esta disponible; se ejecuta sin fijar nucleo", file=sys.stderr)

    errors_path = os.path.join(os.path.dirname(args.out), "errors.log")
    t_start = time.time()
    with open(args.out, "a", newline="") as fout:
        w = csv.writer(fout)
        if new_file:
            w.writerow(columns)
        for idx, (key, extra) in enumerate(jobs, 1):
            print(f"[{idx}/{len(jobs)}] {key}", flush=True)
            try:
                r = subprocess.run(prefix + [args.bench] + extra, capture_output=True, text=True,
                                   timeout=args.timeout)
            except subprocess.TimeoutExpired:
                with open(errors_path, "a") as ef:
                    ef.write(f"TIMEOUT {key}\n")
                print("   -> timeout", file=sys.stderr)
                continue
            if r.returncode != 0 or not r.stdout.strip():
                with open(errors_path, "a") as ef:
                    ef.write(f"FALLO ({r.returncode}) {key}\n{r.stderr}\n")
                print(f"   -> fallo ({r.returncode}): {r.stderr.strip()[:200]}", file=sys.stderr)
                continue
            row = next(csv.reader([r.stdout.strip().splitlines()[-1]]))
            w.writerow(row + [key])
            fout.flush()

    print(f"[ok] terminado en {time.time() - t_start:.0f} s. Resultados en {args.out}")
    if os.path.exists(errors_path):
        print(f"[aviso] hubo errores, revisa {errors_path}")


if __name__ == "__main__":
    main()
