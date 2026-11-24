"""Create a local checksummed Pi artifact; never includes databases or keys."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tarfile


REQUIRED_BACKEND = ('main.py', 'devices.py', 'connectors.py', 'metrics.py', 'cockpit.py',
                    'catalog.py', 'coach.py', 'routes.py', 'routes_material.py', 'training.py')


def verify_payload(root, files):
    """Fail before archiving an incomplete catalog/control deployment."""
    names = {path.relative_to(root).as_posix() for path in files}
    required = {'backend/'+name for name in REQUIRED_BACKEND}
    required.add('frontend/dist/index.html')
    required.add('data/routes/index.json')
    required.add('data/routes/LICENSE.md')
    if not required <= names:
        raise ValueError('Paket unvollständig: ' + ', '.join(sorted(required-names)))
    for path in files:
        if path.is_symlink() or root not in path.resolve().parents:
            raise ValueError('Verknüpfte Datei außerhalb des Pakets nicht übernehmen')
    return names


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path, help='Absolute destination .tar.gz outside the checkout')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    if root in output.parents or not output.name.endswith('.tar.gz'):
        parser.error('Archiv außerhalb des bike-Verzeichnisses als .tar.gz angeben')
    files = sorted(root.joinpath('backend').glob('*.py'))
    files += sorted(p for p in root.joinpath('frontend/dist').rglob('*') if p.is_file())
    files += sorted(root.joinpath('data/routes').glob('*.json'))
    files += [root / 'data/routes/LICENSE.md']
    files += [root / 'README.md', root / 'requirements.txt']
    files += [root / 'deploy' / name for name in ['install-cockpit-update.py', 'package-cockpit-update.py', 'install-display-idle.py', 'display-boot.py', 'display-black-overlay.py', 'daum-power-watch.py', 'fetch-route-material.py']]
    files += sorted(p for p in root.joinpath('tests').glob('test_*.py') if p.name != 'test_native_spike.py')
    # Imported by test_power_probe; execution stays behind its explicit CLI guard.
    files += [root / 'tests/pi_power_control_smoke.py']
    if not (root / 'frontend/dist/index.html').is_file():
        parser.error('Zuerst das Frontend bauen')
    try:
        verify_payload(root, files)
    except ValueError as error:
        parser.error(str(error))
    payload = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    manifest = json.dumps(dict(format_version=1, created_at=datetime.now(timezone.utc).isoformat(),
        feature_set=['catalog', 'live_target_override', 'coach', 'routes_foundation',
                     'verified_power_provenance', 'daum_s23_value_echo',
                     'fullscreen_timeline', 'fullscreen_metrics', 'offline_real_routes'], files=payload), indent=2).encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output, 'w:gz') as archive:
        for path in files:
            archive.add(path, arcname=path.relative_to(root).as_posix(), recursive=False)
        import io
        entry = tarfile.TarInfo('manifest.json')
        entry.size = len(manifest)
        archive.addfile(entry, io.BytesIO(manifest))
    print(json.dumps(dict(archive=str(output), files=len(files), sha256=hashlib.sha256(output.read_bytes()).hexdigest())))


if __name__ == '__main__':
    main()
