"""Відкриті тести задачі 8: конфігурація Alloy.

Запуск: pytest tests/test_lab_08.py -k S1   (замініть S1 на свій набір)
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


T08 = [('S1',
  'alloy',
  [{'sources': [{'name': 'shop',
                 'paths': ['/var/log/app/*.log'],
                 'labels': {'app': 'shop', 'env': 'lab'},
                 'format': 'plain'}],
    'loki_url': 'http://loki:3100/loki/api/v1/push'}],
  {'components': ['local.file_match.shop', 'loki.process.shop', 'loki.source.file.shop', 'loki.write.default'],
   'sources': {'shop': {'targets': [{'__path__': '/var/log/app/*.log', 'app': 'shop', 'env': 'lab'}],
                        'reads_file_match': True,
                        'to_process': True,
                        'to_write': True,
                        'stages': []}},
   'write_url': 'http://loki:3100/loki/api/v1/push'}),
 ('S1',
  'alloy',
  [{'sources': [{'name': 'shop',
                 'paths': ['/var/log/a.log', '/var/log/b.log'],
                 'labels': {'job': 'sys'},
                 'format': 'plain'}],
    'loki_url': 'http://localhost:3100/loki/api/v1/push'}],
  {'components': ['local.file_match.shop', 'loki.process.shop', 'loki.source.file.shop', 'loki.write.default'],
   'sources': {'shop': {'targets': [{'__path__': '/var/log/a.log', 'job': 'sys'},
                                    {'__path__': '/var/log/b.log', 'job': 'sys'}],
                        'reads_file_match': True,
                        'to_process': True,
                        'to_write': True,
                        'stages': []}},
   'write_url': 'http://localhost:3100/loki/api/v1/push'}),
 ('S1',
  'alloy',
  [{'sources': [{'name': 'auth', 'paths': ['/logs/auth/*.log'], 'labels': {'app': 'auth'}},
                {'name': 'shop',
                 'paths': ['/var/log/app/*.log'],
                 'labels': {'app': 'shop', 'env': 'lab'},
                 'format': 'plain'}],
    'loki_url': 'http://loki:3100/loki/api/v1/push'}],
  {'components': ['local.file_match.auth',
                  'local.file_match.shop',
                  'loki.process.auth',
                  'loki.process.shop',
                  'loki.source.file.auth',
                  'loki.source.file.shop',
                  'loki.write.default'],
   'sources': {'auth': {'targets': [{'__path__': '/logs/auth/*.log', 'app': 'auth'}],
                        'reads_file_match': True,
                        'to_process': True,
                        'to_write': True,
                        'stages': []},
               'shop': {'targets': [{'__path__': '/var/log/app/*.log', 'app': 'shop', 'env': 'lab'}],
                        'reads_file_match': True,
                        'to_process': True,
                        'to_write': True,
                        'stages': []}},
   'write_url': 'http://loki:3100/loki/api/v1/push'}),
 ('S2',
  'alloy',
  [{'sources': [{'name': 'shop',
                 'paths': ['/var/log/app/*.log'],
                 'labels': {'app': 'shop', 'env': 'lab'},
                 'format': 'json'}],
    'loki_url': 'http://loki:3100/loki/api/v1/push'}],
  {'components': ['local.file_match.shop', 'loki.process.shop', 'loki.source.file.shop', 'loki.write.default'],
   'sources': {'shop': {'targets': [{'__path__': '/var/log/app/*.log', 'app': 'shop', 'env': 'lab'}],
                        'reads_file_match': True,
                        'to_process': True,
                        'to_write': True,
                        'stages': [('json', {'level': 'level'})]}},
   'write_url': 'http://loki:3100/loki/api/v1/push'}),
 ('S2',
  'alloy',
  [{'sources': [{'name': 'shop',
                 'paths': ['/var/log/app/*.log'],
                 'labels': {'app': 'shop', 'env': 'lab'},
                 'format': 'json',
                 'level_label': True}],
    'loki_url': 'http://loki:3100/loki/api/v1/push'}],
  {'components': ['local.file_match.shop', 'loki.process.shop', 'loki.source.file.shop', 'loki.write.default'],
   'sources': {'shop': {'targets': [{'__path__': '/var/log/app/*.log', 'app': 'shop', 'env': 'lab'}],
                        'reads_file_match': True,
                        'to_process': True,
                        'to_write': True,
                        'stages': [('json', {'level': 'level'}), ('labels', {'level': ''})]}},
   'write_url': 'http://loki:3100/loki/api/v1/push'}),
 ('S2',
  'alloy',
  [{'sources': [{'name': 'shop',
                 'paths': ['/var/log/app/*.log'],
                 'labels': {'app': 'shop', 'env': 'lab'},
                 'format': 'logfmt',
                 'level_label': True}],
    'loki_url': 'http://loki:3100/loki/api/v1/push'}],
  {'components': ['local.file_match.shop', 'loki.process.shop', 'loki.source.file.shop', 'loki.write.default'],
   'sources': {'shop': {'targets': [{'__path__': '/var/log/app/*.log', 'app': 'shop', 'env': 'lab'}],
                        'reads_file_match': True,
                        'to_process': True,
                        'to_write': True,
                        'stages': [('logfmt', {'level': ''}), ('labels', {'level': ''})]}},
   'write_url': 'http://loki:3100/loki/api/v1/push'}),
 ('S3',
  'alloy',
  [{'sources': [{'name': 'shop',
                 'paths': ['/var/log/app/*.log'],
                 'labels': {'app': 'shop', 'env': 'lab'},
                 'format': 'json',
                 'level_label': True,
                 'drop_levels': ['debug', 'trace']}],
    'loki_url': 'http://loki:3100/loki/api/v1/push'}],
  {'components': ['local.file_match.shop', 'loki.process.shop', 'loki.source.file.shop', 'loki.write.default'],
   'sources': {'shop': {'targets': [{'__path__': '/var/log/app/*.log', 'app': 'shop', 'env': 'lab'}],
                        'reads_file_match': True,
                        'to_process': True,
                        'to_write': True,
                        'stages': [('json', {'level': 'level'}),
                                   ('labels', {'level': ''}),
                                   ('drop', 'level', '^(debug|trace)$')]}},
   'write_url': 'http://loki:3100/loki/api/v1/push'}),
 ('S3',
  'alloy',
  [{'sources': [{'name': 'shop',
                 'paths': ['/var/log/app/*.log'],
                 'labels': {'app': 'shop', 'env': 'lab'},
                 'format': 'logfmt',
                 'drop_levels': ['debug']}],
    'loki_url': 'http://loki:3100/loki/api/v1/push'}],
  {'components': ['local.file_match.shop', 'loki.process.shop', 'loki.source.file.shop', 'loki.write.default'],
   'sources': {'shop': {'targets': [{'__path__': '/var/log/app/*.log', 'app': 'shop', 'env': 'lab'}],
                        'reads_file_match': True,
                        'to_process': True,
                        'to_write': True,
                        'stages': [('logfmt', {'level': ''}), ('drop', 'level', '^(debug)$')]}},
   'write_url': 'http://loki:3100/loki/api/v1/push'}),
 ('S3',
  'alloy',
  [{'sources': [{'name': 'shop',
                 'paths': ['/var/log/app/*.log'],
                 'labels': {'app': 'shop', 'env': 'lab'},
                 'format': 'plain',
                 'drop_levels': ['debug'],
                 'level_label': True}],
    'loki_url': 'http://loki:3100/loki/api/v1/push'}],
  {'components': ['local.file_match.shop', 'loki.process.shop', 'loki.source.file.shop', 'loki.write.default'],
   'sources': {'shop': {'targets': [{'__path__': '/var/log/app/*.log', 'app': 'shop', 'env': 'lab'}],
                        'reads_file_match': True,
                        'to_process': True,
                        'to_write': True,
                        'stages': []}},
   'write_url': 'http://loki:3100/loki/api/v1/push'})]


@pytest.mark.parametrize("tag,drv,args,expected", T08, ids=_ids(T08, "T08"))
def test_task_08(tag, drv, args, expected):
    run(8, drv, args, expected)
