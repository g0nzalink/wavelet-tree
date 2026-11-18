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


NAN = float("nan")


def val(d, impl, col, op, pat=None):
    """Valor medio de una columna para (impl, op[, patron]); NaN si no existe o si no hay contadores (-1)."""
    m = (d.impl == impl) & (d.op == op)
    if pat is not None:
        m &= d.pattern == pat
    s = d.loc[m, col]
    v = float(s.mean()) if len(s) else NAN
    return NAN if v < 0 else v


def ratio(a, b):
    """a/b, o NaN si alguno no es válido (evita dividir por 0 cuando el delta de memoria es 0)."""
    return a / b if (b == b and a == a and b > 0) else NAN


def bars2(ax, cats, f, ylabel, title, log=False, labels=None, fs=9):
    """Barras agrupadas propio vs SDSL. f(impl, cat) -> valor."""
    w = 0.38
    for k, impl in enumerate(("mine", "sdsl")):
        ax.bar([i + (k - .5) * w for i in range(len(cats))], [f(impl, c) for c in cats], w,
               color=COLORS[impl], label=LABELS[impl])
    ax.set_xticks(range(len(cats)))
    ax.set_xticklabels(labels or cats, fontsize=fs)
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontsize=10)
    ax.grid(alpha=.3, axis="y", which="both")
    if log:
        ax.set_yscale("log")


def fig_real(df, out):
    """Un panel por archivo real: latencia, patrones, bpc, construcción, memoria y caché."""
    real = df[df.source != "synthetic"]
    for src in real.source.unique():
        d = real[real.source == src]
        n, sg = int(d.n.iloc[0]), int(d.sigma.iloc[0])
        fig, ax = plt.subplots(2, 3, figsize=(15, 8.2))

        bars2(ax[0][0], OPS, lambda i, o: val(d, i, "ns_median", o, "uniform"),
              "ns por consulta", "Latencia (patrón uniforme)", log=True)
        ax[0][0].legend(fontsize=8)

        cp = [(o, p) for o in OPS for p in ("uniform", "sequential", "hotspot")]
        bars2(ax[0][1], cp, lambda i, c: val(d, i, "ns_median", c[0], c[1]),
              "ns por consulta", "Latencia por patrón de acceso", log=True,
              labels=[f"{o}\n{p[:4]}" for o, p in cp], fs=7)

        bars2(ax[0][2], ["bpc"], lambda i, c: val(d, i, "bpc", "build"), "bits por carácter",
              "Espacio de la estructura", log=True, labels=[""])
        ax[0][2].axhline(math.ceil(math.log2(max(sg, 2))), color="k", ls="--", lw=1, label="ceil(log2 σ)")
        ax[0][2].axhline(8, color="gray", ls=":", lw=1, label="texto plano (8 bpc)")
        ax[0][2].legend(fontsize=8)

        bars2(ax[1][0], [""], lambda i, c: val(d, i, "build_s", "build"), "segundos",
              "Tiempo de construcción", labels=[""])
        bars2(ax[1][1], [""], lambda i, c: val(d, i, "rss_delta_kb", "build") / 1024, "MB",
              "Pico de memoria sobre el texto (construcción)", labels=[""])

        cc = [(o, c) for o in OPS for c in ("l1d_miss_q", "ll_miss_q")]
        bars2(ax[1][2], cc, lambda i, c: val(d, i, c[1], c[0], "uniform"), "fallos por consulta",
              "Fallos de caché (uniforme)", labels=[f"{o}\n{'L1D' if c.startswith('l1d') else 'LL'}" for o, c in cc], fs=7)
        if all(math.isnan(val(d, i, c[1], c[0], "uniform")) for i in ("mine", "sdsl") for c in cc):
            ax[1][2].text(.5, .5, "sin contadores\nde hardware", ha="center", va="center",
                          transform=ax[1][2].transAxes, color="gray")

        fig.suptitle(f"{src}   (n={human_n(n)}, σ={sg})")
        save(fig, out, f"07_real_{os.path.splitext(src)[0]}.png")


def fig_real_summary(df, out):
    """Comparación entre archivos reales (ordenados por σ): razón propio/SDSL."""
    real = df[df.source != "synthetic"]
    srcs = sorted(real.source.unique(), key=lambda s_: real[real.source == s_].sigma.iloc[0])
    if len(srcs) < 2:
        return
    labels = [f"{s_}\nσ={int(real[real.source == s_].sigma.iloc[0])}" for s_ in srcs]
    D = {s_: real[real.source == s_] for s_ in srcs}
    x = range(len(srcs))
    fig, ax = plt.subplots(1, 3, figsize=(15, 4.4))

    w = 0.27
    for k, op in enumerate(OPS):
        r = [ratio(val(D[s_], "mine", "ns_median", op, "uniform"), val(D[s_], "sdsl", "ns_median", op, "uniform"))
             for s_ in srcs]
        ax[0].bar([i + (k - 1) * w for i in x], r, w, label=op)
    ax[0].axhline(1, color="k", lw=1)
    ax[0].set_yscale("log")
    ax[0].set_title("Latencia: propio / SDSL  (>1 = SDSL más rápido)", fontsize=10)
    ax[0].legend(fontsize=8)

    bars2(ax[1], srcs, lambda i, s_: val(D[s_], i, "bpc", "build"), "bits por carácter",
          "Espacio (bpc)", log=True, labels=labels, fs=8)
    ax[1].legend(fontsize=8)

    ax[2].bar([i - w / 2 for i in x], [ratio(val(D[s_], "mine", "build_s", "build"), val(D[s_], "sdsl", "build_s", "build"))
                                       for s_ in srcs], w, label="tiempo de construcción")
    ax[2].bar([i + w / 2 for i in x], [ratio(val(D[s_], "mine", "rss_delta_kb", "build"),
                                             val(D[s_], "sdsl", "rss_delta_kb", "build")) for s_ in srcs], w,
              label="pico de memoria")
    ax[2].axhline(1, color="k", lw=1)
    ax[2].set_yscale("log")
    ax[2].set_title("Construcción: propio / SDSL  (>1 = SDSL mejor)", fontsize=10)
    ax[2].legend(fontsize=8)

    for a_ in (ax[0], ax[2]):
        a_.set_xticks(list(x))
        a_.set_xticklabels(labels, fontsize=8)
        a_.grid(alpha=.3, axis="y", which="both")
    fig.suptitle("Pizza&Chili: resumen entre archivos")
    save(fig, out, "08_real_resumen.png")


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
    fig_real_summary(df, args.out)
    summary(df, os.path.dirname(args.out))


if __name__ == "__main__":
    main()
