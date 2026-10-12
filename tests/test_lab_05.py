"""Відкриті тести задачі 5: джерела даних Grafana.

Запуск: pytest tests/test_lab_05.py -k S1   (замініть S1 на свій набір)
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


T05 = [('S1',
  'yaml',
  ['build_datasource_provisioning',
   {'datasources': [{'name': 'Prometheus', 'type': 'prometheus', 'url': 'http://prometheus:9090'},
                    {'name': 'Loki', 'type': 'loki', 'url': 'http://loki:3100'}]}],
  {'apiVersion': 1,
   'datasources': [{'name': 'Prometheus',
                    'type': 'prometheus',
                    'uid': 'prometheus',
                    'access': 'proxy',
                    'url': 'http://prometheus:9090',
                    'isDefault': True,
                    'editable': False},
                   {'name': 'Loki',
                    'type': 'loki',
                    'uid': 'loki',
                    'access': 'proxy',
                    'url': 'http://loki:3100',
                    'isDefault': False,
                    'editable': False}]}),
 ('S1',
  'yaml',
  ['build_datasource_provisioning',
   {'datasources': [{'name': 'Prometheus',
                     'type': 'prometheus',
                     'url': 'http://prometheus:9090',
                     'interval': '15s'}]}],
  {'apiVersion': 1,
   'datasources': [{'name': 'Prometheus',
                    'type': 'prometheus',
                    'uid': 'prometheus',
                    'access': 'proxy',
                    'url': 'http://prometheus:9090',
                    'isDefault': True,
                    'editable': False,
                    'jsonData': {'timeInterval': '15s'}}]}),
 ('S1',
  'yaml',
  ['build_datasource_provisioning',
   {'datasources': [{'name': 'Loki', 'type': 'loki', 'url': 'http://loki:3100'},
                    {'name': 'Prometheus', 'type': 'prometheus', 'url': 'http://prometheus:9090', 'default': True}]}],
  {'apiVersion': 1,
   'datasources': [{'name': 'Loki',
                    'type': 'loki',
                    'uid': 'loki',
                    'access': 'proxy',
                    'url': 'http://loki:3100',
                    'isDefault': False,
                    'editable': False},
                   {'name': 'Prometheus',
                    'type': 'prometheus',
                    'uid': 'prometheus',
                    'access': 'proxy',
                    'url': 'http://prometheus:9090',
                    'isDefault': True,
                    'editable': False}]}),
 ('S2',
  'yaml',
  ['build_datasource_provisioning',
   {'datasources': [{'name': 'Prometheus',
                     'type': 'prometheus',
                     'url': 'http://prometheus:9090',
                     'interval': '5s',
                     'uid': 'prom-main'},
                    {'name': 'Loki', 'type': 'loki', 'url': 'http://loki:3100', 'max_lines': 1000}]}],
  {'apiVersion': 1,
   'datasources': [{'name': 'Prometheus',
                    'type': 'prometheus',
                    'uid': 'prom-main',
                    'access': 'proxy',
                    'url': 'http://prometheus:9090',
                    'isDefault': True,
                    'editable': False,
                    'jsonData': {'timeInterval': '5s'}},
                   {'name': 'Loki',
                    'type': 'loki',
                    'uid': 'loki',
                    'access': 'proxy',
                    'url': 'http://loki:3100',
                    'isDefault': False,
                    'editable': False,
                    'jsonData': {'maxLines': 1000}}]}),
 ('S2',
  'yaml',
  ['build_datasource_provisioning',
   {'datasources': [{'name': 'Loki',
                     'type': 'loki',
                     'url': 'http://loki:3100',
                     'max_lines': 500,
                     'derived': {'name': 'request_id',
                                 'regex': '"request_id":"(\\w+)"',
                                 'url': '/d/requests?var-id=${__value.raw}'}},
                    {'name': 'Prometheus', 'type': 'prometheus', 'url': 'http://prometheus:9090'}]}],
  {'apiVersion': 1,
   'datasources': [{'name': 'Loki',
                    'type': 'loki',
                    'uid': 'loki',
                    'access': 'proxy',
                    'url': 'http://loki:3100',
                    'isDefault': True,
                    'editable': False,
                    'jsonData': {'maxLines': 500,
                                 'derivedFields': [{'name': 'request_id',
                                                    'matcherRegex': '"request_id":"(\\w+)"',
                                                    'url': '/d/requests?var-id=${__value.raw}'}]}},
                   {'name': 'Prometheus',
                    'type': 'prometheus',
                    'uid': 'prometheus',
                    'access': 'proxy',
                    'url': 'http://prometheus:9090',
                    'isDefault': False,
                    'editable': False}]}),
 ('S2',
  'yaml',
  ['build_datasource_provisioning',
   {'datasources': [{'name': 'Prometheus', 'type': 'prometheus', 'url': 'http://prometheus:9090', 'interval': '30s'},
                    {'name': 'Prometheus archive',
                     'type': 'prometheus',
                     'url': 'http://archive:9090',
                     'default': True}]}],
  {'apiVersion': 1,
   'datasources': [{'name': 'Prometheus',
                    'type': 'prometheus',
                    'uid': 'prometheus',
                    'access': 'proxy',
                    'url': 'http://prometheus:9090',
                    'isDefault': False,
                    'editable': False,
                    'jsonData': {'timeInterval': '30s'}},
                   {'name': 'Prometheus archive',
                    'type': 'prometheus',
                    'uid': 'prometheus-archive',
                    'access': 'proxy',
                    'url': 'http://archive:9090',
                    'isDefault': True,
                    'editable': False}]}),
 ('S3',
  'yaml',
  ['build_datasource_provisioning',
   {'datasources': [{'name': 'Loki',
                     'type': 'loki',
                     'url': 'http://loki:3100',
                     'basic_auth_user': 'reader',
                     'password_env': 'LOKI_PASSWORD'},
                    {'name': 'Prometheus', 'type': 'prometheus', 'url': 'http://prometheus:9090'}]}],
  {'apiVersion': 1,
   'datasources': [{'name': 'Loki',
                    'type': 'loki',
                    'uid': 'loki',
                    'access': 'proxy',
                    'url': 'http://loki:3100',
                    'isDefault': True,
                    'editable': False,
                    'basicAuth': True,
                    'basicAuthUser': 'reader',
                    'secureJsonData': {'basicAuthPassword': '${LOKI_PASSWORD}'}},
                   {'name': 'Prometheus',
                    'type': 'prometheus',
                    'uid': 'prometheus',
                    'access': 'proxy',
                    'url': 'http://prometheus:9090',
                    'isDefault': False,
                    'editable': False}]}),
 ('S3',
  'yaml',
  ['build_datasource_provisioning',
   {'datasources': [{'name': 'Prometheus', 'type': 'prometheus', 'url': 'http://prometheus:9090', 'default': True},
                    {'name': 'Loki', 'type': 'loki', 'url': 'http://loki:3100', 'default': True}]}],
  ('!ValueError', 'Може бути лише одне джерело за замовчуванням')),
 ('S3',
  'yaml',
  ['build_datasource_provisioning',
   {'datasources': [{'name': 'Prometheus', 'type': 'graphite', 'url': 'http://prometheus:9090'}]}],
  ('!ValueError', 'Непідтримуваний тип: graphite'))]


@pytest.mark.parametrize("tag,drv,args,expected", T05, ids=_ids(T05, "T05"))
def test_task_05(tag, drv, args, expected):
    run(5, drv, args, expected)
