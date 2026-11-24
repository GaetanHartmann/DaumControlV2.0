import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


spec = importlib.util.spec_from_file_location('display_boot', Path(__file__).parents[1] / 'deploy/display-boot.py')
boot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(boot)


def test_output_discovery_accepts_multiple_connectors_and_rejects_shell_text():
    assert boot.output_names('DP-2 off\nHDMI-A-2 on\nHDMI-A-2 on\n$(poweroff) off\nnoise\n') == ['DP-2', 'HDMI-A-2']


def test_recovery_restores_detected_outputs_and_only_display_units():
    runner = Mock()
    env = {'WAYLAND_DISPLAY': 'wayland-2', 'XDG_RUNTIME_DIR': '/run/user/1234'}
    commands = boot.recover(env, ['DP-2', 'HDMI-A-2'], runner, start_idle=True)
    assert commands[:3] == [['systemctl', '--user', 'stop', boot.BLANK], ['wlopm', '--on', 'DP-2'], ['wlopm', '--on', 'HDMI-A-2']]
    assert commands[-1] == ['systemctl', '--user', 'restart', boot.IDLE]
    assert all(call.args[1] is env for call in runner.call_args_list)
    assert not any('power-watch' in part or part == 'poweroff' for command in commands for part in command)


def test_dry_run_does_not_stop_services_or_change_outputs():
    runner = Mock()
    boot.recover({}, ['HDMI-A-2'], runner, start_idle=True, dry_run=True)
    runner.assert_not_called()


def test_missing_compositor_has_bounded_wait_and_no_output_mutation(monkeypatch, tmp_path):
    monkeypatch.setattr(boot, 'session_environment', Mock(side_effect=RuntimeError('socket missing')))
    clock = iter([0, 0, 1, 1, 2])
    runner, sleep = Mock(), Mock()
    with pytest.raises(RuntimeError, match='Display-Start abgebrochen'):
        boot.wait_for_outputs({}, tmp_path, 1, runner, lambda: next(clock), sleep)
    runner.assert_not_called()


def test_compositor_is_retried_before_detected_output_is_used(monkeypatch, tmp_path):
    env = {'WAYLAND_DISPLAY': 'wayland-4'}
    monkeypatch.setattr(boot, 'session_environment', Mock(side_effect=[RuntimeError('not ready'), env]))
    runner = Mock(return_value=SimpleNamespace(stdout='HDMI-A-3 off\n'))
    assert boot.wait_for_outputs({}, tmp_path, 2, runner, now=lambda: 0, sleep=Mock()) == (env, ['HDMI-A-3'])


def test_installer_preserves_300_second_idle_and_lan_timer():
    text = (Path(__file__).parents[1] / 'deploy/install-display-idle.py').read_text(encoding='utf-8')
    assert 'timeout 300' in text
    assert 'ExecStartPre=' in text
    assert '--start-idle' in text
    assert 'WAYLAND_DISPLAY=wayland-0' not in text
    assert 'poweroff' not in text
