"""Fetch the immutable public v0.0.6 benchmark core and verify its pinned bytes."""
import argparse
import hashlib
import io
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORE_SHA256 = '0f568f483ef2f88b11aab6ac3ee63c7e8fbdb946aefcd2a1d7da583d6bc0aa9d'
URL = 'https://github.com/HhWw96/moontxnwitness/releases/download/v0.0.6/MoonTxnWitness-v0.0.6-portable.zip'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--destination', default=str(ROOT / 'artifacts/baseline-v0.0.6/core.mjs'))
    args = parser.parse_args()
    destination = Path(args.destination)
    if destination.exists():
        assert hashlib.sha256(destination.read_bytes()).hexdigest() == CORE_SHA256, 'Existing baseline differs from pinned public core'
    else:
        request = urllib.request.Request(URL, headers={'User-Agent': 'MoonTxnWitness-performance-baseline'})
        with urllib.request.urlopen(request, timeout=60) as response:
            assert response.status == 200
            packed = response.read(16 * 1024 * 1024 + 1)
            assert len(packed) <= 16 * 1024 * 1024
        with zipfile.ZipFile(io.BytesIO(packed)) as archive:
            core = archive.read('MoonTxnWitness-v0.0.6/dist/core.mjs')
        assert hashlib.sha256(core).hexdigest() == CORE_SHA256, 'Public baseline core digest mismatch'
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open('xb') as output:
            output.write(core)
    print('Verified immutable public v0.0.6 performance baseline: ' + CORE_SHA256)


if __name__ == '__main__':
    main()
