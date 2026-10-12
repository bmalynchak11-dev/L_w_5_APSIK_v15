"""Перевірка частини Б за файлами: python part_b/check_part_b.py part_b/stack [--service shop] [--live]

Скрипт читає файли стеку (compose.yaml, config/..., metrics_sample.txt) і виводить список невиконаних вимог.
З параметром --live додатково опитує стек, що вже працює (Prometheus на :9090, Grafana на :3000, Loki на :3100;
пароль адміністратора береться зі змінної середовища GRAFANA_ADMIN_PASSWORD).
Повертає код 0, якщо вимог не порушено.
"""
import argparse
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))
import obs  # noqa: E402

INFRA = {"prometheus", "grafana", "loki", "alloy", "node-exporter"}
SEVERITIES = {"page", "ticket", "info"}
RECORD_NAME = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*:[a-zA-Z_][a-zA-Z0-9_]*(:[a-zA-Z_][a-zA-Z0-9_]*)+$")


def _yaml(path, problems, what):
    try:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        problems.append(f"{what}: файл не читається як YAML ({exc})")
        return None
    return data


def _metric_names(sample_text):
    return set(re.findall(r"^([a-zA-Z_:][a-zA-Z0-9_:]*)", re.sub(r"^#.*$", "", sample_text, flags=re.M), flags=re.M))


def check(stack, service=None):
    root = Path(stack)
    problems = []
    if not root.is_dir():
        return [f"немає теки {root}"]
    cfg = root / "config"

    # --- compose.yaml
    comp = _yaml(root / "compose.yaml", problems, "compose.yaml") if (root / "compose.yaml").exists() else None
    if comp is None:
        problems.append("немає compose.yaml")
        comp = {"services": {}}
    services = comp.get("services", {})
    for need in sorted(INFRA - set(services)):
        problems.append(f"compose.yaml: немає служби {need}")
    own = [s for s in services if s not in INFRA]
    if service:
        if service not in services:
            problems.append(f"compose.yaml: немає служби вашого сервісу {service}")
    elif not own:
        problems.append("compose.yaml: немає служби власного сервісу (крім prometheus, grafana, loki, alloy, node-exporter)")
    service = service or (own[0] if own else None)
    declared = set(comp.get("volumes") or {})
    used = set()
    for name, svc in services.items():
        image = str(svc.get("image", ""))
        if image and (":" not in image or image.endswith(":latest")) and name in INFRA:
            problems.append(f"compose.yaml: образ служби {name} має мати конкретний тег, а не latest")
        for v in svc.get("volumes", []):
            src = str(v).split(":")[0]
            if src and not src.startswith((".", "/", "$")):
                used.add(src)
    if used - declared:
        problems.append(f"compose.yaml: томи {sorted(used - declared)} не оголошено в розділі volumes")
    env = services.get("grafana", {}).get("environment", {})
    if isinstance(env, list):
        env = dict(x.split("=", 1) for x in env if "=" in x)
    pw = str(env.get("GF_SECURITY_ADMIN_PASSWORD", ""))
    if not pw.startswith("${"):
        problems.append("compose.yaml: пароль Grafana має братися зі змінної середовища (${ІМ'Я}), а не бути в тексті")
    if str(services.get("grafana", {}).get("depends_on", "")).find("prometheus") < 0:
        problems.append("compose.yaml: grafana має залежати від prometheus (depends_on)")

    # --- зразок метрик
    sample_path = root / "metrics_sample.txt"
    names = set()
    if not sample_path.exists():
        problems.append("немає metrics_sample.txt (збережіть вивід curl http://localhost:ПОРТ/metrics вашого сервісу)")
    else:
        names = _metric_names(sample_path.read_text(encoding="utf-8"))
        if len(names) < 3:
            problems.append("metrics_sample.txt: менше трьох різних метрик")
        if not any("_total" in n for n in names):
            problems.append("metrics_sample.txt: немає жодного лічильника (_total)")

    def uses_service_metric(expr):
        return any(re.search(rf"(?<![A-Za-z0-9_:]){re.escape(n)}(?![A-Za-z0-9_:])", expr) for n in names)

    # --- prometheus.yml
    prom = _yaml(cfg / "prometheus/prometheus.yml", problems, "prometheus.yml") if (cfg / "prometheus/prometheus.yml").exists() else None
    if prom is None:
        problems.append("немає config/prometheus/prometheus.yml")
        prom = {}
    jobs = {j.get("job_name"): j for j in prom.get("scrape_configs", [])}
    targets_text = json.dumps(prom.get("scrape_configs", []))
    if service and service not in targets_text:
        problems.append(f"prometheus.yml: немає цілі зі службою {service}")
    if "node-exporter:9100" not in targets_text:
        problems.append("prometheus.yml: немає цілі node-exporter:9100")
    if len(jobs) < 3:
        problems.append("prometheus.yml: має бути щонайменше три завдання (prometheus, вузол, ваш сервіс)")
    rule_files = prom.get("rule_files") or []
    if not rule_files:
        problems.append("prometheus.yml: не задано rule_files")

    # --- правила
    recorded = set()
    alert_count = 0
    about_service = 0
    for rf in rule_files:
        p = cfg / "prometheus" / rf
        if not p.exists():
            problems.append(f"prometheus.yml: файл правил {rf} не існує")
            continue
        data = _yaml(p, problems, rf)
        for g in (data or {}).get("groups", []):
            for r in g.get("rules", []):
                if "record" in r:
                    recorded.add(r["record"])
                    if not RECORD_NAME.match(r["record"]):
                        problems.append(f"правило запису {r['record']}: ім'я має мати вигляд рівень:метрика:операції")
                    continue
                alert_count += 1
                nm = r.get("alert", "?")
                if not r.get("for"):
                    problems.append(f"сповіщення {nm}: немає for")
                if r.get("labels", {}).get("severity") not in SEVERITIES:
                    problems.append(f"сповіщення {nm}: мітка severity має бути однією з {sorted(SEVERITIES)}")
                if not r.get("annotations", {}).get("summary"):
                    problems.append(f"сповіщення {nm}: немає annotations.summary")
                if names and (uses_service_metric(r.get("expr", "")) or re.search(r"\bup\b", r.get("expr", ""))):
                    about_service += 1
    if names and about_service < 2:
        problems.append(f"лише {about_service} сповіщень стосуються метрик вашого сервісу (або up), потрібно щонайменше 2")
    if alert_count < 3:
        problems.append(f"правил сповіщень {alert_count}, потрібно щонайменше 3")
    if not recorded:
        problems.append("немає жодного правила запису (record)")

    # --- джерела даних
    ds_uids = {}
    dsf = list((cfg / "grafana/provisioning/datasources").glob("*.y*ml")) if (cfg / "grafana/provisioning/datasources").is_dir() else []
    if not dsf:
        problems.append("немає config/grafana/provisioning/datasources/*.yaml")
    for f in dsf:
        data = _yaml(f, problems, f.name) or {}
        for d in data.get("datasources", []):
            ds_uids[d.get("uid")] = d.get("type")
    if set(ds_uids.values()) != {"prometheus", "loki"}:
        problems.append("джерела даних: потрібні рівно два типи, prometheus і loki")
    if None in ds_uids:
        problems.append("джерела даних: у кожного джерела має бути uid")
    if not (cfg / "grafana/provisioning/dashboards/provider.yaml").exists():
        problems.append("немає config/grafana/provisioning/dashboards/provider.yaml")

    # --- дашборд
    dash_files = list((cfg / "grafana/dashboards").glob("*.json")) if (cfg / "grafana/dashboards").is_dir() else []
    if not dash_files:
        problems.append("немає config/grafana/dashboards/*.json")
    for f in dash_files:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except ValueError as exc:
            problems.append(f"{f.name}: некоректний JSON ({exc})")
            continue
        panels = [p for p in d.get("panels", []) if p.get("type") != "row"]
        types = {p["type"] for p in panels}
        if len(panels) < 8:
            problems.append(f"{f.name}: панелей {len(panels)}, потрібно щонайменше 8")
        for t in ("stat", "timeseries", "logs"):
            if t not in types:
                problems.append(f"{f.name}: немає панелі типу {t}")
        if not d.get("uid") or not d.get("title"):
            problems.append(f"{f.name}: потрібні uid і title")
        if not d.get("templating", {}).get("list"):
            problems.append(f"{f.name}: потрібна хоч одна змінна (templating)")
        boxes = []
        covered = 0
        for p in d.get("panels", []):
            g = p.get("gridPos", {})
            if g.get("x", 0) + g.get("w", 0) > 24:
                problems.append(f"{f.name}: панель {p.get('title')} виходить за ширину 24")
            for (x, y, w, h, t) in boxes:
                if g["x"] < x + w and x < g["x"] + g["w"] and g["y"] < y + h and y < g["y"] + g["h"]:
                    problems.append(f"{f.name}: панелі {p.get('title')} і {t} перекриваються")
            boxes.append((g["x"], g["y"], g["w"], g["h"], p.get("title")))
            if p.get("type") == "row":
                continue
            if not p.get("title"):
                problems.append(f"{f.name}: панель без заголовка")
            if p.get("fieldConfig", {}).get("defaults", {}).get("unit") is None and p["type"] in ("timeseries", "stat", "gauge"):
                problems.append(f"{f.name}: у панелі {p.get('title')} не задано одиницю виміру (fieldConfig.defaults.unit)")
            for t in p.get("targets", []):
                uid = (t.get("datasource") or p.get("datasource") or {}).get("uid")
                if uid not in ds_uids:
                    problems.append(f"{f.name}: панель {p.get('title')} посилається на невідоме джерело {uid}")
                expr = t.get("expr", "")
                if ds_uids.get(uid) == "loki":
                    try:
                        obs.parse_logql(expr)
                    except obs.LogQLError:
                        if not re.search(r"\{[^}]+\}", expr):
                            problems.append(f"{f.name}: порожній або хибний запит LogQL у панелі {p.get('title')}")
                elif names and uses_service_metric(expr):
                    covered += 1
        if names and covered < 4:
            problems.append(f"{f.name}: лише {covered} панелей із запитами до метрик вашого сервісу, потрібно щонайменше 4")

    # --- Loki і Alloy
    lk = cfg / "loki/loki-config.yaml"
    if not lk.exists():
        problems.append("немає config/loki/loki-config.yaml")
    else:
        data = _yaml(lk, problems, "loki-config.yaml") or {}
        if not data.get("limits_config", {}).get("retention_period"):
            problems.append("loki-config.yaml: не задано limits_config.retention_period")
        if not data.get("compactor", {}).get("retention_enabled"):
            problems.append("loki-config.yaml: не ввімкнено compactor.retention_enabled")
    al = cfg / "alloy/config.alloy"
    if not al.exists():
        problems.append("немає config/alloy/config.alloy")
    else:
        try:
            blocks = obs.parse_alloy(al.read_text(encoding="utf-8"))
        except obs.AlloyError as exc:
            problems.append(f"config.alloy: помилка синтаксису ({exc})")
            blocks = []
        kinds = {b["type"] for b in blocks}
        for need in ("local.file_match", "loki.source.file", "loki.write"):
            if need not in kinds:
                problems.append(f"config.alloy: немає компонента {need}")
        for b in blocks:
            if b["type"] == "loki.write":
                url = str(b["blocks"][0]["attrs"].get("url", "")) if b["blocks"] else ""
                if "loki:3100" not in url:
                    problems.append("config.alloy: loki.write має надсилати журнали на http://loki:3100/loki/api/v1/push")

    # --- відповіді
    ans = root.parent / "ANSWERS.md"
    if not ans.exists():
        problems.append("немає part_b/ANSWERS.md")
    else:
        text = ans.read_text(encoding="utf-8")
        parts = re.split(r"^## ", text, flags=re.M)[1:]
        if len(parts) < 5:
            problems.append("ANSWERS.md: має бути щонайменше п'ять розділів")
        for part in parts:
            body = part.split("**Відповідь:**", 1)[1] if "**Відповідь:**" in part else ""
            body = re.sub(r"<!--.*?-->", "", body, flags=re.S).strip()
            if len(body.split()) < 12:
                problems.append(f"ANSWERS.md: розділ «{part.splitlines()[0].strip()}» не заповнено (менше 12 слів)")
    return problems


def _get(url, auth=None):
    req = urllib.request.Request(url)
    if auth:
        import base64
        req.add_header("Authorization", "Basic " + base64.b64encode(auth.encode()).decode())
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def check_live(host="127.0.0.1", prom=9090, grafana=3000, loki=3100):
    problems = []
    try:
        targets = _get(f"http://{host}:{prom}/api/v1/targets")["data"]["activeTargets"]
        down = [t["labels"].get("job") for t in targets if t["health"] != "up"]
        if down or len(targets) < 3:
            problems.append(f"Prometheus: цілей {len(targets)}, недоступні {down}")
        groups = _get(f"http://{host}:{prom}/api/v1/rules")["data"]["groups"]
        if not any(r["type"] == "alerting" for g in groups for r in g["rules"]):
            problems.append("Prometheus: не завантажено жодного правила сповіщення")
    except Exception as exc:  # noqa: BLE001
        problems.append(f"Prometheus недоступний на {host}:{prom} ({exc})")
    try:
        auth = "admin:" + os.environ.get("GRAFANA_ADMIN_PASSWORD", "")
        found = _get(f"http://{host}:{grafana}/api/search?type=dash-db", auth)
        if not found:
            problems.append("Grafana: не знайдено жодного дашборда")
        ds = _get(f"http://{host}:{grafana}/api/datasources", auth)
        if {d["type"] for d in ds} != {"prometheus", "loki"}:
            problems.append("Grafana: джерела даних мають бути prometheus і loki")
    except Exception as exc:  # noqa: BLE001
        problems.append(f"Grafana недоступна на {host}:{grafana} ({exc}); задайте GRAFANA_ADMIN_PASSWORD")
    try:
        labels = _get(f"http://{host}:{loki}/loki/api/v1/labels")["data"]
        if not labels:
            problems.append("Loki: немає жодної мітки, журнали не надходять")
    except Exception as exc:  # noqa: BLE001
        problems.append(f"Loki недоступний на {host}:{loki} ({exc})")
    return problems


def main(argv=None):
    ap = argparse.ArgumentParser(description="Перевірка частини Б лабораторної APSIK-LAB05")
    ap.add_argument("stack", help="тека зі стеком, наприклад part_b/stack")
    ap.add_argument("--service", help="ім'я служби вашого сервісу в compose.yaml")
    ap.add_argument("--live", action="store_true", help="перевірити також стек, що працює")
    ap.add_argument("--host", default="127.0.0.1")
    a = ap.parse_args(argv)
    problems = check(a.stack, a.service)
    if a.live:
        problems += check_live(a.host)
    for p in problems:
        print("- " + p)
    print(f"Невиконаних вимог: {len(problems)}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
