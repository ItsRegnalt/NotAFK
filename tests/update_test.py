"""Updater test with a fake GitHub (no network, nothing is started or replaced).
Usage: python tests/update_test.py"""
import hashlib
import io
import json
import os
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ui import updater

failures = 0


def check(name, ok, info=''):
    global failures
    failures += not ok
    print(('PASS ' if ok else 'FAIL ') + name, f'[{info}]' if info != '' else '')


pv = updater.parse_version
check('version compare', pv('v1.10.0') > pv('1.9.9') and pv('2') == (2, 0, 0) and pv('v1.0.1') > pv('1.0.0'))

buf = io.BytesIO()
with zipfile.ZipFile(buf, 'w') as z:
    z.writestr('NotAFK/NotAFK.exe', b'new exe')
    z.writestr('NotAFK/_internal/lib.dll', b'lib')
    z.writestr('../escape.txt', b'must stay inside')
package = buf.getvalue()
release = {'tag_name': 'v9.0.0', 'body': 'notes', 'html_url': 'https://example.invalid/r',
           'assets': [{'name': 'NotAFK-9.0.0.zip', 'browser_download_url': 'zip',
                       'digest': 'sha256:' + hashlib.sha256(package).hexdigest()}]}


class Resp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): self.close()


updater._get = lambda url, timeout=10: Resp(package if url == 'zip' else json.dumps(release).encode())
updater.GITHUB_REPO = 'someone/NotAFK'
info = updater.check()
check('newer release is offered', info['available'] and info['version'] == '9.0.0', info)

updater.VERSION = '9.0.0'
check('same version is not offered', not updater.check()['available'])
updater.VERSION = '1.0.0'

try:
    updater.install()
    check('install refuses outside the built EXE', False)
except RuntimeError as e:
    check('install refuses outside the built EXE', 'built app' in str(e), e)

install_dir = tempfile.mkdtemp()
started = []
sys.frozen, real_exe = True, sys.executable
sys.executable = os.path.join(install_dir, 'NotAFK.exe')
updater.subprocess.Popen = lambda args, **kw: started.append(args)
try:
    updater.check()
    version = updater.install()
    work = os.path.join(tempfile.gettempdir(), 'NotAFK-update')
    script = open(os.path.join(work, 'update.ps1'), encoding='utf-8-sig').read()
    check('install unpacks, writes the swap script and starts it',
          version == '9.0.0' and started and 'update.ps1' in started[0]
          and f"'{install_dir}'" in script and os.path.isfile(os.path.join(work, 'files', 'NotAFK', 'NotAFK.exe')))
    check('zip entries cannot escape the update folder', not os.path.exists(os.path.join(work, 'escape.txt')))
    release['assets'][0]['digest'] = 'sha256:' + '0' * 64
    updater.check()
    try:
        updater.install()
        check('damaged download is rejected', False)
    except RuntimeError as e:
        check('damaged download is rejected', 'checksum' in str(e), e)
finally:
    del sys.frozen
    sys.executable = real_exe

print('ALL PASS' if not failures else f'{failures} FAILED')
sys.exit(1 if failures else 0)
