"""Навчальний сервіс «shop»: віддає метрики Prometheus на /metrics і пише журнал JSON у файл.

Запуск: python service.py   (порт 8000, змінні середовища: PORT, LOG_FILE, SEED, SELF_LOAD)
Сервіс сам створює фонове навантаження (SELF_LOAD=1, типово), тож метрики з'являються без зовнішніх клієнтів.
Лише стандартна бібліотека Python, залежності не потрібні.
"""
import json
import os
import random
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import urlopen

PORT = int(os.environ.get("PORT", "8000"))
LOG_FILE = os.environ.get("LOG_FILE", "app.log")
BUCKETS = (0.05, 0.1, 0.25, 0.5, 1.0, 2.5)
PATHS = {"/": (0.02, 0.0), "/orders": (0.08, 0.03), "/pay": (0.2, 0.12)}  # (типова затримка, частка помилок)
START = time.time()
LOCK = threading.Lock()
REQUESTS = {}  # (method, path, code) -> кількість
DURATION = {}  # path -> [кількості по відрах (накопичувально), сума, кількість]
IN_FLIGHT = [0]
RNG = random.Random(int(os.environ.get("SEED", "5")))


def log(level, msg, **fields):
    record = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "level": level, "msg": msg}
    record.update(fields)
    with LOCK:
        with open(LOG_FILE, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def observe(method, path, code, seconds):
    with LOCK:
        REQUESTS[(method, path, code)] = REQUESTS.get((method, path, code), 0) + 1
        h = DURATION.setdefault(path, [[0] * len(BUCKETS), 0.0, 0])
        for i, bound in enumerate(BUCKETS):
            if seconds <= bound:
                h[0][i] += 1
        h[1] += seconds
        h[2] += 1


def render_metrics():
    out = ["# HELP http_requests_total Кількість оброблених запитів.", "# TYPE http_requests_total counter"]
    with LOCK:
        for (method, path, code), n in sorted(REQUESTS.items()):
            out.append(f'http_requests_total{{method="{method}",path="{path}",code="{code}"}} {n}')
        out += ["# HELP http_requests_in_flight Запити, що обробляються зараз.",
                "# TYPE http_requests_in_flight gauge", f"http_requests_in_flight {IN_FLIGHT[0]}",
                "# HELP http_request_duration_seconds Тривалість обробки запиту.",
                "# TYPE http_request_duration_seconds histogram"]
        for path, (counts, total, n) in sorted(DURATION.items()):
            for bound, c in zip(BUCKETS, counts):
                out.append(f'http_request_duration_seconds_bucket{{path="{path}",le="{bound}"}} {c}')
            out.append(f'http_request_duration_seconds_bucket{{path="{path}",le="+Inf"}} {n}')
            out.append(f'http_request_duration_seconds_sum{{path="{path}"}} {total:.6f}')
            out.append(f'http_request_duration_seconds_count{{path="{path}"}} {n}')
        out += ["# HELP process_start_time_seconds Час запуску процесу.", "# TYPE process_start_time_seconds gauge",
                f"process_start_time_seconds {START:.0f}"]
    return "\n".join(out) + "\n"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/metrics":
            body = render_metrics().encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path not in PATHS:
            observe("GET", "other", "404", 0.001)
            self.send_response(404)
            self.end_headers()
            return
        base, error_rate = PATHS[path]
        started = time.time()
        IN_FLIGHT[0] += 1
        try:
            with LOCK:
                delay = base * RNG.uniform(0.5, 2.0)
                failed = RNG.random() < error_rate
            time.sleep(delay)
        finally:
            IN_FLIGHT[0] -= 1
        code = 500 if failed else 200
        seconds = time.time() - started
        observe("GET", path, str(code), seconds)
        if failed:
            log("error", "помилка обробки запиту", path=path, status=code, duration=f"{int(seconds * 1000)}ms")
        else:
            log("info", "запит оброблено", path=path, status=code, duration=f"{int(seconds * 1000)}ms")
        self.send_response(code)
        self.end_headers()


def self_load():
    time.sleep(1)
    rng = random.Random(1)
    while True:
        path = rng.choice(list(PATHS))
        try:
            urlopen(f"http://127.0.0.1:{PORT}{path}", timeout=5).read()
        except Exception:  # noqa: BLE001
            pass
        time.sleep(rng.uniform(0.05, 0.3))


if __name__ == "__main__":
    log("info", "сервіс запущено", port=PORT)
    if os.environ.get("SELF_LOAD", "1") == "1":
        threading.Thread(target=self_load, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
