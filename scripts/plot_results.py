#!/usr/bin/env python3
"""Lee results/results.csv y genera las graficas del informe en results/plots/ (+ summary.csv).

  python3 scripts/plot_results.py
  python3 scripts/plot_results.py --csv results/results.csv --out results/plots
"""
import argparse
import math
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COLORS = {"mine": "#d1495b", "sdsl": "#2e6f95"}
LABELS = {"mine": "Wavelet Tree propio", "sdsl": "SDSL-lite wt_blcd"}
OPS = ["access", "rank", "select"]


def human_n(n):
    return f"{n / 1e6:g}M" if n >= 1e6 else f"{n / 1e3:g}k"


def save(fig, out, name):
    fig.tight_layout()
    path = os.path.join(out, name)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print("  ->", path)


def lines_by_impl(ax, df, x, y, **kw):
    for impl in ("mine", "sdsl"):
        d = df[df.impl == impl].sort_values(x)
        if not d.empty:
            ax.plot(d[x], d[y], marker="o", color=COLORS[impl], label=LABELS[impl], **kw)


def fig_query_vs_sigma(q, out):
    fig, axes = plt.subplots(1, 3, figsize=(14, 4))
    for ax, op in zip(axes, OPS):
        d = q[(q.op == op) & (q.pattern == "uniform")]
        for n, ls in zip(sorted(d.n.unique())[-3:], ("-", "--", ":")):
            for impl in ("mine", "sdsl"):
                dd = d[(d.impl == impl) & (d.n == n)].sort_values("sigma")
                if not dd.empty:
                    ax.plot(dd.sigma, dd.ns_median, ls, marker="o", color=COLORS[impl],
                            label=f"{LABELS[impl]} (n={human_n(n)})")
        ax.set_xscale("log", base=2)
        ax.set_yscale("log")
        ax.set_xlabel("sigma (tamaño del alfabeto)")
        ax.set_ylabel("ns por consulta")
        ax.set_title(f"{op}  (patrón uniforme)")
        ax.grid(alpha=.3, which="both")
    axes[0].legend(fontsize=7)
    fig.suptitle("Latencia de consulta vs sigma (eje Y logarítmico)")
    save(fig, out, "01_latencia_vs_sigma.png")


def fig_patterns(q, out):
    n_max = q.n.max()
    sigmas = sorted(q.sigma.unique())
    sigma = 64 if 64 in sigmas else sigmas[len(sigmas) // 2]
    d = q[(q.n == n_max) & (q.sigma == sigma)]
    pats = [p for p in ("uniform", "sequential", "hotspot") if p in d.pattern.unique()]
    if len(pats) < 2:
        return
    fig, axes = plt.subplots(1, 3, figsize=(14, 4))
    for ax, op in zip(axes, OPS):
        w = 0.38
        for k, impl in enumerate(("mine", "sdsl")):
            vals = [d[(d.op == op) & (d.impl == impl) & (d.pattern == p)].ns_median.mean() for p in pats]
            ax.bar([i + (k - .5) * w for i in range(len(pats))], vals, w, color=COLORS[impl], label=LABELS[impl])
        ax.set_xticks(range(len(pats)))
        ax.set_xticklabels(pats)
        ax.set_yscale("log")
        ax.set_ylabel("ns por consulta")
        ax.set_title(op)
        ax.grid(alpha=.3, axis="y", which="both")
    axes[0].legend(fontsize=8)
    fig.suptitle(f"Patrones de acceso (n={human_n(n_max)}, sigma={sigma})")
    save(fig, out, "02_patrones_de_acceso.png")


def fig_bpc(b, out):
    n_max = b.n.max()
    d = b[b.n == n_max]
    fig, ax = plt.subplots(figsize=(6.5, 4.2))
    lines_by_impl(ax, d, "sigma", "bpc")
    sg = sorted(d.sigma.unique())
    ax.plot(sg, [math.ceil(math.log2(s)) if s > 1 else 1 for s in sg], "k--", lw=1, label="ceil(log2 sigma) (mínimo teórico)")
    ax.plot(sg, [8] * len(sg), color="gray", lw=1, ls=":", label="texto plano (8 bpc)")
    ax.set_xscale("log", base=2)
    ax.set_yscale("log")
    ax.set_xlabel("sigma")
    ax.set_ylabel("bits por carácter (bpc)")
    ax.set_title(f"Espacio de la estructura (n={human_n(n_max)})")
    ax.grid(alpha=.3, which="both")
    ax.legend(fontsize=8)
    save(fig, out, "03_bpc_vs_sigma.png")


def fig_build(b, out):
    sigmas = sorted(b.sigma.unique())
    fig, axes = plt.subplots(1, len(sigmas), figsize=(3.6 * len(sigmas), 3.8), squeeze=False)
    for ax, s in zip(axes[0], sigmas):
        lines_by_impl(ax, b[b.sigma == s], "n", "build_s")
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_title(f"sigma={s}")
        ax.set_xlabel("n")
        ax.grid(alpha=.3, which="both")
    axes[0][0].set_ylabel("segundos de construcción")
    axes[0][0].legend(fontsize=7)
    save(fig, out, "04_construccion_vs_n.png")


def fig_rss(b, out):
    n_max = b.n.max()
    d = b[b.n == n_max]
    fig, ax = plt.subplots(figsize=(6.5, 4.2))
    d = d.assign(mb=d.rss_delta_kb / 1024)
    lines_by_impl(ax, d, "sigma", "mb")
    ax.set_xscale("log", base=2)
    ax.set_yscale("log")
    ax.set_xlabel("sigma")
    ax.set_ylabel("pico de RSS sobre el texto (MB)")
    ax.set_title(f"Memoria pico durante la construcción (n={human_n(n_max)})")
    ax.grid(alpha=.3, which="both")
    ax.legend(fontsize=8)
    save(fig, out, "05_memoria_pico.png")


def fig_cache(q, out):
    cols = [("l1d_miss_q", "fallos L1D por consulta"), ("ll_miss_q", "fallos LL por consulta"),
            ("instr_q", "instrucciones por consulta")]
    d = q[(q.pattern == "uniform") & (q.cycles_q > 0)]
    if d.empty:
        print("  (sin contadores de hardware en el CSV: se omite la gráfica de caché)")
        return
    sigmas = sorted(d.sigma.unique())
    sigma = 64 if 64 in sigmas else sigmas[len(sigmas) // 2]
    d = d[d.sigma == sigma]
    fig, axes = plt.subplots(len(cols), 3, figsize=(13, 3.2 * len(cols)), squeeze=False)
    for r, (col, title) in enumerate(cols):
        for c, op in enumerate(OPS):
            ax = axes[r][c]
            dd = d[(d.op == op) & (d[col] >= 0)]
            lines_by_impl(ax, dd, "n", col)
            ax.set_xscale("log")
            ax.grid(alpha=.3)
            ax.set_title(f"{op}: {title}", fontsize=9)
            ax.set_xlabel("n")
    axes[0][0].legend(fontsize=7)
    fig.suptitle(f"Contadores de hardware (patrón uniforme, sigma={sigma})")
    save(fig, out, "06_contadores_de_hardware.png")


def fig_real(df, out):
    real = df[df.source != "synthetic"]
    for src in real.source.unique():
        d = real[real.source == src]
        q = d[d.op.isin(OPS) & (d.pattern == "uniform")]
        if q.empty:
            continue
        fig, axes = plt.subplots(1, 2, figsize=(11, 4))
        w = 0.38
        for k, impl in enumerate(("mine", "sdsl")):
            vals = [q[(q.impl == impl) & (q.op == op)].ns_median.mean() for op in OPS]
            axes[0].bar([i + (k - .5) * w for i in range(3)], vals, w, color=COLORS[impl], label=LABELS[impl])
        axes[0].set_xticks(range(3))
        axes[0].set_xticklabels(OPS)
        axes[0].set_yscale("log")
        axes[0].set_ylabel("ns por consulta")
        axes[0].legend(fontsize=8)
        bp = d.groupby("impl").bpc.first()
        axes[1].bar([LABELS[i] for i in bp.index], bp.values, color=[COLORS[i] for i in bp.index])
        axes[1].set_ylabel("bits por carácter")
        s, n = int(d.sigma.iloc[0]), int(d.n.iloc[0])
        fig.suptitle(f"{src}  (n={human_n(n)}, sigma={s})")
        save(fig, out, f"07_real_{os.path.splitext(src)[0]}.png")


def summary(df, out_dir):
    """Razon propio / SDSL (>1 = SDSL es mas rapido o mas chico)."""
    keys = ["op", "pattern", "source", "dist", "n", "sigma"]
    cols = ["ns_median", "build_s", "bpc", "l1d_miss_q", "ll_miss_q"]
    m = df[df.impl == "mine"].set_index(keys)[cols]
    s = df[df.impl == "sdsl"].set_index(keys)[cols]
    j = m.join(s, lsuffix="_mine", rsuffix="_sdsl", how="inner")
    for c in cols:
        a, b = j[f"{c}_mine"], j[f"{c}_sdsl"]
        j[f"{c}_ratio"] = (a / b).where((a >= 0) & (b > 0))
    path = os.path.join(out_dir, "summary.csv")
    j.reset_index().to_csv(path, index=False, float_format="%.4g")
    print("  ->", path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=os.path.join(ROOT, "results", "results.csv"))
    ap.add_argument("--out", default=os.path.join(ROOT, "results", "plots"))
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    df = pd.read_csv(args.csv)
    syn = df[df.source == "synthetic"]
    q = syn[syn.op.isin(OPS)]
    b = syn[syn.op == "build"]
    print(f"[info] {len(df)} filas leídas")

    if not q.empty:
        fig_query_vs_sigma(q, args.out)
        fig_patterns(q, args.out)
        fig_cache(q, args.out)
    if not b.empty:
        fig_bpc(b, args.out)
        fig_build(b, args.out)
        fig_rss(b, args.out)
    fig_real(df, args.out)
    summary(df, os.path.dirname(args.out))


if __name__ == "__main__":
    main()
