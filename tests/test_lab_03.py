"""Відкриті тести задачі 3: запити PromQL для панелей.

Запуск: pytest tests/test_lab_03.py -k S1   (замініть S1 на свій набір)
Тут лише приклади з карток варіантів; повний набір перевірок є у викладача.
"""
import signal

import pytest
from conftest import load
from support import DRIVERS


def _same(a, b):
    """Рівність із допуском для дробових чисел; список і кортеж вважаються однаковими послідовностями."""
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) <= 1e-9 * max(1.0, abs(b))
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_same(a[k], b[k]) for k in a)
    return a == b


def run(task, drv, args, expected):
    """Запускає драйвер на вашому модулі. Помилки подано як ("!КласПомилки", "повідомлення")."""
    got = DRIVERS[drv](load(task), *args)
    assert _same(got, expected), f"отримано {got!r}, очікувалось {expected!r}"


def _ids(cases, prefix):
    return [f"{prefix}-{c[0]}-{i}" for i, c in enumerate(cases)]


@pytest.fixture(autouse=True)
def _watchdog():
    """Тест, що завис (нескінченний цикл), завершується за 10 с."""
    def boom(signum, frame):
        raise TimeoutError("тест завис довше 10 с: перевірте умови завершення циклів")
    old = signal.signal(signal.SIGALRM, boom)
    signal.alarm(10)
    yield
    signal.alarm(0)
    signal.signal(signal.SIGALRM, old)


T03 = [('S1',
  'promql',
  [{'kind': 'host', 'mountpoint': '/', 'device': 'eth0', 'window': '5m'}, 'host', 'cpu_used_percent', 600],
  [[{'instance': 'a'}, 70.0], [{'instance': 'b'}, 80.0]]),
 ('S1',
  'promql',
  [{'kind': 'host', 'mountpoint': '/', 'device': 'eth0', 'window': '10m'}, 'host', 'cpu_used_percent', 600],
  [[{'instance': 'a'}, 50.51282051282051], [{'instance': 'b'}, 80.0]]),
 ('S1',
  'promql',
  [{'kind': 'host', 'mountpoint': '/', 'device': 'eth0', 'window': '5m'}, 'host', 'mem_used_percent', 600],
  [[{'instance': 'a'}, 75.0], [{'instance': 'b'}, 25.0]]),
 ('S2',
  'promql',
  [{'kind': 'trend', 'window': '1h', 'horizon_hours': 24, 'mountpoint': '/'}, 'trend', 'uptime_hours', 7200],
  [[{'instance': 'a'}, 1.0], [{'instance': 'b'}, 2.0]]),
 ('S2',
  'promql',
  [{'kind': 'trend', 'window': '1h', 'horizon_hours': 24, 'mountpoint': '/'}, 'trend', 'disk_full_soon', 7200],
  [[{'instance': 'a', 'mountpoint': '/'}, -1260000000000.0]]),
 ('S2',
  'promql',
  [{'kind': 'trend', 'window': '1h', 'horizon_hours': 6, 'mountpoint': '/'}, 'trend', 'disk_full_soon', 7200],
  [[{'instance': 'a', 'mountpoint': '/'}, -180000000000.0]]),
 ('S3',
  'promql',
  [{'kind': 'app', 'window': '5m', 'top': 3}, 'app', 'rps_by_code', 7200],
  [[{'code': '200'}, 2.216666666666667], [{'code': '500'}, 0.1]]),
 ('S3',
  'promql',
  [{'kind': 'app', 'window': '2m', 'top': 3}, 'app', 'rps_by_code', 7200],
  [[{'code': '200'}, 2.216666666666667], [{'code': '500'}, 0.1]]),
 ('S3',
  'promql',
  [{'kind': 'app', 'window': '5m', 'top': 3}, 'app', 'top_paths', 7200],
  [[{'path': '/'}, 5400.0], [{'path': '/orders'}, 720.0], [{'path': '/pay'}, 2160.0]])]


@pytest.mark.parametrize("tag,drv,args,expected", T03, ids=_ids(T03, "T03"))
def test_task_03(tag, drv, args, expected):
    run(3, drv, args, expected)
