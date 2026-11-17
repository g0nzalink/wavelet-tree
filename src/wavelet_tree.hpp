#include <algorithm>
#include <iostream>
#include <vector>
#include <string>
#include <random>

using namespace std;

struct bitvector {
    vector<int> tilin = {}; //apariciones de 1s a lo largo del bitmap
    
    bitvector(vector<int>& bitmap) {
        tilin.resize(bitmap.size() + 1, 0);
        for(size_t i = 0; i < bitmap.size(); i++) tilin[i+1] = tilin[i] + bitmap[i];
    }

    int rank1(int i){return tilin[i];}
    int rank0(int i){return i - tilin[i];}

    int select1(int j){            // posición del j-ésimo 1, j desde 1
        int lo = 0, hi = (int)tilin.size() - 2;   // hi = n - 1
        while (lo < hi) {
            int m = (lo + hi) / 2;
            if (rank1(m + 1) >= j) hi = m;
            else lo = m + 1;
        }
        return lo;
    }

    int select0(int j){            // posición del j-ésimo 0, j desde 1
        int lo = 0, hi = (int)tilin.size() - 2;
        while (lo < hi) {
            int m = (lo + hi) / 2;
            if (rank0(m + 1) >= j) hi = m;
            else lo = m + 1;
        }
        return lo;
    }

};

struct node {
    int lo = 0;
    int hi = 0;
    bitvector* data = nullptr;
    node* left = nullptr;
    node* right = nullptr;
};

struct WaveletTree {
    vector<char> alfabeto;
    int mapa[256]; // mapa[c] = posicion de c en el alfabeto, -1 si no aparece en el texto
    node* root = nullptr;
    int tamanio;

    int indice(char c) {
        return mapa[(unsigned char)c];
    }

    WaveletTree(const string& s) {
        for(int i = 0; i < 256; i++) mapa[i] = -1; // por si el string viene vacio
        tamanio = s.size();
        if (tamanio == 0) return;
        alfabeto.assign(s.begin(), s.end());
        sort(alfabeto.begin(), alfabeto.end());
        alfabeto.erase(unique(alfabeto.begin(), alfabeto.end()), alfabeto.end());

        alfabeto.shrink_to_fit(); // el assign reservo n chars, liberamos lo que sobra

        //con lo anterior ahora esta el alfabeto puro nomas
        for(int i = 0; i < (int)alfabeto.size(); i++) mapa[(unsigned char)alfabeto[i]] = i;

        vector <int> v;
        for(char c : s){v.push_back(indice(c));}
        root = build(v, 0, alfabeto.size() - 1);
    }

    node* build(vector<int>& s, int lo, int hi) { //s es el string convertido a enteros basado en el orden del alfabeto
        node* n = new node{lo, hi};
        if(lo == hi) return n;
        int mid = (lo + hi) / 2;
        vector<int> bitmap, L, R;
        for(int x: s) {
            bool bit = x > mid;
            bitmap.push_back(bit);
            (bit ? R : L).push_back(x);
        }
        node* left = build(L, lo, mid);
        node* right = build(R, mid + 1, hi);
        n->data = new bitvector(bitmap);
        n->left = left;
        n->right = right;
        return n;
    }

    char access(int i) { // que letra esta en la posicion i
        if (root == nullptr || i < 0 || i >= tamanio) return '\0';
        node* n = root;
        while(n->lo != n->hi) {
            int b = n->data->rank1(i+1) - n->data->rank1(i); // cual es el bit que esta en la posicion i
            i = b ? n->data->rank1(i) : n->data->rank0(i); // nueva posicion de i para el nodo que vaya
            n = b ? n->right : n->left;
        }
        return alfabeto[n->lo];
    }

    int rank(char c_, int i) { // cuantas apariciones tiene c_ hasta la posicion i
        if(i < 0 || i > tamanio) return -1; // primero vemos si la posicion es valida
        int c = indice(c_);
        if (c < 0) return 0;
        if(i == 0) return 0;
        node* n = root;
        while(n->lo != n->hi) {
            int mid = (n->lo + n->hi) / 2;
            if(c > mid) {
                i = n->data->rank1(i);
                n = n->right;
            }
            else {
                i = n->data->rank0(i);
                n = n->left;
            }
        }
        return i;
    }

    int select(char c_, int j) { // donde esta el j-esimo c_
        int c = indice(c_);
        if(c < 0 || j < 1 || j > rank(c_,tamanio)) return -1;
        node* n = root;
        vector<int> bits_tomados;
        vector<node*> nodes;
        while(n->lo != n->hi) {
            int mid = (n->lo + n->hi) / 2;
            nodes.push_back(n);
            if(c > mid) {
                n = n->right;
                bits_tomados.push_back(1);
            }
            else {
                n = n->left;
                bits_tomados.push_back(0);
            }
        }
        int pos = j - 1;
        for(int i = bits_tomados.size() - 1; i >= 0; i--) {
            if(bits_tomados[i]) {
                pos = nodes[i]->data->select1(pos+1);
            }
            else {
                pos = nodes[i]->data->select0(pos+1);
            }
        }
        return pos;
    }

    // libera todos los nodos 
    void destruir(node* n) {
        if(n == nullptr) return;
        destruir(n->left);
        destruir(n->right);
        delete n->data;
        delete n;
    }
    ~WaveletTree() { destruir(root); }

    // no copiamos el arbol, si no dos objetos liberarian los mismos nodos
    WaveletTree(const WaveletTree&) = delete;
    WaveletTree& operator=(const WaveletTree&) = delete;

    // bytes que ocupa la estructura, para calcular bits por caracter: bpc = 8 * bytes() / n
    size_t bytes_nodo(node* n) {
        if(n == nullptr) return 0;
        size_t total = sizeof(node);
        if(n->data) total += sizeof(bitvector) + n->data->tilin.capacity() * sizeof(int);
        return total + bytes_nodo(n->left) + bytes_nodo(n->right);
    }
    size_t bytes() {
        return sizeof(WaveletTree) + alfabeto.capacity() * sizeof(char) + bytes_nodo(root);
    }
};

