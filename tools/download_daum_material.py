"""Download pinned reference material for inspection; never imports/runs it.

Run from any directory: python tools/download_daum_material.py
References remain in the ignored local cache. Vendor documents do not inherit
the license of a repository that happens to contain them.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / '.cache' / 'fitness-material' / 'daum'
MAX_BYTES = 2_000_000
INCYCLIST = 'a77985fc581d35670af83c604cd41643a1c204f1'
PREMIUM = '546e13f6d0db9992644fbe18154e9f070cae0d7c'
QZ = '6d6bb41fa58ba2485d5e6f30385cf71809717aa7'
ERGOFACE = '6cd85cd093cb86c590a78f749346057ba515e16d'


def reference(name: str, repository: str, revision: str, path: str,
              license_state: str, sha256: str = '') -> dict:
    return dict(name=name, repository=repository, revision=revision, path=path,
                url=f'https://raw.githubusercontent.com/{repository}/{revision}/{path}',
                source_url=f'https://github.com/{repository}/blob/{revision}/{path}',
                license_state=license_state, sha256=sha256)


MATERIAL = [
    reference('SP-KOMM-PM1.pdf', 'sta-hems/daumUSB2BLE', PREMIUM,
              'manual/SP-KOMM-PM1.pdf',
              'daum electronic manufacturer document; redistribution permission unverified; local reference only'),
    reference('incyclist-utils.ts', 'incyclist/devices', INCYCLIST,
              'src/serial/daum/premium/utils.ts', 'MIT; retain accompanying license'),
    reference('incyclist-utils.unit.test.ts', 'incyclist/devices', INCYCLIST,
              'src/serial/daum/premium/utils.unit.test.ts', 'MIT; retain accompanying license'),
    reference('incyclist-LICENSE.txt', 'incyclist/devices', INCYCLIST, 'LICENSE', 'MIT'),
    reference('premium-daumPremium.js', 'sta-hems/daumUSB2BLE', PREMIUM,
              'USB/daumPremium.js', 'MIT; retain accompanying license'),
    reference('premium-protocol-tests.js', 'sta-hems/daumUSB2BLE', PREMIUM,
              'test/daumPremium_test_protocol.js', 'MIT; retain accompanying license'),
    reference('premium-README.md', 'sta-hems/daumUSB2BLE', PREMIUM,
              'README.md', 'repository MIT; author implementation claims require separate hardware verification'),
    reference('premium-LICENSE.txt', 'sta-hems/daumUSB2BLE', PREMIUM, 'LICENSE', 'MIT'),
    reference('qz-DaumUSB.cpp', 'cagnulein/qdomyos-zwift', QZ,
              'src/devices/daumbike/DaumUSB.cpp', 'GPL-2.0-or-later according to file header'),
    reference('ergoface-rs232.py', 'weinzmi/ergoFACE', ERGOFACE,
              'src/rs232.py', 'MPL-2.0 according to repository LICENSE'),
    reference('ergoface-LICENSE.txt', 'weinzmi/ergoFACE', ERGOFACE, 'LICENSE', 'MPL-2.0'),
]

# Recorded after inspecting the original bytes on 2026-11-09. URLs are also
# pinned to commits; changed bytes fail before an existing cache is replaced.
SHA256 = {
    'SP-KOMM-PM1.pdf': '11f521eaf0d3078ce4923741c50ccfde5ef7dcc28252087d8601e9caa53de4f9',
    'incyclist-utils.ts': 'e9af6720b90fe58d88b6099493fd2e27d36506b6d8d9df96e001d7a213c1c84e',
    'incyclist-utils.unit.test.ts': 'bacef07f590007cc9a26de0159b2635fe85f0dc09c3a142e266572ab7ec79d0b',
    'incyclist-LICENSE.txt': '78d2b03fae02a9630128d7cd45da678e52571a57f3b00bf41b29b35f65d7a3ee',
    'premium-daumPremium.js': '7263fad299351e62096d3d75570cdf53d5a7fa0dfb522cdcd90d22d05d4e54bd',
    'premium-protocol-tests.js': '78ee98e1922a7e981b25b5604fe6f5c41ba1fbbc52217ad72e528932b846ef3f',
    'premium-README.md': '6a03a66e95d0d8bbc805dfde96fe6609dec64c34f7f6f0d133487cac87700faf',
    'premium-LICENSE.txt': 'd6dc3a5ab0e92ba2d896c65c9d285d77b78d52bac03da27461af8924df71a33a',
    'qz-DaumUSB.cpp': '038222e83c7a6955e508a7b944a3096a350343d7da2877ca3e919989c7f5634e',
    'ergoface-rs232.py': '4f9247c82491e20296c7ba276e451035f23d55817bd46a7ff7271509c8355050',
    'ergoface-LICENSE.txt': '2684de17300e0a434686f1ec7f8af6045207a4b457a3fe04b2b9ce655e7c5d50',
}
for _item in MATERIAL:
    _item['sha256'] = SHA256[_item['name']]


def download(item: dict, destination: Path, *, opener=urlopen) -> dict:
    """Validate a complete response before replacing a cached reference."""
    name = item['name']
    if Path(name).name != name or '/' in name or '\\' in name or name in ('.', '..'):
        raise ValueError('Reference filename must not contain a path')
    request = Request(item['url'], headers={'User-Agent': 'Fitness-Cockpit-reference-downloader/1.0'})
    with opener(request, timeout=20) as response:
        final_url = response.geturl()
        if not final_url.startswith('https://raw.githubusercontent.com/'):
            raise ValueError('Unexpected download redirect')
        content = response.read(MAX_BYTES + 1)
        content_type = response.headers.get('Content-Type', '')
    if not content or len(content) > MAX_BYTES:
        raise ValueError('Reference is empty or exceeds the size limit')
    if name.endswith('.pdf'):
        if not content.startswith(b'%PDF-'):
            raise ValueError('Expected PDF but received another document')
    else:
        content.decode('utf-8')
        if content.lstrip().lower().startswith((b'<!doctype html', b'<html')):
            raise ValueError('Expected source text but received HTML')
    digest = hashlib.sha256(content).hexdigest()
    if item.get('sha256') and digest != item['sha256']:
        raise ValueError('Reference checksum differs from the recorded version')
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / name
    temporary = target.with_name(target.name + '.part')
    try:
        temporary.write_bytes(content)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return dict(item, sha256=digest, bytes=len(content), final_url=final_url,
                content_type=content_type, downloaded_at=datetime.now(timezone.utc).isoformat())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=CACHE)
    args = parser.parse_args()
    records = []
    failures = []
    for item in MATERIAL:
        try:
            record = download(item, args.output)
            records.append(record)
            print(f"OK {record['name']}: {record['bytes']} bytes; SHA256 {record['sha256']}")
        except (OSError, ValueError) as error:
            failures.append(dict(name=item['name'], url=item['url'], error=str(error)))
            print(f"FAILED {item['name']}: {error}")
    args.output.mkdir(parents=True, exist_ok=True)
    manifest = dict(references=records, failures=failures, executed_downloads=False)
    (args.output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
