"""Допоміжний код тестів: набори даних (ряди метрик, журнали) і драйвери задач.

Драйвер викликає вашу функцію й перетворює результат на просту структуру (словник, список), яку тест порівнює з
очікуваною. Помилки подаються кортежем ("!Клас", "повідомлення"). Файл не змінюйте.
"""
import json

import yaml
from conftest import load  # noqa: F401
import obs

STEP = 15.0


def safe(fn, *args):
    try:
        return fn(*args)
    except Exception as exc:  # noqa: BLE001
        return ("!" + type(exc).__name__, str(exc))


def is_err(x):
    return isinstance(x, tuple) and len(x) == 2 and isinstance(x[0], str) and x[0].startswith("!")


def parse_yaml(text):
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        return ("!YAMLError", str(exc)[:80])
    return data


# ----------------------------------------------------------------------------- Задача 1, 5, 7: YAML-конфігурації


def d_yaml(mod, func, arg):
    """Викликає mod.<func>(arg) і розбирає отриманий текст як YAML."""
    text = safe(getattr(mod, func), arg)
    return text if is_err(text) else parse_yaml(text)


# ----------------------------------------------------------------------------- Задача 2: relabel


def d_relabel(mod, params, inputs):
    text = safe(mod.build_relabel_configs, params)
    if is_err(text):
        return text
    data = parse_yaml(text)
    if is_err(data) or not isinstance(data, dict):
        return ("!Формат", "результат має бути YAML-словником")
    extra = set(data) - {"relabel_configs", "metric_relabel_configs"}
    if extra:
        return ("!Формат", f"зайві ключі: {sorted(extra)}")
    series_mode = params["scenario"] == "trim"
    key = "metric_relabel_configs" if series_mode else "relabel_configs"
    other = "relabel_configs" if series_mode else "metric_relabel_configs"
    if data.get(other):
        return ("!Формат", f"сценарій {params['scenario']} не має використовувати {other}")
    rules = data.get(key) or []
    out = []
    for labels in inputs:
        try:
            res = obs.relabel(labels, rules)
        except Exception as exc:  # noqa: BLE001
            return ("!" + type(exc).__name__, str(exc))
        if res is None:
            out.append(None)
        elif series_mode:
            out.append(res)
        else:
            out.append({"address": res.get("__address__"),
                        "labels": {k: v for k, v in res.items() if not k.startswith("__")}})
    return out


# ----------------------------------------------------------------------------- Задача 3: PromQL


def _lin(n, f):
    return [f(k) for k in range(n)]


def datasets():
    """Іменовані набори рядів: назва -> (ряди, крок у секундах)."""
    n = 41

    def ctr(a_before, a_after):
        return _lin(n, lambda k: a_before * k if k <= 20 else a_before * 20 + a_after * (k - 20))

    host = []
    for inst, cpus in (("a", [(12, 6), (9, 3)]), ("b", [(3, 3)])):
        for i, (x, y) in enumerate(cpus):
            host.append(({"__name__": "node_cpu_seconds_total", "instance": inst, "cpu": str(i), "mode": "idle"},
                         ctr(x, y)))
            host.append(({"__name__": "node_cpu_seconds_total", "instance": inst, "cpu": str(i), "mode": "user"},
                         _lin(n, lambda k: 2 * k)))
    for inst, tot, av in (("a", 8e9, 2e9), ("b", 4e9, 3e9)):
        host.append(({"__name__": "node_memory_MemTotal_bytes", "instance": inst}, [tot] * n))
        host.append(({"__name__": "node_memory_MemAvailable_bytes", "instance": inst}, [av] * n))
    for inst, mp, size, avail in (("a", "/", 100e9, 40e9), ("a", "/data", 200e9, 150e9), ("b", "/", 50e9, 45e9)):
        lab = {"instance": inst, "mountpoint": mp, "device": "sda1" if mp == "/" else "sdb1", "fstype": "ext4"}
        host.append(({"__name__": "node_filesystem_size_bytes", **lab}, [size] * n))
        host.append(({"__name__": "node_filesystem_avail_bytes", **lab}, [avail] * n))
    for inst, dev, inc in (("a", "eth0", 1500), ("a", "lo", 15000), ("b", "eth0", 300)):
        host.append(({"__name__": "node_network_receive_bytes_total", "instance": inst, "device": dev},
                     _lin(n, lambda k: inc * k)))
    host.append(({"__name__": "node_load1", "instance": "a"}, [1.5] * n))
    host.append(({"__name__": "node_load1", "instance": "b"}, [0.6] * n))

    m = 121
    trend = []
    for inst, boot in (("a", 3600), ("b", 0)):
        trend.append(({"__name__": "node_boot_time_seconds", "instance": inst}, [boot] * m))
    trend.append(({"__name__": "node_filesystem_avail_bytes", "instance": "a", "mountpoint": "/"},
                  _lin(m, lambda k: 300e9 - 1e9 * k)))
    trend.append(({"__name__": "node_filesystem_avail_bytes", "instance": "b", "mountpoint": "/"},
                  _lin(m, lambda k: 300e9 - 0.1e9 * k)))
    trend.append(({"__name__": "node_filesystem_avail_bytes", "instance": "a", "mountpoint": "/data"},
                  _lin(m, lambda k: 50e9 - 0.4e9 * k)))
    trend.append(({"__name__": "node_load1", "instance": "a"}, _lin(m, lambda k: float(k % 4))))
    trend.append(({"__name__": "node_load1", "instance": "b"}, [0.5] * m))
    for job, inst, val in (("node", "a", 1), ("node", "b", 0), ("app", "c", 0), ("app", "d", 0), ("prom", "e", 1)):
        trend.append(({"__name__": "up", "job": job, "instance": inst}, [val] * m))

    app = []
    for inst, path, code, inc in (("s1", "/", "200", 60), ("s1", "/pay", "200", 30), ("s1", "/pay", "500", 6),
                                  ("s1", "/orders", "200", 12), ("s1", "/health", "200", 1), ("s2", "/", "200", 30)):
        app.append(({"__name__": "http_requests_total", "instance": inst, "path": path, "code": code},
                    _lin(m, lambda k: inc * k)))
    app.append(({"__name__": "http_requests_in_flight", "instance": "s1"}, _lin(m, lambda k: float(k % 7))))
    app.append(({"__name__": "http_requests_in_flight", "instance": "s2"}, [2.0] * m))
    app.append(({"__name__": "process_start_time_seconds", "instance": "s1"}, _lin(m, lambda k: 1000 if k < 50 else 2000)))
    app.append(({"__name__": "process_start_time_seconds", "instance": "s2"}, [1500] * m))
    app.append(({"__name__": "process_resident_memory_bytes", "instance": "s1"}, _lin(m, lambda k: 1e8 + 1e6 * k)))
    app.append(({"__name__": "process_resident_memory_bytes", "instance": "s2"}, _lin(m, lambda k: 5e8 - 2e6 * k)))

    # сповіщення: крок 15 с, 81 вибірка (до 1200 с)
    k5 = 81
    alerts = [
        ({"__name__": "up", "job": "node", "instance": "a"}, _lin(k5, lambda k: 0 if 20 <= k < 60 else 1)),
        ({"__name__": "up", "job": "shop", "instance": "s"}, [1] * k5),
        ({"__name__": "node_cpu_seconds_total", "instance": "a", "cpu": "0", "mode": "idle"},
         _lin(k5, lambda k: 10 * k if k <= 20 else 200 + 1 * (k - 20) if k <= 60 else 240 + 10 * (k - 60))),
        ({"__name__": "node_filesystem_avail_bytes", "instance": "a", "mountpoint": "/"},
         _lin(k5, lambda k: 30e9 if k < 40 else 8e9)),
        ({"__name__": "node_filesystem_size_bytes", "instance": "a", "mountpoint": "/"}, [100e9] * k5),
        ({"__name__": "http_requests_total", "job": "shop", "instance": "s", "code": "200"}, _lin(k5, lambda k: 15 * k)),
        ({"__name__": "http_requests_total", "job": "shop", "instance": "s", "code": "500"}, _lin(k5, lambda k: 3 * k)),
        ({"__name__": "http_requests_total", "job": "api", "instance": "x", "code": "200"}, _lin(k5, lambda k: 1 * k)),
    ]
    return {"host": (host, 15.0), "trend": (trend, 60.0), "app": (app, 60.0), "alerts": (alerts, 15.0)}


DATASETS = datasets()


def d_promql(mod, params, dataset, key, t):
    """Обчислює запит params -> queries[key] у момент t і повертає відсортований список (мітки, значення)."""
    queries = safe(mod.promql_queries, params)
    if is_err(queries):
        return queries
    if not isinstance(queries, dict) or key not in queries:
        return ("!KeyError", f"немає ключа {key}")
    series, step = DATASETS[dataset]
    try:
        res = obs.Engine(obs.Store(series, step)).query(queries[key], t)
    except Exception as exc:  # noqa: BLE001
        return ("!" + type(exc).__name__, str(exc))
    if not isinstance(res, dict):
        return ("!Тип", "вираз має повертати вектор")
    return sorted(([dict(sorted(k)), v] for k, v in res.items()), key=lambda x: json.dumps(x[0]))


def d_promql_keys(mod, params):
    queries = safe(mod.promql_queries, params)
    return queries if is_err(queries) else sorted(queries)


# ----------------------------------------------------------------------------- Задача 4: правила


def d_rules(mod, spec):
    text = safe(mod.build_rules, spec)
    return text if is_err(text) else parse_yaml(text)


def d_timeline(mod, spec, dataset, alert, end):
    """Життєвий цикл сповіщення alert на наборі даних: список (час, стан) у моменти зміни стану.
    Перші 300 с (розігрів вікон rate) не показуються; перевірка виконується кожні 15 с."""
    data = d_rules(mod, spec)
    if is_err(data):
        return data
    series, step = DATASETS[dataset]
    for group in data["groups"]:
        for rule in group["rules"]:
            if rule.get("alert") == alert:
                hold = obs.parse_duration(rule["for"]) if rule.get("for") else 0.0
                states = obs.alert_states(rule["expr"], series, step, 15.0, hold, end)
                out, last = [], None
                for t, st in states:
                    if t >= 300 and st != last:
                        out.append((t, st))
                        last = st
                return out
    return ("!KeyError", f"сповіщення {alert} не знайдено")


# ----------------------------------------------------------------------------- Задача 6: дашборд


def d_dashboard(mod, spec):
    text = safe(mod.build_dashboard, spec)
    if is_err(text):
        return text
    try:
        d = json.loads(text)
    except ValueError as exc:
        return ("!JSONError", str(exc)[:80])
    out = {"uid": d.get("uid"), "title": d.get("title"), "tags": d.get("tags"), "refresh": d.get("refresh"),
           "time": d.get("time"), "schemaVersion": d.get("schemaVersion"),
           "variables": [(v["name"], v["datasource"]["uid"], v["query"]["query"], v.get("includeAll", False))
                         for v in d.get("templating", {}).get("list", [])], "panels": []}
    for p in d.get("panels", []):
        g = p["gridPos"]
        row = {"id": p["id"], "type": p["type"], "title": p["title"], "pos": [g["x"], g["y"], g["w"], g["h"]]}
        if p["type"] != "row":
            row["ds"] = p["datasource"]["uid"]
            row["targets"] = [(t["refId"], t["expr"], t.get("legendFormat"), t["datasource"]["uid"]) for t in p["targets"]]
            row["unit"] = p["fieldConfig"]["defaults"]["unit"]
            row["steps"] = [(s["value"], s["color"]) for s in p["fieldConfig"]["defaults"]["thresholds"]["steps"]]
        out["panels"].append(row)
    return out


def grid_problems(dashboard_json):
    """Перевірка властивостей розкладки: межі, відсутність перекриттів, унікальні id."""
    d = json.loads(dashboard_json)
    problems, boxes, ids = [], [], set()
    for p in d["panels"]:
        g = p["gridPos"]
        if p["id"] in ids:
            problems.append(f"повторний id {p['id']}")
        ids.add(p["id"])
        if g["x"] < 0 or g["w"] < 1 or g["x"] + g["w"] > 24:
            problems.append(f"панель {p['title']} виходить за ширину 24")
        for (x, y, w, h, t) in boxes:
            if g["x"] < x + w and x < g["x"] + g["w"] and g["y"] < y + h and y < g["y"] + g["h"]:
                problems.append(f"панелі {p['title']} і {t} перекриваються")
        boxes.append((g["x"], g["y"], g["w"], g["h"], p["title"]))
    return problems


# ----------------------------------------------------------------------------- Задача 8: Alloy


def _ref(v):
    return str(v) if isinstance(v, obs.Ref) else v


def d_alloy(mod, spec):
    text = safe(mod.build_alloy_config, spec)
    if is_err(text):
        return text
    try:
        blocks = obs.parse_alloy(text)
    except obs.AlloyError as exc:
        return ("!AlloyError", str(exc))
    by = {(b["type"], b["label"]): b for b in blocks}
    out = {"components": sorted(f"{t}.{l}" for t, l in by), "sources": {}}
    write = by.get(("loki.write", "default"))
    out["write_url"] = write["blocks"][0]["attrs"].get("url") if write and write["blocks"] else None
    for src in spec["sources"]:
        n = src["name"]
        fm, fs, pr = by.get(("local.file_match", n)), by.get(("loki.source.file", n)), by.get(("loki.process", n))
        info = {}
        if fm:
            info["targets"] = [dict(t) for t in fm["attrs"].get("path_targets", [])]
        if fs:
            info["reads_file_match"] = _ref(fs["attrs"].get("targets")) == f"local.file_match.{n}.targets"
            info["to_process"] = [_ref(x) for x in fs["attrs"].get("forward_to", [])] == [f"loki.process.{n}.receiver"]
        if pr:
            info["to_write"] = [_ref(x) for x in pr["attrs"].get("forward_to", [])] == ["loki.write.default.receiver"]
            stages = []
            for b in pr["blocks"]:
                a = b["attrs"]
                if b["type"] == "stage.json":
                    stages.append(("json", dict(a.get("expressions", {}))))
                elif b["type"] == "stage.logfmt":
                    stages.append(("logfmt", dict(a.get("mapping", {}))))
                elif b["type"] == "stage.labels":
                    stages.append(("labels", dict(a.get("values", {}))))
                elif b["type"] == "stage.drop":
                    stages.append(("drop", a.get("source"), a.get("expression")))
                else:
                    stages.append((b["type"],))
            info["stages"] = stages
        out["sources"][n] = info
    return out


# ----------------------------------------------------------------------------- Задача 9: LogQL


def log_entries():
    """Журнали двох застосунків: (час, мітки потоку, рядок). Час у секундах від 0."""
    import json as _j
    e = []

    def add(t, app, env, line):
        e.append((float(t), {"app": app, "env": env}, line))
    add(10, "shop", "prod", "INFO order created id=1")
    add(20, "shop", "prod", "ERROR payment failed: timeout id=2")
    add(30, "shop", "stage", "ERROR healthcheck failed")
    add(40, "shop", "prod", "DEBUG cache miss key=7")
    add(50, "shop", "dev", "ERROR Timeout while calling bank")
    add(60, "auth", "prod", "ERROR bad password user=ann")
    add(70, "shop", "stage", "WARN slow query took 900ms")
    add(80, "shop", "prod", "ERROR disk full")
    add(90, "shop", "prod", "INFO error budget report ready")

    def js(t, app, level, path, status, duration):
        add(t, app, "prod", _j.dumps({"level": level, "path": path, "status": status, "duration": duration}))
    js(100, "shop", "info", "/", 200, "20ms")
    js(110, "shop", "error", "/pay", 500, "1200ms")
    js(120, "shop", "error", "/pay", 502, "300ms")
    js(130, "shop", "warn", "/orders", 200, "650ms")
    js(140, "shop", "info", "/orders", 404, "15ms")
    js(150, "auth", "error", "/login", 500, "800ms")
    js(160, "shop", "error", "/orders", 500, "510ms")
    js(170, "shop", "info", "/pay", 200, "2s")
    add(175, "shop", "prod", "not json at all")
    js(180, "shop", "error", "/pay", 503, "90ms")
    for i, (level, path, status) in enumerate([
            ("info", "/items", 200), ("info", "/items", 200), ("error", "/pay", 500), ("warn", "/items", 429),
            ("info", "/pay", 200), ("error", "/pay", 503), ("info", "/items", 200), ("error", "/items", 500),
            ("error", "/pay", 500), ("info", "/items", 200)]):
        js(100 + 10 * i, "api", level, path, status, f"{20 + i}ms")
    return e


LOGS = log_entries()


def d_logql(mod, params, key, t):
    queries = safe(mod.logql_queries, params)
    if is_err(queries):
        return queries
    if not isinstance(queries, dict) or key not in queries:
        return ("!KeyError", f"немає ключа {key}")
    try:
        res = obs.LogEngine(LOGS).query(queries[key], t)
    except Exception as exc:  # noqa: BLE001
        return ("!" + type(exc).__name__, str(exc))
    if isinstance(res, list):
        index = {line: i for i, (_, _, line) in enumerate(LOGS)}
        return [index.get(x, "?") for x in res]
    return sorted(([dict(sorted(k)), v] for k, v in res.items()), key=lambda x: json.dumps(x[0]))


# ----------------------------------------------------------------------------- Задача 10: compose


def d_compose(mod, spec):
    text = safe(mod.build_compose, spec)
    if is_err(text):
        return text
    data = parse_yaml(text)
    if is_err(data):
        return data
    out = {"name": data.get("name"), "volumes": sorted(data.get("volumes") or {}), "services": {}}
    for name, s in data.get("services", {}).items():
        env = s.get("environment", {})
        if isinstance(env, list):
            env = dict(x.split("=", 1) for x in env)
        out["services"][name] = {
            "image": s.get("image"), "container_name": s.get("container_name"), "restart": s.get("restart"),
            "ports": [str(p) for p in s.get("ports", [])], "command": s.get("command"),
            "volumes": sorted(s.get("volumes", [])), "depends_on": sorted(s.get("depends_on", []) if not isinstance(
                s.get("depends_on"), dict) else s["depends_on"]), "environment": env, "pid": s.get("pid")}
    return out


DRIVERS = {k[2:]: v for k, v in dict(globals()).items() if k.startswith("d_")}
