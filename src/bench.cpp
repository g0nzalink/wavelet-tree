// bench.cpp - Benchmark: WaveletTree propio (wavelet_tree.hpp) vs sdsl::wt_blcd<>
//
// Un proceso = una configuracion (implementacion, operacion, patron, datos).
// Imprime UNA linea CSV por stdout (usa --header para ver las columnas).
// Solo Linux (usa perf_event_open, getrusage). Compilar con CMake, ver README.
//
// Ejemplos:
//   ./bench --header
//   ./bench --impl mine --op select --sigma 16 --n 1000000 --queries 1000000
//   ./bench --impl sdsl --op build  --file datos/dna --prefix 20000000
#include "wavelet_tree.hpp"          // tu implementacion (struct WaveletTree)

#include <sdsl/wavelet_trees.hpp>

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <memory>
#include <random>
#include <string>
#include <vector>

#include <linux/perf_event.h>
#include <sys/ioctl.h>
#include <sys/resource.h>
#include <sys/syscall.h>
#include <unistd.h>

using std::string;
using std::vector;
using Clock = std::chrono::steady_clock;

// ---------------------------------------------------------------- utilidades
[[noreturn]] static void die(const string& msg) {
    fprintf(stderr, "ERROR: %s\n", msg.c_str());
    exit(2);
}

template <class T>
static inline void do_not_optimize(T const& v) {
    asm volatile("" : : "r,m"(v) : "memory");
}

static double median(vector<double> v) {
    if (v.empty()) return -1;
    std::sort(v.begin(), v.end());
    size_t m = v.size() / 2;
    return v.size() % 2 ? v[m] : 0.5 * (v[m - 1] + v[m]);
}
static double vmin(const vector<double>& v) { return v.empty() ? -1 : *std::min_element(v.begin(), v.end()); }
static double vmax(const vector<double>& v) { return v.empty() ? -1 : *std::max_element(v.begin(), v.end()); }

static long peak_rss_kb() {  // en Linux ru_maxrss viene en KB
    struct rusage r;
    getrusage(RUSAGE_SELF, &r);
    return r.ru_maxrss;
}

// ------------------------------------------------- contadores de hardware (perf)
// Cuenta SOLO el tramo que se encierra entre start() y stop(), en espacio de usuario.
// Si no hay permisos o el sistema no los expone (WSL, VM), devuelve -1.
struct Perf {
    int fd[4] = {-1, -1, -1, -1};  // ciclos, instrucciones, fallos L1D (lectura), fallos LL (lectura)

    static int open_ev(uint32_t type, uint64_t config, int group) {
        perf_event_attr pe;
        memset(&pe, 0, sizeof pe);
        pe.type = type;
        pe.size = sizeof pe;
        pe.config = config;
        pe.disabled = (group == -1);
        pe.exclude_kernel = 1;
        pe.exclude_hv = 1;
        return (int)syscall(SYS_perf_event_open, &pe, 0, -1, group, 0);
    }
    Perf() {
        const uint64_t R = PERF_COUNT_HW_CACHE_OP_READ << 8, M = PERF_COUNT_HW_CACHE_RESULT_MISS << 16;
        fd[0] = open_ev(PERF_TYPE_HARDWARE, PERF_COUNT_HW_CPU_CYCLES, -1);
        if (fd[0] < 0) return;
        fd[1] = open_ev(PERF_TYPE_HARDWARE, PERF_COUNT_HW_INSTRUCTIONS, fd[0]);
        fd[2] = open_ev(PERF_TYPE_HW_CACHE, PERF_COUNT_HW_CACHE_L1D | R | M, fd[0]);
        fd[3] = open_ev(PERF_TYPE_HW_CACHE, PERF_COUNT_HW_CACHE_LL | R | M, fd[0]);
    }
    ~Perf() { for (int f : fd) if (f >= 0) close(f); }
    void start() {
        if (fd[0] < 0) return;
        ioctl(fd[0], PERF_EVENT_IOC_RESET, PERF_IOC_FLAG_GROUP);
        ioctl(fd[0], PERF_EVENT_IOC_ENABLE, PERF_IOC_FLAG_GROUP);
    }
    void stop() { if (fd[0] >= 0) ioctl(fd[0], PERF_EVENT_IOC_DISABLE, PERF_IOC_FLAG_GROUP); }
    double read_counter(int i) const {
        if (fd[i] < 0) return -1;
        uint64_t v = 0;
        if (read(fd[i], &v, sizeof v) != (ssize_t)sizeof v) return -1;
        return (double)v;
    }
};

// ---------------------------------------------------------------- argumentos
struct Args {
    string impl = "mine";      // mine | sdsl
    string op = "access";      // build | access | rank | select
    string pattern = "uniform";  // uniform | sequential | hotspot
    string dist = "uniform";   // distribucion de simbolos del texto sintetico: uniform | zipf
    string file;               // si se da, se usa este archivo en vez de texto sintetico
    size_t prefix = 0;         // bytes a leer del archivo (0 = todo)
    size_t n = 1000000;
    int sigma = 16;
    size_t queries = 1000000;
    int reps = 5;
    uint64_t seed = 42;
    bool verify = true;
    bool header = false;
};

static Args parse(int argc, char** argv) {
    Args a;
    for (int i = 1; i < argc; i++) {
        string k = argv[i];
        auto val = [&]() -> string {
            if (i + 1 >= argc) die("falta valor para " + k);
            return argv[++i];
        };
        if (k == "--impl") a.impl = val();
        else if (k == "--op") a.op = val();
        else if (k == "--pattern") a.pattern = val();
        else if (k == "--dist") a.dist = val();
        else if (k == "--file") a.file = val();
        else if (k == "--prefix") a.prefix = std::stoull(val());
        else if (k == "--n") a.n = std::stoull(val());
        else if (k == "--sigma") a.sigma = std::stoi(val());
        else if (k == "--queries") a.queries = std::stoull(val());
        else if (k == "--reps") a.reps = std::stoi(val());
        else if (k == "--seed") a.seed = std::stoull(val());
        else if (k == "--no-verify") a.verify = false;
        else if (k == "--header") a.header = true;
        else die("argumento desconocido: " + k);
    }
    if (a.impl != "mine" && a.impl != "sdsl") die("--impl debe ser mine o sdsl");
    if (a.op != "build" && a.op != "access" && a.op != "rank" && a.op != "select") die("--op invalido");
    if (a.pattern != "uniform" && a.pattern != "sequential" && a.pattern != "hotspot") die("--pattern invalido");
    if (a.sigma < 1 || a.sigma > 256) die("--sigma debe estar en [1,256]");
    return a;
}

static const char* HEADER =
    "impl,op,pattern,source,dist,n,sigma,queries,reps,"
    "ns_median,ns_min,ns_max,build_s,build_s_min,build_s_max,"
    "struct_bytes,bpc,peak_rss_kb,rss_delta_kb,"
    "cycles_q,instr_q,l1d_miss_q,ll_miss_q,checksum";

// ------------------------------------------------------------------ datos
static string make_text(const Args& a) {
    string s;
    if (!a.file.empty()) {
        std::ifstream f(a.file, std::ios::binary);
        if (!f) die("no se pudo abrir " + a.file);
        f.seekg(0, std::ios::end);
        size_t sz = (size_t)f.tellg();
        f.seekg(0);
        size_t n = (a.prefix && a.prefix < sz) ? a.prefix : sz;
        s.resize(n);
        f.read(&s[0], (std::streamsize)n);
        return s;
    }
    std::mt19937_64 rng(a.seed);
    int off = a.sigma < 256 ? 1 : 0;  // evita el byte 0 salvo que hagan falta los 256
    s.resize(a.n);
    if (a.dist == "zipf") {
        vector<double> w(a.sigma);
        for (int k = 0; k < a.sigma; k++) w[k] = 1.0 / (k + 1);
        std::discrete_distribution<int> d(w.begin(), w.end());
        for (size_t i = 0; i < a.n; i++) s[i] = (char)(off + d(rng));
    } else {
        std::uniform_int_distribution<int> d(0, a.sigma - 1);
        for (size_t i = 0; i < a.n; i++) s[i] = (char)(off + d(rng));
    }
    return s;
}

// ---------------------------------------------------------- wrappers de implementaciones
// Interfaz comun: build, bytes, access(i), rank(c,i), select(c,j) -> int
struct MineW {
    std::unique_ptr<WaveletTree> t;
    void build(const string& s) { t.reset(new WaveletTree(s)); }
    size_t bytes() { return t->bytes(); }
    int access(int i) { return (unsigned char)t->access(i); }
    int rank(int c, int i) { return t->rank((char)c, i); }
    int select(int c, int j) { return t->select((char)c, j); }
};

struct SdslW {
    sdsl::wt_blcd<> t;  // rank_support_v + select_support_mcl por defecto
    void build(const string& s) {
        t = sdsl::wt_blcd<>();
        sdsl::construct_im(t, s, 1);
    }
    size_t bytes() { return sdsl::size_in_bytes(t); }
    int access(int i) { return (int)t[i]; }
    int rank(int c, int i) { return (int)t.rank(i, (uint8_t)c); }      // OJO: SDSL usa (i, c)
    int select(int c, int j) { return (int)t.select(j, (uint8_t)c); }  // OJO: SDSL usa (j, c)
};

// ----------------------------------------------------------------- consultas
struct Query { int c; int x; int exp; };  // simbolo, argumento (i o j), resultado esperado

static vector<uint32_t> make_positions(const string& pattern, size_t n, size_t Q, std::mt19937_64& rng) {
    vector<uint32_t> p(Q);
    std::uniform_int_distribution<uint32_t> any(0, (uint32_t)(n - 1));
    if (pattern == "uniform") {
        for (auto& x : p) x = any(rng);
    } else if (pattern == "sequential") {
        uint32_t start = any(rng);
        for (size_t k = 0; k < Q; k++) p[k] = (uint32_t)((start + k) % n);
    } else {  // hotspot: 80% de las consultas caen en el 1% de las posiciones
        uint32_t h = (uint32_t)std::max<size_t>(1, n / 100);
        uint32_t start = std::uniform_int_distribution<uint32_t>(0, (uint32_t)n - h)(rng);
        std::uniform_real_distribution<double> u(0, 1);
        std::uniform_int_distribution<uint32_t> hot(start, start + h - 1);
        for (auto& x : p) x = (u(rng) < 0.8) ? hot(rng) : any(rng);
    }
    return p;
}

template <class W>
static inline int one(W& w, int op, const Query& q) {
    return op == 1 ? w.access(q.x) : op == 2 ? w.rank(q.c, q.x) : w.select(q.c, q.x);
}

template <class W>
static uint64_t pass(W& w, int op, const vector<Query>& qs) {
    uint64_t sum = 0;
    if (op == 1) for (const auto& q : qs) sum += (uint64_t)w.access(q.x);
    else if (op == 2) for (const auto& q : qs) sum += (uint64_t)w.rank(q.c, q.x);
    else for (const auto& q : qs) sum += (uint64_t)w.select(q.c, q.x);
    return sum;
}

// ---------------------------------------------------------------------- main
template <class W>
static int run(const Args& a, const string& text, int sigma_real, const string& source) {
    const size_t n = text.size();
    const long base_rss = peak_rss_kb();  // pico tras cargar/generar el texto
    int op = a.op == "access" ? 1 : a.op == "rank" ? 2 : a.op == "select" ? 3 : 0;

    double ns_med = -1, ns_min = -1, ns_max = -1;
    double cyc = -1, ins = -1, l1 = -1, ll = -1;
    uint64_t checksum = 0;
    vector<double> bt;
    size_t struct_bytes = 0;
    size_t Q = 0;

    if (op == 0) {  // ---- construccion: se repite a.reps veces
        for (int r = 0; r < a.reps; r++) {
            W w;
            auto t0 = Clock::now();
            w.build(text);
            auto t1 = Clock::now();
            bt.push_back(std::chrono::duration<double>(t1 - t0).count());
            if (r == 0) struct_bytes = w.bytes();
        }
    } else {  // ---- consultas: una construccion + varias pasadas
        W w;
        auto t0 = Clock::now();
        w.build(text);
        auto t1 = Clock::now();
        bt.push_back(std::chrono::duration<double>(t1 - t0).count());
        struct_bytes = w.bytes();

        vector<int> occ;  // occ[i] = numero de apariciones de text[i] en text[0..i]
        {
            occ.resize(n);
            int cnt[256] = {0};
            for (size_t i = 0; i < n; i++) occ[i] = ++cnt[(unsigned char)text[i]];
        }
        std::mt19937_64 rng(a.seed + 1);
        Q = a.queries;
        auto pos = make_positions(a.pattern, n, Q, rng);
        vector<Query> qs(Q);
        uint64_t expsum = 0;
        for (size_t k = 0; k < Q; k++) {
            uint32_t p = pos[k];
            unsigned char c = (unsigned char)text[p];
            if (op == 1) qs[k] = {0, (int)p, (int)c};
            else if (op == 2) qs[k] = {(int)c, (int)p + 1, occ[p]};  // rank(c, p+1) = occ[p]
            else qs[k] = {(int)c, occ[p], (int)p};                    // select(c, occ[p]) = p
            expsum += (uint64_t)qs[k].exp;
        }
        occ.clear(); occ.shrink_to_fit();

        if (a.verify) {  // comprobacion exacta (fuera del tiempo medido)
            size_t m = std::min<size_t>(Q, 200000);
            for (size_t k = 0; k < m; k++) {
                int r = one(w, op, qs[k]);
                if (r != qs[k].exp) {
                    fprintf(stderr, "ERROR de correccion (%s %s): consulta %zu c=%d x=%d esperado=%d obtuvo=%d\n",
                            a.impl.c_str(), a.op.c_str(), k, qs[k].c, qs[k].x, qs[k].exp, r);
                    return 3;
                }
            }
        }
        do_not_optimize(pass(w, op, qs));  // calentamiento (cache, TLB, predictor)

        Perf perf;
        vector<double> ns, vc, vi, v1, vl;
        for (int r = 0; r < a.reps; r++) {
            perf.start();
            auto s0 = Clock::now();
            uint64_t sum = pass(w, op, qs);
            auto s1 = Clock::now();
            perf.stop();
            do_not_optimize(sum);
            if (sum != expsum) {
                fprintf(stderr, "ERROR: checksum distinto (%s %s)\n", a.impl.c_str(), a.op.c_str());
                return 3;
            }
            checksum = sum;
            ns.push_back(std::chrono::duration<double, std::nano>(s1 - s0).count() / (double)Q);
            double c0 = perf.read_counter(0);
            if (c0 >= 0) {
                vc.push_back(c0 / Q);
                vi.push_back(perf.read_counter(1) / Q);
                double a1 = perf.read_counter(2), a2 = perf.read_counter(3);
                if (a1 >= 0) v1.push_back(a1 / Q);
                if (a2 >= 0) vl.push_back(a2 / Q);
            }
        }
        ns_med = median(ns); ns_min = vmin(ns); ns_max = vmax(ns);
        cyc = median(vc); ins = median(vi); l1 = median(v1); ll = median(vl);
    }

    long peak = peak_rss_kb();
    double bpc = n ? 8.0 * (double)struct_bytes / (double)n : -1;
    printf("%s,%s,%s,%s,%s,%zu,%d,%zu,%d,%.3f,%.3f,%.3f,%.6f,%.6f,%.6f,%zu,%.4f,%ld,%ld,%.3f,%.3f,%.5f,%.5f,%llu\n",
           a.impl.c_str(), a.op.c_str(), op == 0 ? "-" : a.pattern.c_str(), source.c_str(),
           a.file.empty() ? a.dist.c_str() : "-", n, sigma_real, Q, a.reps,
           ns_med, ns_min, ns_max, median(bt), vmin(bt), vmax(bt),
           struct_bytes, bpc, peak, peak - base_rss, cyc, ins, l1, ll, (unsigned long long)checksum);
    return 0;
}

int main(int argc, char** argv) {
    Args a = parse(argc, argv);
    if (a.header) { puts(HEADER); return 0; }

    string text = make_text(a);
    if (text.empty()) die("texto vacio");
    bool seen[256] = {false};
    for (unsigned char c : text) seen[c] = true;
    int sigma_real = 0;
    for (bool b : seen) sigma_real += b;

    string source = "synthetic";
    if (!a.file.empty()) {
        size_t sl = a.file.find_last_of('/');
        source = sl == string::npos ? a.file : a.file.substr(sl + 1);
    }
    return a.impl == "mine" ? run<MineW>(a, text, sigma_real, source)
                            : run<SdslW>(a, text, sigma_real, source);
}
