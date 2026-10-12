"""Відкриті тести задачі 7: конфігурація Loki.

Запуск: pytest tests/test_lab_07.py -k S1   (замініть S1 на свій набір)
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


T07 = [('S1',
  'yaml',
  ['build_loki_config', {'retention': '168h'}],
  {'auth_enabled': False,
   'server': {'http_listen_port': 3100, 'grpc_listen_port': 9096},
   'common': {'instance_addr': '127.0.0.1',
              'path_prefix': '/loki',
              'storage': {'filesystem': {'chunks_directory': '/loki/chunks', 'rules_directory': '/loki/rules'}},
              'replication_factor': 1,
              'ring': {'kvstore': {'store': 'inmemory'}}},
   'schema_config': {'configs': [{'from': '2024-04-01',
                                  'store': 'tsdb',
                                  'object_store': 'filesystem',
                                  'schema': 'v13',
                                  'index': {'prefix': 'index_', 'period': '24h'}}]},
   'limits_config': {'retention_period': '168h', 'reject_old_samples': True, 'reject_old_samples_max_age': '168h'},
   'compactor': {'working_directory': '/loki/compactor',
                 'retention_enabled': True,
                 'delete_request_store': 'filesystem'},
   'analytics': {'reporting_enabled': False}}),
 ('S1',
  'yaml',
  ['build_loki_config', {'retention': '24h'}],
  {'auth_enabled': False,
   'server': {'http_listen_port': 3100, 'grpc_listen_port': 9096},
   'common': {'instance_addr': '127.0.0.1',
              'path_prefix': '/loki',
              'storage': {'filesystem': {'chunks_directory': '/loki/chunks', 'rules_directory': '/loki/rules'}},
              'replication_factor': 1,
              'ring': {'kvstore': {'store': 'inmemory'}}},
   'schema_config': {'configs': [{'from': '2024-04-01',
                                  'store': 'tsdb',
                                  'object_store': 'filesystem',
                                  'schema': 'v13',
                                  'index': {'prefix': 'index_', 'period': '24h'}}]},
   'limits_config': {'retention_period': '24h', 'reject_old_samples': True, 'reject_old_samples_max_age': '168h'},
   'compactor': {'working_directory': '/loki/compactor',
                 'retention_enabled': True,
                 'delete_request_store': 'filesystem'},
   'analytics': {'reporting_enabled': False}}),
 ('S1',
  'yaml',
  ['build_loki_config', {'retention': '720h', 'max_age': '24h'}],
  {'auth_enabled': False,
   'server': {'http_listen_port': 3100, 'grpc_listen_port': 9096},
   'common': {'instance_addr': '127.0.0.1',
              'path_prefix': '/loki',
              'storage': {'filesystem': {'chunks_directory': '/loki/chunks', 'rules_directory': '/loki/rules'}},
              'replication_factor': 1,
              'ring': {'kvstore': {'store': 'inmemory'}}},
   'schema_config': {'configs': [{'from': '2024-04-01',
                                  'store': 'tsdb',
                                  'object_store': 'filesystem',
                                  'schema': 'v13',
                                  'index': {'prefix': 'index_', 'period': '24h'}}]},
   'limits_config': {'retention_period': '720h', 'reject_old_samples': True, 'reject_old_samples_max_age': '24h'},
   'compactor': {'working_directory': '/loki/compactor',
                 'retention_enabled': True,
                 'delete_request_store': 'filesystem'},
   'analytics': {'reporting_enabled': False}}),
 ('S2',
  'yaml',
  ['build_loki_config',
   {'retention': '336h',
    'http_port': 3200,
    'grpc_port': 9097,
    'data_dir': '/var/lib/loki/',
    'ingestion_rate_mb': 8,
    'max_streams_per_user': 5000,
    'max_age': '72h'}],
  {'auth_enabled': False,
   'server': {'http_listen_port': 3200, 'grpc_listen_port': 9097},
   'common': {'instance_addr': '127.0.0.1',
              'path_prefix': '/var/lib/loki',
              'storage': {'filesystem': {'chunks_directory': '/var/lib/loki/chunks',
                                         'rules_directory': '/var/lib/loki/rules'}},
              'replication_factor': 1,
              'ring': {'kvstore': {'store': 'inmemory'}}},
   'schema_config': {'configs': [{'from': '2024-04-01',
                                  'store': 'tsdb',
                                  'object_store': 'filesystem',
                                  'schema': 'v13',
                                  'index': {'prefix': 'index_', 'period': '24h'}}]},
   'limits_config': {'retention_period': '336h',
                     'reject_old_samples': True,
                     'reject_old_samples_max_age': '72h',
                     'ingestion_rate_mb': 8,
                     'max_streams_per_user': 5000},
   'compactor': {'working_directory': '/var/lib/loki/compactor',
                 'retention_enabled': True,
                 'delete_request_store': 'filesystem'},
   'analytics': {'reporting_enabled': False}}),
 ('S2',
  'yaml',
  ['build_loki_config', {'retention': '48h', 'ingestion_rate_mb': 4}],
  {'auth_enabled': False,
   'server': {'http_listen_port': 3100, 'grpc_listen_port': 9096},
   'common': {'instance_addr': '127.0.0.1',
              'path_prefix': '/loki',
              'storage': {'filesystem': {'chunks_directory': '/loki/chunks', 'rules_directory': '/loki/rules'}},
              'replication_factor': 1,
              'ring': {'kvstore': {'store': 'inmemory'}}},
   'schema_config': {'configs': [{'from': '2024-04-01',
                                  'store': 'tsdb',
                                  'object_store': 'filesystem',
                                  'schema': 'v13',
                                  'index': {'prefix': 'index_', 'period': '24h'}}]},
   'limits_config': {'retention_period': '48h',
                     'reject_old_samples': True,
                     'reject_old_samples_max_age': '168h',
                     'ingestion_rate_mb': 4},
   'compactor': {'working_directory': '/loki/compactor',
                 'retention_enabled': True,
                 'delete_request_store': 'filesystem'},
   'analytics': {'reporting_enabled': False}}),
 ('S2',
  'yaml',
  ['build_loki_config', {'retention': '48h', 'max_streams_per_user': 100, 'data_dir': '/data'}],
  {'auth_enabled': False,
   'server': {'http_listen_port': 3100, 'grpc_listen_port': 9096},
   'common': {'instance_addr': '127.0.0.1',
              'path_prefix': '/data',
              'storage': {'filesystem': {'chunks_directory': '/data/chunks', 'rules_directory': '/data/rules'}},
              'replication_factor': 1,
              'ring': {'kvstore': {'store': 'inmemory'}}},
   'schema_config': {'configs': [{'from': '2024-04-01',
                                  'store': 'tsdb',
                                  'object_store': 'filesystem',
                                  'schema': 'v13',
                                  'index': {'prefix': 'index_', 'period': '24h'}}]},
   'limits_config': {'retention_period': '48h',
                     'reject_old_samples': True,
                     'reject_old_samples_max_age': '168h',
                     'max_streams_per_user': 100},
   'compactor': {'working_directory': '/data/compactor',
                 'retention_enabled': True,
                 'delete_request_store': 'filesystem'},
   'analytics': {'reporting_enabled': False}}),
 ('S3',
  'yaml',
  ['build_loki_config', {'retention': '12h'}],
  ('!ValueError', 'Строк зберігання має бути не меншим за 24 год')),
 ('S3',
  'yaml',
  ['build_loki_config', {'retention': '0h'}],
  ('!ValueError', 'Строк зберігання має бути не меншим за 24 год')),
 ('S3',
  'yaml',
  ['build_loki_config', {'retention': '100h'}],
  {'auth_enabled': False,
   'server': {'http_listen_port': 3100, 'grpc_listen_port': 9096},
   'common': {'instance_addr': '127.0.0.1',
              'path_prefix': '/loki',
              'storage': {'filesystem': {'chunks_directory': '/loki/chunks', 'rules_directory': '/loki/rules'}},
              'replication_factor': 1,
              'ring': {'kvstore': {'store': 'inmemory'}}},
   'schema_config': {'configs': [{'from': '2024-04-01',
                                  'store': 'tsdb',
                                  'object_store': 'filesystem',
                                  'schema': 'v13',
                                  'index': {'prefix': 'index_', 'period': '24h'}}]},
   'limits_config': {'retention_period': '100h', 'reject_old_samples': True, 'reject_old_samples_max_age': '168h'},
   'compactor': {'working_directory': '/loki/compactor',
                 'retention_enabled': True,
                 'delete_request_store': 'filesystem'},
   'analytics': {'reporting_enabled': False}})]


@pytest.mark.parametrize("tag,drv,args,expected", T07, ids=_ids(T07, "T07"))
def test_task_07(tag, drv, args, expected):
    run(7, drv, args, expected)
