"""Відкриті тести задачі 2: relabel.

Запуск: pytest tests/test_lab_02.py -k S1   (замініть S1 на свій набір)
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


T02 = [('S1',
  'relabel',
  [{'scenario': 'trim', 'drop_prefixes': ['go_', 'process_'], 'drop_labels': ['id', 'name']},
   [{'__name__': 'go_goroutines', 'job': 'node'},
    {'__name__': 'process_cpu_seconds_total'},
    {'__name__': 'node_load1', 'job': 'node', 'id': '/', 'name': 'x'}]],
  [None, None, {'__name__': 'node_load1', 'job': 'node'}]),
 ('S1',
  'relabel',
  [{'scenario': 'trim', 'drop_prefixes': ['go_', 'process_'], 'drop_labels': ['id', 'name']},
   [{'__name__': 'gopher_total', 'job': 'j'},
    {'__name__': 'http_requests_total', 'path': '/', 'identity': 'u1', 'name': 'n'}]],
  [{'__name__': 'gopher_total', 'job': 'j'}, {'__name__': 'http_requests_total', 'path': '/', 'identity': 'u1'}]),
 ('S1',
  'relabel',
  [{'scenario': 'trim', 'drop_prefixes': ['container_'], 'drop_labels': ['pod']},
   [{'__name__': 'container_cpu_usage', 'pod': 'p'},
    {'__name__': 'kube_pod_info', 'pod': 'p', 'node': 'n1'},
    {'__name__': 'up'}]],
  [None, {'__name__': 'kube_pod_info', 'node': 'n1'}, {'__name__': 'up'}]),
 ('S2',
  'relabel',
  [{'scenario': 'address', 'domain': 'college.lab', 'labels': ['host', 'env']},
   [{'__address__': 'web01.prod.college.lab:9100', 'job': 'node'}, {'__address__': 'db02.stage.college.lab:9187'}]],
  [{'address': 'web01.prod.college.lab:9100', 'labels': {'job': 'node', 'host': 'web01', 'env': 'prod'}},
   {'address': 'db02.stage.college.lab:9187', 'labels': {'host': 'db02', 'env': 'stage'}}]),
 ('S2',
  'relabel',
  [{'scenario': 'address', 'domain': 'college.lab', 'labels': ['host', 'env']},
   [{'__address__': 'localhost:9090', 'job': 'prometheus'},
    {'__address__': 'web01.prod.college.lab'},
    {'__address__': 'web01.prod.collegexlab:9100'}]],
  [{'address': 'localhost:9090', 'labels': {'job': 'prometheus'}},
   {'address': 'web01.prod.college.lab', 'labels': {}},
   {'address': 'web01.prod.collegexlab:9100', 'labels': {}}]),
 ('S2',
  'relabel',
  [{'scenario': 'address', 'domain': 'uni.edu.ua', 'labels': ['server', 'stage']},
   [{'__address__': 'web-01.test.uni.edu.ua:80'}, {'__address__': 'a.b.c.uni.edu.ua:80'}]],
  [{'address': 'web-01.test.uni.edu.ua:80', 'labels': {'server': 'web-01', 'stage': 'test'}},
   {'address': 'a.b.c.uni.edu.ua:80', 'labels': {}}]),
 ('S3',
  'relabel',
  [{'scenario': 'meta', 'prefix': '__meta_service_', 'flag': 'scrape', 'port': 'port', 'ignore': ['scrape', 'port']},
   [{'__address__': '10.0.0.5:80',
     '__meta_service_scrape': 'true',
     '__meta_service_port': '9102',
     '__meta_service_team': 'ops',
     '__meta_service_name': 'billing',
     'job': 'svc'}]],
  [{'address': '10.0.0.5:9102', 'labels': {'job': 'svc', 'team': 'ops', 'name': 'billing'}}]),
 ('S3',
  'relabel',
  [{'scenario': 'meta', 'prefix': '__meta_service_', 'flag': 'scrape', 'port': 'port', 'ignore': ['scrape', 'port']},
   [{'__address__': '10.0.0.5:80', '__meta_service_scrape': 'false', '__meta_service_port': '9102'},
    {'__address__': '10.0.0.6:80', '__meta_service_port': '9102'},
    {'__address__': '10.0.0.7:80', '__meta_service_scrape': 'TRUE', '__meta_service_port': '9102'}]],
  [None, None, None]),
 ('S3',
  'relabel',
  [{'scenario': 'meta', 'prefix': '__meta_service_', 'flag': 'scrape', 'port': 'port', 'ignore': ['scrape', 'port']},
   [{'__address__': '10.0.0.6',
     '__meta_service_scrape': 'true',
     '__meta_service_port': '8080',
     '__meta_other_x': '1'},
    {'__address__': '10.0.0.7:80', '__meta_service_scrape': 'true', '__meta_service_team': 'dev'}]],
  [{'address': '10.0.0.6:8080', 'labels': {}}, {'address': '10.0.0.7:80', 'labels': {'team': 'dev'}}])]


@pytest.mark.parametrize("tag,drv,args,expected", T02, ids=_ids(T02, "T02"))
def test_task_02(tag, drv, args, expected):
    run(2, drv, args, expected)
