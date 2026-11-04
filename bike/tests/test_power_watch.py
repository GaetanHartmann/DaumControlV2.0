import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest


spec = importlib.util.spec_from_file_location('daum_power_watch', Path(__file__).parents[1] / 'deploy' / 'daum-power-watch.py')
watch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watch)


def test_power_watch_waits_and_resets_on_reconnection_or_unknown_link():
    timer = watch.LinkTimer(300)
    assert not timer.update(False, 0)
    assert not timer.update(False, 299)
    assert timer.update(False, 300)
    assert not timer.update(True, 301)
    assert not timer.update(False, 400)
    assert not timer.update(None, 650)
    assert not timer.update(False, 700)
    assert not timer.update(False, 999)
    assert timer.update(False, 1000)


def test_missing_carrier_never_means_bike_off(tmp_path):
    path = tmp_path / 'carrier'
    assert watch.read_carrier(path) is None
    for text, expected in [('0', False), ('1', True), ('unknown', None)]:
        path.write_text(text)
        assert watch.read_carrier(path) is expected


def test_watch_requires_confirmed_stop_before_shutdown():
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self):
            return b'{"running": true}'

    with patch.object(watch, 'urlopen', return_value=Response()):
        with pytest.raises(RuntimeError):
            watch.stop_training('http://127.0.0.1:8000')


def test_auto_off_is_disabled_for_missing_or_invalid_configuration(tmp_path):
    config = tmp_path / 'power.json'
    assert not watch.auto_off_enabled(config)
    for value, expected in [('{}', False), ('{"enabled": "yes"}', False),
                            ('{"enabled": false}', False), ('{"enabled": true}', True)]:
        config.write_text(value)
        assert watch.auto_off_enabled(config) is expected
