"""Updates from GitHub Releases.

check() asks the GitHub API for the latest release of version.GITHUB_REPO. install() downloads its .zip
asset (checked against the SHA-256 digest GitHub publishes for it), unpacks it next to nothing the user
owns (%TEMP%), and starts a small script that waits for NotAFK to exit, copies the new files over the
install folder and starts NotAFK again. User data lives in %LOCALAPPDATA%\\NotAFK, so it is never touched."""
import ctypes
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

from version import GITHUB_REPO, VERSION

EXE = 'NotAFK.exe'
_latest = None  # last release seen by check(), used by install()


def parse_version(text):
    """'v1.2.10' -> (1, 2, 10); missing parts count as 0."""
    parts = [int(n) for n in re.findall(r'\d+', str(text))[:3]]
    return tuple(parts + [0] * (3 - len(parts)))


def _get(url, timeout=10):
    req = urllib.request.Request(url, headers={'User-Agent': 'NotAFK-updater', 'Accept': 'application/vnd.github+json'})
    return urllib.request.urlopen(req, timeout=timeout)


def check():
    """{'available', 'current', 'version', 'notes', 'page', 'canInstall'}; raises on network errors."""
    global _latest
    info = {'available': False, 'current': VERSION}
    if not GITHUB_REPO:
        return info
    with _get(f'https://api.github.com/repos/{GITHUB_REPO}/releases/latest') as r:
        data = json.load(r)
    asset = next((a for a in data.get('assets', []) if a.get('name', '').lower().endswith('.zip')), None)
    version = str(data.get('tag_name', '')).lstrip('vV')
    _latest = {'version': version, 'asset': asset}
    info.update(version=version, notes=(data.get('body') or '')[:800], page=data.get('html_url', ''),
                available=bool(asset) and parse_version(version) > parse_version(VERSION),
                canInstall=bool(getattr(sys, 'frozen', False)))
    return info


def _writable(folder):
    try:
        probe = tempfile.NamedTemporaryFile(dir=folder, delete=True)
        probe.close()
        return True
    except OSError:
        return False


def install():
    """Download + unpack the latest release and start the swap script. The caller must then exit NotAFK."""
    if not getattr(sys, 'frozen', False):
        raise RuntimeError('Updates install in the built app (NotAFK.exe) only.')
    if not _latest or not _latest['asset']:
        raise RuntimeError('No update found. Check for updates first.')
    asset = _latest['asset']
    work = os.path.join(tempfile.gettempdir(), 'NotAFK-update')
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)
    package = os.path.join(work, 'package.zip')
    digest = hashlib.sha256()
    with _get(asset['browser_download_url'], timeout=60) as r, open(package, 'wb') as f:
        for chunk in iter(lambda: r.read(1 << 16), b''):
            digest.update(chunk)
            f.write(chunk)
    expected = str(asset.get('digest') or '')
    if expected.startswith('sha256:') and expected[7:].lower() != digest.hexdigest():
        raise RuntimeError('The download is damaged (checksum mismatch). Try again later.')
    unpacked = os.path.join(work, 'files')
    with zipfile.ZipFile(package) as z:
        z.extractall(unpacked)  # zipfile drops absolute paths and '..' parts
    source = next((root for root, _, files in os.walk(unpacked) if EXE in files), None)
    if not source:
        raise RuntimeError(f'The update package has no {EXE}.')
    target = os.path.dirname(sys.executable)
    script = os.path.join(work, 'update.ps1')
    q = lambda path: "'" + path.replace("'", "''") + "'"  # noqa: E731  PowerShell literal string
    # PowerShell + UTF-8 BOM: a .cmd file is read in the OEM code page and breaks non-ASCII paths (e.g. a user name with ğ)
    with open(script, 'w', encoding='utf-8-sig') as f:
        f.write(f'Wait-Process -Id {os.getpid()} -ErrorAction SilentlyContinue\n'
                f'robocopy {q(source)} {q(target)} /E /R:5 /W:1 | Out-Null\n'
                f'Start-Process -FilePath {q(os.path.join(target, EXE))}\n')
    args = f'-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{script}"'
    if _writable(target):
        subprocess.Popen(f'powershell.exe {args}', creationflags=0x08000000 | 0x00000200,  # NO_WINDOW|NEW_GROUP
                         cwd=work, close_fds=True)
    else:  # installed under Program Files: the copy needs administrator rights
        shell32 = ctypes.windll.shell32
        shell32.ShellExecuteW.restype = ctypes.c_void_p
        if (shell32.ShellExecuteW(None, 'runas', 'powershell.exe', args, work, 0) or 0) <= 32:
            raise RuntimeError('The update needs administrator rights, and the request was cancelled.')
    return _latest['version']
