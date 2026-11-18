"""DPI / multi-monitor test for the screen picker. Runs hidden: no window is shown, no real input.
Usage: python tests/dpi_test.py

Checks the process is per-monitor DPI aware, the picker covers every monitor in real pixels, the HUD and the
crosshair scale with each monitor's DPI (a 150% monitor is simulated next to the real ones), and the HUD is
always wide enough for its text."""
import ctypes
import ctypes.wintypes as wt
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ui.webview_shell  # noqa: F401  (sets per-monitor DPI awareness, like the app)
from ui import picker
from core.background import screen_pixel

user32 = ctypes.windll.user32
failures = 0


def check(name, ok, info=''):
    global failures
    failures += not ok
    print(('PASS ' if ok else 'FAIL ') + name, f'[{info}]' if info != '' else '')


user32.GetThreadDpiAwarenessContext.restype = ctypes.c_void_p
user32.AreDpiAwarenessContextsEqual.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
ctx = user32.GetThreadDpiAwarenessContext()
check('process is per-monitor DPI aware (v2)', bool(user32.AreDpiAwarenessContextsEqual(ctx, ctypes.c_void_p(-4))))

monitors = []
MONITORENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(wt.RECT), ctypes.c_void_p)


def on_monitor(_h, _dc, rect, _l):
    r = rect.contents
    cx, cy = (r.left + r.right) // 2, (r.top + r.bottom) // 2
    monitors.append({'rect': (r.left, r.top, r.right, r.bottom), 'center': (cx, cy), 'dpi': picker.monitor_dpi(cx, cy)})
    return 1


user32.EnumDisplayMonitors(None, None, MONITORENUMPROC(on_monitor), 0)
print('monitors:', [(m['rect'], m['dpi']) for m in monitors])
for m in monitors:
    check(f"pixel color readable on monitor {m['rect']}", screen_pixel(*m['center']).startswith('#'))

# HUD size: always fits the text, grows with the DPI
hint = 'Left click: pick  ·  Esc / right click: cancel'
coords = 'X: -99999   Y: -99999   #FFFFFF'
sizes = {dpi: picker.hud_layout(hint, coords, dpi) for dpi in (96, 120, 144, 192)}
for dpi, (w, h, font_px, scale) in sizes.items():
    hint_w = picker.hud_layout(hint, '', dpi)[0]  # hint text + padding
    coords_w = picker.hud_layout('', coords, dpi)[0]  # swatch + coordinates + padding
    check(f'HUD at {dpi} dpi is wide enough for its text', w >= max(hint_w, coords_w), (w, h, font_px))
w96, w192 = sizes[96][0], sizes[192][0]
# text widths are not exactly linear (font hinting), the height is
check('HUD at 200% is about twice as large as at 100%', 1.7 <= w192 / w96 <= 2.1 and sizes[192][1] == 2 * sizes[96][1], (w96, w192))

# Picker windows (hidden) across the whole virtual desktop, with a simulated 150% monitor
done = threading.Event()
pk = picker.ScreenPicker(lambda r: done.set(), visible=False)
pk.start()
for _ in range(100):
    if pk.hud:
        break
    time.sleep(0.02)
time.sleep(0.1)
vx, vy, vw, vh = (user32.GetSystemMetrics(i) for i in (76, 77, 78, 79))
r = wt.RECT()
user32.GetWindowRect(pk.overlay, ctypes.byref(r))
check('picker overlay covers every monitor (virtual desktop, real pixels)',
      (r.left, r.top, r.right - r.left, r.bottom - r.top) == (vx, vy, vw, vh)
      and all(r.left <= m['rect'][0] and r.top <= m['rect'][1] and r.right >= m['rect'][2] and r.bottom >= m['rect'][3]
              for m in monitors), (r.left, r.top, r.right, r.bottom))

real_dpi = picker.monitor_dpi
fake = monitors[-1]  # pretend the last monitor runs at 150%
picker.monitor_dpi = lambda x, y: 144 if (fake['rect'][0] <= x < fake['rect'][2] and fake['rect'][1] <= y < fake['rect'][3]) \
    else real_dpi(x, y)
results = []
for m in monitors:
    x, y = m['center']
    pk._cursor = lambda x=x, y=y: (x, y)
    pk._update_hud()
    time.sleep(0.05)
    hr = wt.RECT()
    user32.GetWindowRect(pk.hud, ctypes.byref(hr))
    left, right, top, bottom = pk.segments
    gap = round(picker.LINE_GAP * pk.scale)
    crosshair_ok = (left[0] + left[2] == x - gap and right[0] == x + gap + 1 and left[1] == right[1] == y
                    and top[1] + top[3] == y - gap and bottom[1] == y + gap + 1 and top[0] == bottom[0] == x)
    results.append((m, pk.scale, pk._font_px, hr.right - hr.left))
    check(f"monitor {m['rect']}: crosshair meets at the cursor, HUD inside the desktop",
          crosshair_ok and hr.left >= vx and hr.top >= vy and hr.right <= vx + vw and hr.bottom <= vy + vh,
          (x, y, pk.scale))
picker.monitor_dpi = real_dpi
if len(monitors) > 1:
    big = next(x for x in results if x[0] is fake)
    small = next(x for x in results if x[0] is not fake)
    check('moving to the 150% monitor makes the HUD font and size 1.5x',
          big[1] == 1.5 and big[2] == round(13 * 1.5) and 1.3 <= big[3] / (small[3] / small[1]) <= 1.7,
          (small[1:], big[1:]))
pk.cancel()
check('picker closes on cancel', done.wait(3))

print('ALL PASS' if not failures else f'{failures} FAILED')
sys.exit(1 if failures else 0)
