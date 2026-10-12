"""Відкриті тести задачі 4: правила запису та сповіщень.

Запуск: pytest tests/test_lab_04.py -k S1   (замініть S1 на свій набір)
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


T04 = [('S1',
  'rules',
  [{'groups': [{'name': 'availability',
                'rules': [{'alert': 'InstanceDown',
                           'kind': 'down',
                           'job': 'node',
                           'for': '2m',
                           'severity': 'page',
                           'summary': 'Ціль недоступна'},
                          {'alert': 'HighCpu',
                           'kind': 'cpu',
                           'threshold': 85,
                           'for': '1m',
                           'severity': 'ticket',
                           'summary': 'Процесор перевантажено'}]}]}],
  {'groups': [{'name': 'availability',
               'rules': [{'alert': 'InstanceDown',
                          'expr': 'up{job="node"} == 0',
                          'for': '2m',
                          'labels': {'severity': 'page'},
                          'annotations': {'summary': 'Ціль недоступна',
                                          'description': '{{ $labels.instance }}: поточне значення {{ $value | '
                                                         'humanize }}'}},
                         {'alert': 'HighCpu',
                          'expr': '100 - avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100 > '
                                  '85',
                          'for': '1m',
                          'labels': {'severity': 'ticket'},
                          'annotations': {'summary': 'Процесор перевантажено',
                                          'description': '{{ $labels.instance }}: поточне значення {{ $value | '
                                                         'humanize }}'}}]}]}),
 ('S1',
  'rules',
  [{'groups': [{'name': 'g',
                'interval': '30s',
                'rules': [{'alert': 'NoTraffic',
                           'kind': 'rate',
                           'metric': 'http_requests_total',
                           'window': '5m',
                           'threshold': 100,
                           'severity': 'info',
                           'summary': 'Забагато запитів'}]}]}],
  {'groups': [{'name': 'g',
               'interval': '30s',
               'rules': [{'alert': 'NoTraffic',
                          'expr': 'sum by (job) (rate(http_requests_total[5m])) > 100',
                          'labels': {'severity': 'info'},
                          'annotations': {'summary': 'Забагато запитів',
                                          'description': '{{ $labels.instance }}: поточне значення {{ $value | '
                                                         'humanize }}'}}]}]}),
 ('S1',
  'rules',
  [{'groups': [{'name': 'g',
                'rules': [{'alert': 'DiskLow',
                           'kind': 'disk',
                           'mountpoint': '/data',
                           'threshold': 10,
                           'for': '0s',
                           'severity': 'page',
                           'summary': 'Мало місця'}]}]}],
  {'groups': [{'name': 'g',
               'rules': [{'alert': 'DiskLow',
                          'expr': 'node_filesystem_avail_bytes{mountpoint="/data"} / '
                                  'node_filesystem_size_bytes{mountpoint="/data"} * 100 < 10',
                          'labels': {'severity': 'page'},
                          'annotations': {'summary': 'Мало місця',
                                          'description': '{{ $labels.instance }}: поточне значення {{ $value | '
                                                         'humanize }}'}}]}]}),
 ('S2',
  'rules',
  [{'groups': [{'name': 'recording',
                'rules': [{'record': True, 'metric': 'http_requests_total', 'window': '5m', 'by': ['job']},
                          {'record': True, 'metric': 'http_requests_total', 'window': '1m', 'by': ['job', 'code']},
                          {'record': True,
                           'metric': 'http_request_duration_seconds_count',
                           'window': '5m',
                           'by': ['path']}]}]}],
  {'groups': [{'name': 'recording',
               'rules': [{'record': 'job:http_requests:rate5m',
                          'expr': 'sum by (job) (rate(http_requests_total[5m]))'},
                         {'record': 'job_code:http_requests:rate1m',
                          'expr': 'sum by (job, code) (rate(http_requests_total[1m]))'},
                         {'record': 'path:http_request_duration_seconds_count:rate5m',
                          'expr': 'sum by (path) (rate(http_request_duration_seconds_count[5m]))'}]}]}),
 ('S2',
  'rules',
  [{'groups': [{'name': 'mixed',
                'rules': [{'record': True,
                           'metric': 'node_network_receive_bytes_total',
                           'window': '1m',
                           'by': ['instance']},
                          {'alert': 'DiskLow',
                           'kind': 'disk',
                           'mountpoint': '/',
                           'threshold': 15,
                           'for': '5m',
                           'severity': 'ticket',
                           'summary': 'Диск майже повний'}]}]}],
  {'groups': [{'name': 'mixed',
               'rules': [{'record': 'instance:node_network_receive_bytes:rate1m',
                          'expr': 'sum by (instance) (rate(node_network_receive_bytes_total[1m]))'},
                         {'alert': 'DiskLow',
                          'expr': 'node_filesystem_avail_bytes{mountpoint="/"} / '
                                  'node_filesystem_size_bytes{mountpoint="/"} * 100 < 15',
                          'for': '5m',
                          'labels': {'severity': 'ticket'},
                          'annotations': {'summary': 'Диск майже повний',
                                          'description': '{{ $labels.instance }}: поточне значення {{ $value | '
                                                         'humanize }}'}}]}]}),
 ('S2',
  'timeline',
  [{'groups': [{'name': 'd',
                'rules': [{'alert': 'DiskLow',
                           'kind': 'disk',
                           'mountpoint': '/',
                           'threshold': 15,
                           'for': '1m',
                           'severity': 'ticket',
                           'summary': 'Диск'}]}]},
   'alerts',
   'DiskLow',
   1200],
  [(300.0, 'inactive'), (600.0, 'pending'), (660.0, 'firing')]),
 ('S3',
  'rules',
  [{'groups': [{'name': 'a',
                'rules': [{'alert': 'Bad-Name', 'kind': 'down', 'job': 'x', 'severity': 'page', 'summary': 's'}]}]}],
  ('!ValueError', "Недопустиме ім'я правила: Bad-Name")),
 ('S3',
  'rules',
  [{'groups': [{'name': 'a',
                'rules': [{'alert': 'X', 'kind': 'down', 'job': 'x', 'severity': 'urgent', 'summary': 's'}]}]}],
  ('!ValueError', 'Невідома важливість: urgent')),
 ('S3',
  'rules',
  [{'groups': [{'name': 'a',
                'rules': [{'alert': 'X',
                           'kind': 'down',
                           'job': 'x',
                           'for': 'five minutes',
                           'severity': 'page',
                           'summary': 's'}]}]}],
  ('!ValueError', 'Некоректна тривалість: five minutes'))]


@pytest.mark.parametrize("tag,drv,args,expected", T04, ids=_ids(T04, "T04"))
def test_task_04(tag, drv, args, expected):
    run(4, drv, args, expected)
