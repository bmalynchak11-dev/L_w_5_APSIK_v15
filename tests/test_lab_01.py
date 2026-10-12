"""Відкриті тести задачі 1: файл prometheus.yml.

Запуск: pytest tests/test_lab_01.py -k S1   (замініть S1 на свій набір)
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


T01 = [('S1',
  'yaml',
  ['build_prometheus_config',
   {'scrape_interval': '15s',
    'jobs': [{'name': 'prometheus', 'targets': ['localhost:9090']},
             {'name': 'node', 'targets': ['node-exporter:9100']}]}],
  {'global': {'scrape_interval': '15s', 'evaluation_interval': '15s'},
   'scrape_configs': [{'job_name': 'prometheus', 'static_configs': [{'targets': ['localhost:9090']}]},
                      {'job_name': 'node', 'static_configs': [{'targets': ['node-exporter:9100']}]}]}),
 ('S1',
  'yaml',
  ['build_prometheus_config', {'scrape_interval': '30s', 'jobs': [{'name': 'node', 'targets': ['10.0.0.5:9100']}]}],
  {'global': {'scrape_interval': '30s', 'evaluation_interval': '30s'},
   'scrape_configs': [{'job_name': 'node', 'static_configs': [{'targets': ['10.0.0.5:9100']}]}]}),
 ('S1',
  'yaml',
  ['build_prometheus_config',
   {'scrape_interval': '10s', 'evaluation_interval': '1m', 'jobs': [{'name': 'app', 'targets': ['shop:8000']}]}],
  {'global': {'scrape_interval': '10s', 'evaluation_interval': '1m'},
   'scrape_configs': [{'job_name': 'app', 'static_configs': [{'targets': ['shop:8000']}]}]}),
 ('S2',
  'yaml',
  ['build_prometheus_config',
   {'scrape_interval': '30s',
    'external_labels': {'site': 'college', 'replica': '1'},
    'rule_files': ['rules.yml'],
    'alertmanagers': ['alertmanager:9093'],
    'jobs': [{'name': 'app',
              'targets': ['shop:8000', 'shop-2:8000'],
              'labels': {'env': 'lab'},
              'metrics_path': '/actuator/prometheus',
              'scrape_interval': '10s',
              'scrape_timeout': '5s',
              'sample_limit': 5000},
             {'name': 'node', 'targets': ['node-exporter:9100']}]}],
  {'global': {'scrape_interval': '30s',
              'evaluation_interval': '30s',
              'external_labels': {'site': 'college', 'replica': '1'}},
   'rule_files': ['rules.yml'],
   'alerting': {'alertmanagers': [{'static_configs': [{'targets': ['alertmanager:9093']}]}]},
   'scrape_configs': [{'job_name': 'app',
                       'static_configs': [{'targets': ['shop:8000', 'shop-2:8000'], 'labels': {'env': 'lab'}}],
                       'metrics_path': '/actuator/prometheus',
                       'scrape_interval': '10s',
                       'scrape_timeout': '5s',
                       'sample_limit': 5000},
                      {'job_name': 'node', 'static_configs': [{'targets': ['node-exporter:9100']}]}]}),
 ('S2',
  'yaml',
  ['build_prometheus_config',
   {'scrape_interval': '15s',
    'alertmanagers': ['am1:9093', 'am2:9093'],
    'jobs': [{'name': 'node', 'targets': ['n:9100']}]}],
  {'global': {'scrape_interval': '15s', 'evaluation_interval': '15s'},
   'alerting': {'alertmanagers': [{'static_configs': [{'targets': ['am1:9093', 'am2:9093']}]}]},
   'scrape_configs': [{'job_name': 'node', 'static_configs': [{'targets': ['n:9100']}]}]}),
 ('S2',
  'yaml',
  ['build_prometheus_config',
   {'scrape_interval': '15s',
    'rule_files': ['rules/a.yml', 'rules/b.yml'],
    'jobs': [{'name': 'x', 'targets': ['x:1'], 'metrics_path': '/metrics', 'scheme': 'http'}]}],
  {'global': {'scrape_interval': '15s', 'evaluation_interval': '15s'},
   'rule_files': ['rules/a.yml', 'rules/b.yml'],
   'scrape_configs': [{'job_name': 'x', 'static_configs': [{'targets': ['x:1']}]}]}),
 ('S3',
  'yaml',
  ['build_prometheus_config', {'jobs': [{'name': 'a', 'targets': ['a:1']}, {'name': 'a', 'targets': ['b:2']}]}],
  ('!ValueError', 'Дублікат завдання: a')),
 ('S3',
  'yaml',
  ['build_prometheus_config', {'jobs': [{'name': 'ok', 'targets': ['a:1']}, {'name': 'empty', 'targets': []}]}],
  ('!ValueError', 'Завдання empty не має цілей')),
 ('S3',
  'yaml',
  ['build_prometheus_config', {'jobs': [{'name': 'n', 'targets': ['node-exporter']}]}],
  ('!ValueError', 'Ціль має містити порт: node-exporter'))]


@pytest.mark.parametrize("tag,drv,args,expected", T01, ids=_ids(T01, "T01"))
def test_task_01(tag, drv, args, expected):
    run(1, drv, args, expected)
