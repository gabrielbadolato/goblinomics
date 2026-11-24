"""Leitor mínimo de tabelas literais de Lua (só dados: tabelas, números, textos, nil, nomes)."""
import re

TOK = re.compile(r'''\s*(?:(--\[\[.*?\]\])|(--[^\n]*)|("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')|(-?\d+\.?\d*(?:e-?\d+)?)|([A-Za-z_][\w.]*)|(.))''', re.S)

def tokens(t):
    pos = 0
    while pos < len(t):
        m = TOK.match(t, pos)
        if not m: break
        pos = m.end()
        if m.group(1) or m.group(2): continue
        if m.group(3): yield ("s", bytes(m.group(3)[1:-1], "utf-8").decode("unicode_escape").encode("latin-1", "ignore").decode("utf-8", "ignore") if "\\" in m.group(3) else m.group(3)[1:-1])
        elif m.group(4): yield ("n", float(m.group(4)) if "." in m.group(4) or "e" in m.group(4) else int(m.group(4)))
        elif m.group(5): yield ("i", m.group(5))
        elif m.group(6).strip(): yield ("p", m.group(6))

class P:
    def __init__(self, t): self.t = list(tokens(t)); self.i = 0
    def peek(self): return self.t[self.i] if self.i < len(self.t) else ("e", None)
    def nxt(self): x = self.peek(); self.i += 1; return x
    def value(self):
        k, v = self.nxt()
        if k == "p" and v == "{": return self.table()
        if k in "sn": return v
        if k == "i": return None if v == "nil" else True if v == "true" else False if v == "false" else "@" + v
        raise ValueError((k, v, self.i))
    def table(self):
        d, n = {}, 1
        while True:
            k, v = self.peek()
            if k == "p" and v == "}": self.i += 1; break
            if k == "p" and v in ",;": self.i += 1; continue
            if k == "p" and v == "[":
                self.i += 1; key = self.value(); assert self.nxt() == ("p", "]"); assert self.nxt() == ("p", "=")
                if isinstance(key, str) and key.startswith("@"): key = key.split(".")[-1]
                d[key] = self.value()
            elif k == "i" and self.t[self.i + 1] == ("p", "="):
                self.i += 2; d[v] = self.value()
            else:
                d[n] = self.value(); n += 1
        return d

def tabela(texto): 
    p = P(texto); assert p.nxt() == ("p", "{"); return p.table()

def lista(d):
    """Tabela posicional -> lista (com None nos buracos)."""
    if not isinstance(d, dict): return d
    n = max([k for k in d if isinstance(k, int)] or [0])
    return [d.get(i) for i in range(1, n + 1)]
