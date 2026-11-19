"""Install the repository's exact official MoonBit archives into a new directory."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import stat
import subprocess
import tarfile
import tempfile
from urllib.parse import quote
from urllib.request import urlopen
import zipfile


ROOT = Path(__file__).resolve().parents[1]
OFFICIAL_CDN = 'https://cli.moonbitlang.com'


def download(relative_url, archive, expected):
    if not re.fullmatch(r'[0-9a-f]{64}', expected):
        raise ValueError('The toolchain archive digest must be an exact SHA-256')
    digest = hashlib.sha256()
    with urlopen(OFFICIAL_CDN + relative_url, timeout=60) as response, archive.open('xb') as output:
        for chunk in iter(lambda: response.read(1024 * 1024), b''):
            output.write(chunk)
            digest.update(chunk)
    if digest.hexdigest() != expected:
        raise ValueError(f'Toolchain archive checksum differs: {archive.name}')
    print(f'{archive.name} SHA-256 {expected}', flush=True)


def extract(archive, to):
    if archive.suffix == '.zip':
        with zipfile.ZipFile(archive) as package:
            for name in package.namelist():
                if not (to / name).resolve().is_relative_to(to.resolve()):
                    raise ValueError('Toolchain archive member would escape the installation')
            package.extractall(to)
    else:
        with tarfile.open(archive) as package:
            package.extractall(to, filter='data')


def install(home):
    lock = json.loads((ROOT / '.moonbit-toolchain.json').read_text(encoding='utf-8'))
    version = lock['compiler']
    if not re.fullmatch(r'\d+\.\d+\.\d+\+[0-9a-f]+', version):
        raise ValueError('The lock must select an exact stable MoonBit compiler build')
    system = platform.system().lower()
    if system not in ('windows', 'linux') or platform.machine().lower() not in ('amd64', 'x86_64'):
        raise ValueError('This installer has pinned archives for Windows and Linux x86-64')
    target = f'{system}-x86_64'
    windows = system == 'windows'
    suffix = '.exe' if windows else ''
    encoding = quote(version, safe='')
    home = home.absolute()
    if home.exists() or home.is_symlink():
        raise ValueError('Install into a new MoonBit home')
    home.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='moonbit-archives-', dir=home.parent) as temporary:
        directory = Path(temporary)
        binaries = directory / f"moonbit-{target}.{'zip' if windows else 'tar.gz'}"
        core = directory / 'core.tar.gz'
        download(f'/binaries/{encoding}/{binaries.name}', binaries, lock[target])
        download(f'/cores/core-{encoding}.tar.gz', core, lock['core'])
        home.mkdir()
        extract(binaries, home)
        extract(core, home / 'lib')

    bin_dir = home / 'bin'
    if not windows:
        if not (bin_dir / 'moonx').exists():
            (bin_dir / 'moonx').symlink_to('moon')
        for executable in [*bin_dir.iterdir(), bin_dir / 'internal/tcc']:
            if executable.is_file() and not executable.is_symlink():
                executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
    core_dir = home / 'lib/core'
    manifest = (core_dir / 'moon.mod').read_text(encoding='utf-8')
    if not re.search(r'^version\s*=\s*"' + re.escape(version) + r'"\s*$', manifest, re.MULTILINE):
        raise ValueError('The standard library must match the locked compiler build')
    env = dict(os.environ, MOON_HOME=str(home))
    env['PATH'] = str(bin_dir) + os.pathsep + env.get('PATH', '')
    compiler = subprocess.check_output([bin_dir / ('moonc' + suffix), '-v'], env=env, text=True).strip()
    if compiler.split()[0].removeprefix('v') != version:
        raise ValueError(f'Expected moonc {version}, got {compiler}')
    moon = bin_dir / ('moon' + suffix)
    subprocess.run([moon, '-C', core_dir, 'bundle', '--warn-list', '-a', '--all'], env=env, check=True)
    subprocess.run([moon, 'version', '--all'], env=env, check=True)
    return home


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home', type=Path, required=True)
    parser.add_argument('--github-env', action='store_true', help='Expose the installed toolchain to later Actions steps')
    arguments = parser.parse_args()
    home = install(arguments.home)
    if arguments.github_env:
        for key, line in [('GITHUB_ENV', 'MOON_HOME=' + str(home)), ('GITHUB_PATH', str(home / 'bin'))]:
            with open(os.environ[key], 'a', encoding='utf-8') as output:
                output.write(line + '\n')


if __name__ == '__main__':
    main()
