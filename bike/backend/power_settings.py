"""Shared on/off setting for the separately installed Pi power watcher."""
import json
import os
from pathlib import Path
import tempfile


def read_settings(path: Path):
    enabled = False
    try:
        enabled = json.loads(path.read_text())['enabled'] is True
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return dict(available=path.is_file(), enabled=enabled, delay_seconds=300)


def save_settings(path: Path, enabled: bool):
    if not path.is_file():
        raise ValueError('Abschaltautomatik ist auf diesem Gerät noch nicht installiert.')
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as file:
            temporary = Path(file.name)
            json.dump({'enabled': enabled}, file)
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()
    return read_settings(path)
