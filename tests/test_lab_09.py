"""Відкриті тести задачі 9: запити LogQL.

Запуск: pytest tests/test_lab_09.py -k S1   (замініть S1 на свій набір)
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


T09 = [('S1',
  'logql',
  [{'kind': 'filter', 'app': 'shop', 'word': 'ERROR', 'exclude': 'healthcheck', 'envs': 'prod|stage'}, 'errors', 200],
  [1, 4, 7]),
 ('S1',
  'logql',
  [{'kind': 'filter', 'app': 'shop', 'word': 'timeout', 'exclude': 'Timeout', 'envs': 'prod|stage'}, 'errors', 200],
  [1]),
 ('S1',
  'logql',
  [{'kind': 'filter', 'app': 'shop', 'word': 'ERROR', 'exclude': 'healthcheck', 'envs': 'prod|stage'},
   'timeouts',
   200],
  [1]),
 ('S2',
  'logql',
  [{'kind': 'parse', 'app': 'shop', 'level': 'error', 'min_status': 500, 'slow': '500ms'}, 'level_errors', 200],
  [10, 11, 15, 18]),
 ('S2',
  'logql',
  [{'kind': 'parse', 'app': 'shop', 'level': 'warn', 'min_status': 500, 'slow': '500ms'}, 'level_errors', 200],
  [12]),
 ('S2',
  'logql',
  [{'kind': 'parse', 'app': 'shop', 'level': 'error', 'min_status': 500, 'slow': '500ms'}, 'server_errors', 200],
  [10, 11, 15, 18]),
 ('S3',
  'logql',
  [{'kind': 'metric', 'app': 'api', 'window': '5m', 'top': 2}, 'lines_rate', 200],
  [[{}, 0.03333333333333333]]),
 ('S3',
  'logql',
  [{'kind': 'metric', 'app': 'api', 'window': '1m', 'top': 2}, 'lines_rate', 200],
  [[{}, 0.08333333333333333]]),
 ('S3',
  'logql',
  [{'kind': 'metric', 'app': 'api', 'window': '5m', 'top': 2}, 'by_level', 200],
  [[{'level': 'error'}, 4.0], [{'level': 'info'}, 5.0], [{'level': 'warn'}, 1.0]])]


@pytest.mark.parametrize("tag,drv,args,expected", T09, ids=_ids(T09, "T09"))
def test_task_09(tag, drv, args, expected):
    run(9, drv, args, expected)
