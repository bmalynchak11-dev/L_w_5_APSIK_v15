"""Допоміжні засоби перевірки: мінімальні рушії PromQL і LogQL, імітація relabel, розбирач синтаксису Alloy.

Рушії реалізують лише ту підмножину мов, яка потрібна задачам лабораторної. Обчислення PromQL повторює алгоритми
Prometheus (екстраполяція rate, регресія predict_linear), тому очікувані значення можна звірити з реальним Prometheus.
Файл однаковий у студентському й викладацькому наборах і його не слід змінювати.
"""
import math
import re

# ======================================================================================
# PromQL
# ======================================================================================
DUR_UNITS = {"ms": 0.001, "s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800, "y": 31536000}
LOOKBACK = 300.0


def parse_duration(text):
    """'5m' -> 300.0, '1h30m' -> 5400.0"""
    parts = re.findall(r"(\d+)(ms|s|m|h|d|w|y)", text)
    if not parts or "".join(a + b for a, b in parts) != text:
        raise ValueError(f"некоректна тривалість: {text!r}")
    return float(sum(int(a) * DUR_UNITS[b] for a, b in parts))


class PromQLError(Exception):
    pass


_TOKEN = re.compile(r"""\s*(?:
    (?P<str>"(?:\\.|[^"\\])*"|`[^`]*`|'(?:\\.|[^'\\])*')|
    (?P<dur>\[\s*(?:\d+(?:ms|s|m|h|d|w|y))+\s*\])|
    (?P<num>(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?(?![A-Za-z_]))|
    (?P<id>[A-Za-z_:][A-Za-z0-9_:]*)|
    (?P<op>==|!=|>=|<=|=~|!~|[-+*/%^<>=(){},])
    )""", re.X)

AGG = {"sum", "avg", "min", "max", "count", "topk", "bottomk", "group"}
FUNCS = {"rate", "irate", "increase", "delta", "changes", "resets", "avg_over_time", "min_over_time", "max_over_time",
         "sum_over_time", "count_over_time", "predict_linear", "time", "abs", "ceil", "floor", "round", "clamp_min",
         "clamp_max", "vector", "scalar", "sqrt"}
SET_OPS = {"and", "or", "unless"}
PREC = [("or",), ("and", "unless"), ("==", "!=", "<", ">", "<=", ">="), ("+", "-"), ("*", "/", "%"), ("^",)]


def _tokens(text):
    pos, out = 0, []
    text = text.strip()
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if not m or m.end() == pos:
            raise PromQLError(f"неочікуваний символ на позиції {pos}: {text[pos:pos + 10]!r}")
        pos = m.end()
        kind = m.lastgroup
        out.append((kind, m.group(kind)))
        while pos < len(text) and text[pos].isspace():
            pos += 1
    return out


class _Parser:
    def __init__(self, text):
        self.t = _tokens(text)
        self.i = 0

    def peek(self, k=0):
        return self.t[self.i + k] if self.i + k < len(self.t) else (None, None)

    def take(self):
        tok = self.peek()
        self.i += 1
        return tok

    def expect(self, val):
        k, v = self.take()
        if v != val:
            raise PromQLError(f"очікувалось {val!r}, знайдено {v!r}")

    def parse(self):
        node = self.expr(0)
        if self.i != len(self.t):
            raise PromQLError(f"зайві символи: {self.peek()[1]!r}")
        return node

    def expr(self, level):
        if level >= len(PREC):
            return self.unary()
        left = self.expr(level + 1)
        while True:
            k, v = self.peek()
            if v in PREC[level] and k in ("op", "id"):
                self.take()
                bool_mod, on, ignoring = False, None, None
                if self.peek()[1] == "bool":
                    self.take(); bool_mod = True
                if self.peek()[1] in ("on", "ignoring") and self.peek(1)[1] == "(":
                    which = self.take()[1]
                    labels = self.label_list()
                    on, ignoring = (labels, None) if which == "on" else (None, labels)
                right = self.expr(level + 1) if v != "^" else self.expr(level)
                left = ("bin", v, left, right, bool_mod, on, ignoring)
            else:
                return left

    def label_list(self):
        self.expect("(")
        out = []
        while self.peek()[1] != ")":
            out.append(self.take()[1])
            if self.peek()[1] == ",":
                self.take()
        self.expect(")")
        return out

    def unary(self):
        k, v = self.peek()
        if v == "-":
            self.take()
            return ("neg", self.unary())
        if v == "+":
            self.take()
            return self.unary()
        return self.postfix()

    def postfix(self):
        node = self.primary()
        while self.peek()[0] == "dur":
            raw = self.take()[1]
            node = ("range", node, parse_duration(raw[1:-1].strip()))
        return node

    def primary(self):
        k, v = self.take()
        if k == "num":
            return ("num", float(v))
        if v == "(":
            node = self.expr(0)
            self.expect(")")
            return ("paren", node)
        if k == "op" and v == "{":
            raise PromQLError("селектор без імені потрібно починати з імені метрики")
        if k != "id":
            raise PromQLError(f"неочікуваний елемент {v!r}")
        if v in AGG:
            return self.aggregation(v)
        if v in FUNCS and self.peek()[1] == "(":
            self.take()
            args = []
            while self.peek()[1] != ")":
                args.append(self.expr(0))
                if self.peek()[1] == ",":
                    self.take()
            self.expect(")")
            return ("call", v, args)
        if v in ("inf", "Inf", "NaN", "nan"):
            return ("num", float(v))
        return self.selector(v)

    def aggregation(self, op):
        by = without = None
        if self.peek()[1] in ("by", "without"):
            which = self.take()[1]
            labels = self.label_list()
            by, without = (labels, None) if which == "by" else (None, labels)
        self.expect("(")
        param = None
        if op in ("topk", "bottomk"):
            param = self.expr(0)
            self.expect(",")
        arg = self.expr(0)
        self.expect(")")
        if self.peek()[1] in ("by", "without") and by is None and without is None:
            which = self.take()[1]
            labels = self.label_list()
            by, without = (labels, None) if which == "by" else (None, labels)
        return ("agg", op, param, arg, by, without)

    def selector(self, name):
        matchers = [("__name__", "=", name)]
        if self.peek()[1] == "{":
            self.take()
            while self.peek()[1] != "}":
                lab = self.take()[1]
                op = self.take()[1]
                k, s = self.take()
                if k != "str":
                    raise PromQLError("значення мітки має бути рядком")
                matchers.append((lab, op, _unquote(s)))
                if self.peek()[1] == ",":
                    self.take()
            self.expect("}")
        if self.peek()[1] == "offset":
            raise PromQLError("offset у лабораторній не підтримується")
        return ("sel", matchers)


def _unquote(s):
    if s[0] == "`":
        return s[1:-1]
    return bytes(s[1:-1], "utf-8").decode("unicode_escape").encode("latin-1").decode("utf-8") if "\\" in s else s[1:-1]


def parse_promql(text):
    return _Parser(text).parse()


def selectors(node):
    """Усі селектори вираження (для перевірки, що запит використовує потрібні метрики)."""
    out = []
    if isinstance(node, tuple):
        if node and node[0] == "sel":
            out.append(node[1])
        else:
            for x in node[1:]:
                out.extend(selectors(x) if isinstance(x, (tuple, list)) else [])
    elif isinstance(node, list):
        for x in node:
            out.extend(selectors(x))
    return out


def metric_names(text):
    return sorted({m[2] for sel in selectors(parse_promql(text)) for m in sel if m[0] == "__name__"})


def functions_used(text):
    found = set()

    def walk(n):
        if isinstance(n, tuple):
            if n and n[0] == "call":
                found.add(n[1])
            elif n and n[0] == "agg":
                found.add(n[1])
            for x in n[1:]:
                walk(x)
        elif isinstance(n, list):
            for x in n:
                walk(x)
    walk(parse_promql(text))
    return found


class Store:
    """Набір рядів: series = [(мітки_словником, [значення...])], вибірки беруться з кроком step від часу 0."""

    def __init__(self, series, step=15.0):
        self.series = []
        for labels, values in series:
            samples = [(i * step, float(v)) for i, v in enumerate(values) if v is not None]
            self.series.append((tuple(sorted(labels.items())), samples))


def _match(matchers, labels):
    d = dict(labels)
    for name, op, val in matchers:
        actual = d.get(name, "")
        if op == "=" and actual != val:
            return False
        if op == "!=" and actual == val:
            return False
        if op == "=~" and not re.fullmatch(val, actual):
            return False
        if op == "!~" and re.fullmatch(val, actual):
            return False
    return True


def _extrapolated(samples, t, rng, counter, rate):
    pts = [(ts, v) for ts, v in samples if t - rng < ts <= t]
    if len(pts) < 2:
        return None
    first, last = pts[0], pts[-1]
    result = last[1] - first[1]
    if counter:
        prev = pts[0][1]
        for _, v in pts[1:]:
            if v < prev:
                result += prev
            prev = v
    d_start = first[0] - (t - rng)
    d_end = t - last[0]
    sampled = last[0] - first[0]
    avg = sampled / (len(pts) - 1)
    if counter and result > 0 and first[1] >= 0:
        d_zero = sampled * (first[1] / result)
        if d_zero < d_start:
            d_start = d_zero
    thr = avg * 1.1
    ext = sampled
    ext += d_start if d_start < thr else avg / 2
    ext += d_end if d_end < thr else avg / 2
    result *= ext / sampled
    if rate:
        result /= rng
    return result


def _linreg(pts, t, ahead):
    n = len(pts)
    sx = sy = sxy = sxx = 0.0
    for ts, v in pts:
        x = ts - t
        sx += x; sy += v; sxy += x * v; sxx += x * x
    cov = sxy - sx * sy / n
    var = sxx - sx * sx / n
    slope = cov / var
    intercept = sy / n - slope * sx / n
    return slope * ahead + intercept


class Engine:
    def __init__(self, store):
        self.store = store

    def query(self, text, t):
        """Повертає скаляр (float) або словник {frozenset(міток без __name__): значення}."""
        res = self.ev(parse_promql(text), float(t))
        if isinstance(res, dict):
            return {frozenset((k, v) for k, v in lab if k != "__name__"): val for lab, val in res.items()}
        return res

    # --- обчислення; вектор = {tuple(sorted(labels)): value}
    def ev(self, n, t):
        kind = n[0]
        if kind == "num":
            return n[1]
        if kind == "paren":
            return self.ev(n[1], t)
        if kind == "neg":
            return self.unop(self.ev(n[1], t))
        if kind == "sel":
            out = {}
            for lab, samples in self.store.series:
                if _match(n[1], lab):
                    cand = [(ts, v) for ts, v in samples if t - LOOKBACK < ts <= t]
                    if cand:
                        out[lab] = cand[-1][1]
            return out
        if kind == "range":
            raise PromQLError("діапазонний вектор можна використовувати лише у функції")
        if kind == "call":
            return self.call(n, t)
        if kind == "agg":
            return self.agg(n, t)
        if kind == "bin":
            return self.binop(n, t)
        raise PromQLError(f"невідомий вузол {kind}")

    @staticmethod
    def unop(v):
        return -v if not isinstance(v, dict) else {k: -x for k, x in v.items()}

    def rangevec(self, node, t):
        if node[0] != "range":
            raise PromQLError("функція очікує діапазонний вектор, наприклад metric[5m]")
        sel, rng = node[1], node[2]
        if sel[0] != "sel":
            raise PromQLError("діапазон підтримується лише для селектора")
        return [(lab, samples) for lab, samples in self.store.series if _match(sel[1], lab)], rng

    def call(self, n, t):
        name, args = n[1], n[2]
        if name == "time":
            return t
        if name in ("abs", "ceil", "floor", "sqrt", "round"):
            fn = {"abs": abs, "ceil": math.ceil, "floor": math.floor, "sqrt": math.sqrt,
                  "round": lambda x: math.floor(x + 0.5)}[name]
            v = self.ev(args[0], t)
            return fn(v) if not isinstance(v, dict) else {k: fn(x) for k, x in v.items()}
        if name in ("clamp_min", "clamp_max"):
            v = self.ev(args[0], t)
            lim = self.ev(args[1], t)
            fn = max if name == "clamp_min" else min
            return {k: fn(x, lim) for k, x in v.items()}
        if name == "vector":
            return {(): self.ev(args[0], t)}
        if name == "scalar":
            v = self.ev(args[0], t)
            return next(iter(v.values())) if len(v) == 1 else float("nan")
        series, rng = self.rangevec(args[0], t)
        out = {}
        for lab, samples in series:
            pts = [(ts, v) for ts, v in samples if t - rng < ts <= t]
            key = tuple(x for x in lab if x[0] != "__name__")
            val = None
            if name in ("rate", "increase"):
                val = _extrapolated(samples, t, rng, True, name == "rate")
            elif name == "delta":
                val = _extrapolated(samples, t, rng, False, False)
            elif name == "irate" and len(pts) >= 2:
                (t1, v1), (t2, v2) = pts[-2], pts[-1]
                val = (v2 if v2 < v1 else v2 - v1) / (t2 - t1)
            elif name == "changes" and pts:
                val = float(sum(1 for a, b in zip(pts, pts[1:]) if a[1] != b[1]))
            elif name == "resets" and pts:
                val = float(sum(1 for a, b in zip(pts, pts[1:]) if b[1] < a[1]))
            elif name == "avg_over_time" and pts:
                val = sum(v for _, v in pts) / len(pts)
            elif name == "min_over_time" and pts:
                val = min(v for _, v in pts)
            elif name == "max_over_time" and pts:
                val = max(v for _, v in pts)
            elif name == "sum_over_time" and pts:
                val = sum(v for _, v in pts)
            elif name == "count_over_time" and pts:
                val = float(len(pts))
            elif name == "predict_linear" and len(pts) >= 2:
                val = _linreg(pts, t, self.ev(args[1], t))
            if val is not None:
                out[key] = val
        return out

    def agg(self, n, t):
        _, op, param, arg, by, without = n
        vec = self.ev(arg, t)
        if not isinstance(vec, dict):
            raise PromQLError("агрегація очікує вектор")
        groups = {}
        for lab, val in vec.items():
            d = dict(lab)
            if by is not None:
                key = tuple(sorted((k, v) for k, v in d.items() if k in by))
            elif without is not None:
                key = tuple(sorted((k, v) for k, v in d.items() if k not in without and k != "__name__"))
            else:
                key = ()
            groups.setdefault(key, []).append((lab, val))
        out = {}
        if op in ("topk", "bottomk"):
            k = int(self.ev(param, t))
            for key, items in groups.items():
                items.sort(key=lambda x: x[1], reverse=(op == "topk"))
                for lab, val in items[:k]:
                    out[lab] = val
            return out
        for key, items in groups.items():
            vals = [v for _, v in items]
            out[key] = {"sum": sum(vals), "avg": sum(vals) / len(vals), "min": min(vals), "max": max(vals),
                        "count": float(len(vals)), "group": 1.0}[op]
        return out

    def binop(self, n, t):
        _, op, l, r, bool_mod, on, ignoring = n
        a, b = self.ev(l, t), self.ev(r, t)
        if op in SET_OPS:
            return self.setop(op, a, b, on, ignoring)
        ar = {"+": lambda x, y: x + y, "-": lambda x, y: x - y, "*": lambda x, y: x * y,
              "/": lambda x, y: x / y if y else (math.nan if x == 0 else math.copysign(math.inf, x)),
              "%": lambda x, y: math.fmod(x, y) if y else math.nan, "^": lambda x, y: x ** y}
        cmp_ = {"==": lambda x, y: x == y, "!=": lambda x, y: x != y, "<": lambda x, y: x < y,
                ">": lambda x, y: x > y, "<=": lambda x, y: x <= y, ">=": lambda x, y: x >= y}
        if not isinstance(a, dict) and not isinstance(b, dict):
            if op in cmp_:
                if not bool_mod:
                    raise PromQLError("порівняння двох скалярів потребує bool")
                return float(cmp_[op](a, b))
            return ar[op](a, b)

        def apply(x, y):
            if op in ar:
                return ar[op](x, y)
            ok = cmp_[op](x, y)
            return float(ok) if bool_mod else (x if ok else None)

        out = {}
        if isinstance(a, dict) and not isinstance(b, dict):
            for k, x in a.items():
                v = apply(x, b)
                if v is not None:
                    out[self._drop(k, op in ar or bool_mod)] = v
            return out
        if isinstance(b, dict) and not isinstance(a, dict):
            for k, y in b.items():
                v = apply(a, y)
                if v is not None:
                    out[self._drop(k, op in ar or bool_mod)] = v
            return out
        index = {}
        for k, y in b.items():
            index.setdefault(self._sig(k, on, ignoring), []).append((k, y))
        for k, x in a.items():
            for _, y in index.get(self._sig(k, on, ignoring), [])[:1]:
                v = apply(x, y)
                if v is not None:
                    key = self._drop(k, op in ar or bool_mod)
                    if on is not None and (op in ar or bool_mod):
                        key = tuple(p for p in key if p[0] in on)
                    out[key] = v
        return out

    @staticmethod
    def _drop(k, drop_name):
        return tuple(p for p in k if p[0] != "__name__") if drop_name else k

    @staticmethod
    def _sig(k, on, ignoring):
        d = {p for p in k if p[0] != "__name__"}
        if on is not None:
            return frozenset(p for p in d if p[0] in on)
        if ignoring is not None:
            return frozenset(p for p in d if p[0] not in ignoring)
        return frozenset(d)

    def setop(self, op, a, b, on, ignoring):
        sigs = {self._sig(k, on, ignoring) for k in b}
        if op == "and":
            return {k: v for k, v in a.items() if self._sig(k, on, ignoring) in sigs}
        if op == "unless":
            return {k: v for k, v in a.items() if self._sig(k, on, ignoring) not in sigs}
        out = dict(a)
        asigs = {self._sig(k, on, ignoring) for k in a}
        out.update({k: v for k, v in b.items() if self._sig(k, on, ignoring) not in asigs})
        return out


def alert_states(expr, series, step, eval_interval, for_seconds, end, keep_firing=0.0):
    """Імітація життєвого циклу сповіщення: повертає список (час, стан) із станами inactive, pending, firing
    для кожного моменту перевірки від 0 до end включно (для одного ряду результату)."""
    eng = Engine(Store(series, step))
    states, pending_since, last_true = [], None, None
    t = 0.0
    while t <= end + 1e-9:
        active = bool(eng.query(expr, t))
        if active:
            last_true = t
            if pending_since is None:
                pending_since = t
            st = "firing" if t - pending_since >= for_seconds else "pending"
        elif pending_since is not None and last_true is not None and t - last_true <= keep_firing and \
                t - pending_since >= for_seconds:
            st = "firing"
        else:
            pending_since = None
            st = "inactive"
        states.append((t, st))
        t += eval_interval
    return states


# ======================================================================================
# Relabeling (підмножина Prometheus)
# ======================================================================================
def _expand(repl, m):
    def sub(mm):
        key = mm.group(1) or mm.group(2)
        try:
            return m.group(int(key)) or "" if key.isdigit() else m.group(key) or ""
        except (IndexError, error_type):
            return ""
    return re.sub(r"\$(?:(\w+)|\{(\w+)\})", sub, repl)


error_type = re.error


def relabel(labels, configs):
    """Застосовує список правил relabel до словника міток. Повертає новий словник або None, якщо ціль відкинуто."""
    labels = dict(labels)
    for c in configs:
        action = c.get("action", "replace")
        sources = c.get("source_labels", [])
        sep = c.get("separator", ";")
        value = sep.join(labels.get(s, "") for s in sources)
        rx = re.compile("^(?:" + c.get("regex", "(.*)") + ")$", re.S)
        if action == "replace":
            m = rx.match(value)
            if not m:
                continue
            target = _expand(c["target_label"], m)
            val = _expand(c.get("replacement", "$1"), m)
            if val == "":
                labels.pop(target, None)
            else:
                labels[target] = val
        elif action == "keep":
            if not rx.match(value):
                return None
        elif action == "drop":
            if rx.match(value):
                return None
        elif action == "labelmap":
            for k, v in list(labels.items()):
                m = rx.match(k)
                if m:
                    labels[_expand(c.get("replacement", "$1"), m)] = v
        elif action == "labeldrop":
            labels = {k: v for k, v in labels.items() if not rx.match(k)}
        elif action == "labelkeep":
            labels = {k: v for k, v in labels.items() if rx.match(k)}
        elif action == "lowercase":
            labels[c["target_label"]] = value.lower()
        elif action == "uppercase":
            labels[c["target_label"]] = value.upper()
        else:
            raise ValueError(f"дія {action!r} у лабораторній не підтримується")
    return labels


# ======================================================================================
# LogQL (підмножина)
# ======================================================================================
class LogQLError(Exception):
    pass


_LTOK = re.compile(r"""\s*(?:
    (?P<str>"(?:\\.|[^"\\])*"|`[^`]*`)|
    (?P<dur>\[\s*(?:\d+(?:ms|s|m|h|d|w))+\s*\])|
    (?P<num>\d+(?:\.\d+)?(?:ms|us|µs|ns|s|m|h|d)*)|
    (?P<id>[A-Za-z_][A-Za-z0-9_.]*)|
    (?P<op>\|=|\|~|!=|!~|==|=~|>=|<=|[|=<>(){},-])
    )""", re.X)


def _ltokens(text):
    pos, out = 0, []
    text = text.strip()
    while pos < len(text):
        m = _LTOK.match(text, pos)
        if not m or m.end() == pos:
            raise LogQLError(f"неочікуваний символ: {text[pos:pos + 10]!r}")
        pos = m.end()
        out.append((m.lastgroup, m.group(m.lastgroup)))
        while pos < len(text) and text[pos].isspace():
            pos += 1
    return out


def _lunq(s):
    if s[0] == "`":
        return s[1:-1]
    return re.sub(r"\\(.)", lambda m: {"n": "\n", "t": "\t"}.get(m.group(1), m.group(1)), s[1:-1])


def _unit_value(text):
    """'500ms' -> 0.5, '2s' -> 2.0, '15' -> 15.0 (тривалості переводяться в секунди)."""
    m = re.fullmatch(r"(\d+(?:\.\d+)?)((?:ms|us|µs|ns|s|m|h|d)*)", text)
    if not m:
        raise LogQLError(f"некоректне число: {text!r}")
    if not m.group(2):
        return float(m.group(1))
    units = {"ns": 1e-9, "us": 1e-6, "µs": 1e-6, "ms": 1e-3, "s": 1, "m": 60, "h": 3600, "d": 86400}
    parts = re.findall(r"(\d+(?:\.\d+)?)(ms|us|µs|ns|s|m|h|d)", text)
    return sum(float(a) * units[b] for a, b in parts)


def parse_logql(text):
    t = _ltokens(text)
    pos = [0]

    def peek(k=0):
        return t[pos[0] + k] if pos[0] + k < len(t) else (None, None)

    def take():
        tok = peek()
        pos[0] += 1
        return tok

    def expect(v):
        if take()[1] != v:
            raise LogQLError(f"очікувалось {v!r}")

    def labels():
        expect("{")
        ms = []
        while peek()[1] != "}":
            name = take()[1]
            op = take()[1]
            k, s = take()
            if k != "str":
                raise LogQLError("значення мітки має бути рядком")
            ms.append((name, op, _lunq(s)))
            if peek()[1] == ",":
                take()
        expect("}")
        return ms

    def pipeline():
        stages = []
        while True:
            k, v = peek()
            if v in ("|=", "!=", "|~", "!~") and k == "op":
                take()
                k2, s = take()
                if k2 != "str":
                    raise LogQLError("після фільтра рядка має бути рядок")
                stages.append(("line", v, _lunq(s)))
            elif v == "|" and k == "op":
                take()
                k2, name = take()
                if name in ("json", "logfmt"):
                    stages.append((name,))
                elif k2 == "id":
                    op = take()[1]
                    k3, val = take()
                    if k3 == "str":
                        stages.append(("lfilter", name, op, _lunq(val), "str"))
                    else:
                        stages.append(("lfilter", name, op, _unit_value(val), "num"))
                else:
                    raise LogQLError(f"невідома стадія конвеєра: {name!r}")
            else:
                return stages

    def expr():
        k, v = peek()
        if v == "{":
            sel = labels()
            return ("logs", sel, pipeline())
        if k == "id" and v in ("rate", "count_over_time", "bytes_over_time", "bytes_rate"):
            take(); expect("(")
            inner = expr()
            k2, d = take()
            if k2 != "dur":
                raise LogQLError("потрібен діапазон [5m]")
            expect(")")
            return ("mfn", v, inner, parse_duration(d[1:-1].strip()))
        if k == "id" and v in ("sum", "count", "max", "min", "avg", "topk"):
            take()
            by = None
            if peek()[1] in ("by", "without"):
                which = take()[1]
                expect("(")
                by = [take()[1]]
                while peek()[1] == ",":
                    take(); by.append(take()[1])
                expect(")")
                by = (which, by)
            expect("(")
            param = None
            if v == "topk":
                param = float(take()[1]); expect(",")
            inner = expr()
            expect(")")
            if peek()[1] in ("by", "without") and by is None:
                which = take()[1]
                expect("(")
                lst = [take()[1]]
                while peek()[1] == ",":
                    take(); lst.append(take()[1])
                expect(")")
                by = (which, lst)
            return ("magg", v, param, inner, by)
        raise LogQLError(f"неочікуваний елемент: {v!r}")

    node = expr()
    if pos[0] != len(t):
        raise LogQLError(f"зайві символи: {peek()[1]!r}")
    return node


def _parse_line(line, kind):
    if kind == "json":
        import json
        try:
            d = json.loads(line)
        except ValueError:
            return {"__error__": "JSONParserErr"}
        out = {}

        def flat(prefix, obj):
            for k, v in obj.items():
                key = f"{prefix}_{k}" if prefix else k
                if isinstance(v, dict):
                    flat(key, v)
                else:
                    out[key] = str(v).lower() if isinstance(v, bool) else str(v)
        if isinstance(d, dict):
            flat("", d)
        return out
    out = {}
    for m in re.finditer(r'(\w+)=("(?:\\.|[^"\\])*"|\S*)', line):
        v = m.group(2)
        out[m.group(1)] = v[1:-1] if v.startswith('"') else v
    return out


def _lmatch(ms, labels):
    for name, op, val in ms:
        actual = labels.get(name, "")
        if op == "=" and actual != val:
            return False
        if op == "!=" and actual == val:
            return False
        if op == "=~" and not re.fullmatch(val, actual):
            return False
        if op == "!~" and re.fullmatch(val, actual):
            return False
    return True


def _run_pipeline(stages, line, labels):
    labels = dict(labels)
    for st in stages:
        if st[0] == "line":
            _, op, s = st
            ok = (s in line) if op == "|=" else (s not in line) if op == "!=" else \
                bool(re.search(s, line)) if op == "|~" else not re.search(s, line)
            if not ok:
                return None
        elif st[0] in ("json", "logfmt"):
            labels.update(_parse_line(line, st[0]))
        else:
            _, name, op, val, kind = st
            actual = labels.get(name)
            if kind == "str":
                a = actual if actual is not None else ""
                ok = {"=": a == val, "==": a == val, "!=": a != val,
                      "=~": bool(re.fullmatch(val, a)), "!~": not re.fullmatch(val, a)}.get(op)
                if ok is None:
                    return None
            else:
                try:
                    a = _unit_value(actual)
                except (LogQLError, TypeError):
                    return None
                ok = {"=": a == val, "==": a == val, "!=": a != val, ">": a > val, ">=": a >= val,
                      "<": a < val, "<=": a <= val}[op]
            if not ok:
                return None
    return labels


class LogEngine:
    """entries = [(час_с, {мітки потоку}, 'рядок')]. query повертає список рядків (журнальний запит)
    або словник {frozenset(міток): число} (метричний запит) на момент t."""

    def __init__(self, entries):
        self.entries = sorted(entries, key=lambda e: e[0])

    def _stream(self, node, lo, hi):
        _, sel, stages = node
        out = []
        for ts, lab, line in self.entries:
            if lo < ts <= hi and _lmatch(sel, lab):
                res = _run_pipeline(stages, line, lab)
                if res is not None:
                    out.append((ts, res, line))
        return out

    def query(self, text, t=None, start=0.0):
        node = parse_logql(text)
        if node[0] == "logs":
            t = float("inf") if t is None else t
            return [line for _, _, line in self._stream(node, start - 1e-9, t)]
        return self._metric(node, t)

    def _metric(self, node, t):
        if node[0] == "mfn":
            _, fn, inner, rng = node
            groups = {}
            for ts, lab, line in self._stream(inner, t - rng, t):
                key = frozenset((k, v) for k, v in lab.items() if not k.startswith("__"))
                groups.setdefault(key, []).append(line)
            out = {}
            for key, lines in groups.items():
                if fn == "count_over_time":
                    out[key] = float(len(lines))
                elif fn == "rate":
                    out[key] = len(lines) / rng
                elif fn == "bytes_over_time":
                    out[key] = float(sum(len(x.encode()) for x in lines))
                else:
                    out[key] = sum(len(x.encode()) for x in lines) / rng
            return out
        _, op, param, inner, by = node
        vec = self._metric(inner, t)
        groups = {}
        for key, val in vec.items():
            d = dict(key)
            if by is None:
                g = frozenset()
            elif by[0] == "by":
                g = frozenset((k, v) for k, v in d.items() if k in by[1])
            else:
                g = frozenset((k, v) for k, v in d.items() if k not in by[1])
            groups.setdefault(g, []).append((key, val))
        out = {}
        if op == "topk":
            items = sorted(((k, v) for it in groups.values() for k, v in it), key=lambda x: -x[1])
            return dict(items[:int(param)])
        for g, items in groups.items():
            vals = [v for _, v in items]
            out[g] = {"sum": sum(vals), "count": float(len(vals)), "max": max(vals), "min": min(vals),
                      "avg": sum(vals) / len(vals)}[op]
        return out


# ======================================================================================
# Мінімальний розбирач синтаксису Alloy (River)
# ======================================================================================
class AlloyError(Exception):
    pass


_ATOK = re.compile(r"""\s*(?:
    (?P<comment>//[^\n]*|/\*.*?\*/)|
    (?P<str>"(?:\\.|[^"\\])*"|`[^`]*`)|
    (?P<num>-?\d+(?:\.\d+)?)|
    (?P<id>[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)|
    (?P<op>[{}\[\]=,()])
    )""", re.X | re.S)


class Ref(str):
    """Посилання на експорт компонента, наприклад loki.write.default.receiver."""


def parse_alloy(text):
    """Повертає список блоків: {"type": "loki.write", "label": "default", "attrs": {...}, "blocks": [...]}."""
    toks, pos = [], 0
    text = text.strip()
    while pos < len(text):
        m = _ATOK.match(text, pos)
        if not m or m.end() == pos:
            raise AlloyError(f"неочікуваний символ: {text[pos:pos + 15]!r}")
        pos = m.end()
        if m.lastgroup != "comment":
            toks.append((m.lastgroup, m.group(m.lastgroup)))
        while pos < len(text) and text[pos].isspace():
            pos += 1
    i = [0]

    def peek(k=0):
        return toks[i[0] + k] if i[0] + k < len(toks) else (None, None)

    def take():
        tok = peek(); i[0] += 1; return tok

    def value():
        k, v = take()
        if k == "str":
            return _lunq(v)
        if k == "num":
            return float(v) if "." in v else int(v)
        if k == "id":
            if v in ("true", "false"):
                return v == "true"
            if v == "null":
                return None
            return Ref(v)
        if v == "[":
            arr = []
            while peek()[1] != "]":
                arr.append(value())
                if peek()[1] == ",":
                    take()
            take()
            return arr
        if v == "{":
            obj = {}
            while peek()[1] != "}":
                k2, key = take()
                key = _lunq(key) if k2 == "str" else key
                if take()[1] != "=":
                    raise AlloyError("очікувалось '=' в об'єкті")
                obj[key] = value()
                if peek()[1] == ",":
                    take()
            take()
            return obj
        raise AlloyError(f"неочікуваний елемент {v!r}")

    def body(closing):
        attrs, blocks = {}, []
        while peek()[1] != closing:
            k, name = take()
            if k is None:
                raise AlloyError("несподіваний кінець файла")
            if k != "id":
                raise AlloyError(f"очікувалось ім'я, знайдено {name!r}")
            if peek()[1] == "=":
                take()
                attrs[name] = value()
            else:
                label = None
                if peek()[0] == "str":
                    label = _lunq(take()[1])
                if take()[1] != "{":
                    raise AlloyError(f"очікувалось '{{' після {name}")
                a, b = body("}")
                take()
                blocks.append({"type": name, "label": label, "attrs": a, "blocks": b})
        return attrs, blocks
    attrs, blocks = body(None)
    if attrs:
        raise AlloyError("атрибути поза блоками не допускаються")
    return blocks
