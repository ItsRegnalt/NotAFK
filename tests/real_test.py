"""Real mouse / keyboard test (B list). DRIVES THE REAL MOUSE AND KEYBOARD: don't touch them while it runs.
Uses its own visible test window (tests/real_target.py, nothing is saved), the desktop (creates two
NotAFK_test_* folders, drags one into the other, then deletes both), the screen picker on every monitor,
and Spotify in Background Mode (Space twice = play, then pause again; nothing is deleted).
Usage: python tests/real_test.py"""
import ctypes, ctypes.wintypes as wt, json, os, shutil, subprocess, sys, threading, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ui.webview_shell as shell  # noqa: E402  (per-monitor DPI aware, like the app)
from pynput import keyboard, mouse  # noqa: E402
from core.background import window_rect, window_title  # noqa: E402

user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
user32.SendMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.SendMessageW.restype = ctypes.c_ssize_t
KB, MS = keyboard.Controller(), mouse.Controller()
failures = 0


def check(name, ok, info=''):
    global failures
    failures += not ok
    print(('PASS ' if ok else 'FAIL ') + name, f'[{info}]' if info != '' else '', flush=True)


def cursor():
    pt = wt.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def run(steps, **cfg):
    """Run steps with the real engine (same JSON the UI sends); returns (finished_ok, statuses)."""
    config = {"steps": steps, "runMode": "once", "globalDelayEnabled": False, "targetJitter": "0", "curvePercent": 20,
              "mouseSpeed": "1,5", **cfg}
    worker = shell.build_worker(config)
    done, result, statuses = threading.Event(), [], []
    worker.execution_finished.connect(lambda ok: (result.append(ok), done.set()))
    worker.status_changed.connect(statuses.append)
    worker.start()
    done.wait(cfg.get('_timeout', 40))
    return (result[0] if result else None), statuses


# --- test window ---------------------------------------------------------------------------------------
proc = subprocess.Popen([sys.executable, os.path.join(os.path.dirname(__file__), 'real_target.py'), '300', '200', '760', '520'],
                        stdout=subprocess.PIPE, text=True)
_, MAIN, EDIT = proc.stdout.readline().split()
MAIN, EDIT = int(MAIN), int(EDIT)
time.sleep(0.5)


def text():
    n = user32.SendMessageW(EDIT, 0x0E, 0, 0)  # WM_GETTEXTLENGTH
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.SendMessageW(EDIT, 0x0D, n + 1, ctypes.addressof(buf))  # WM_GETTEXT
    return buf.value


def set_text(value):
    buf = ctypes.create_unicode_buffer(value)
    user32.SendMessageW(EDIT, 0x0C, 0, ctypes.addressof(buf))  # WM_SETTEXT


def char_point(i):
    pos = user32.SendMessageW(EDIT, 0xD6, i, 0)  # EM_POSFROMCHAR
    pt = wt.POINT(ctypes.c_short(pos & 0xFFFF).value, ctypes.c_short((pos >> 16) & 0xFFFF).value)
    user32.ClientToScreen(EDIT, ctypes.byref(pt))
    return pt.x, pt.y + 10


def at(i, dx=0):
    x, y = char_point(i)
    return {"x": x + dx, "y": y}


def click(i, **extra):
    return {"id": f"c{i}{time.time()}", "enabled": True, "type": "click", "coords": at(i, 1), "button": "Left click",
            "times": "1", **extra}


def typed(value, **extra):
    return {"id": f"t{value}{time.time()}", "enabled": True, "type": "text", "textValue": value, "keyDelay": "0,02", **extra}


def key(name, mods=(), **extra):
    return {"id": f"k{name}{time.time()}", "enabled": True, "type": "key", "keyName": name, "keyMode": "press",
            "modifiers": list(mods), **extra}


try:
    # B1: click, text, Enter, Ctrl+End, scroll, move, long press, drag-select ------------------------------
    set_text('0123456789\r\n' + '\r\n'.join(f'line {i}' for i in range(1, 120)))
    ok, _ = run([click(10), typed('ABC'), key('Enter'), typed('x'), key('End', ['Ctrl']), typed('END')])
    t = text()
    check('B1 click + text + Enter + Ctrl+End', ok and t.startswith('0123456789ABC\r\nx\r\nline 1') and t.endswith('line 119END'),
          repr(t[:24]) + ' ... ' + repr(t[-12:]))

    user32.SendMessageW(EDIT, 0xB6, 0, -1000)  # EM_LINESCROLL back to the top
    rc = window_rect(EDIT)
    mid = {"x": (rc.left + rc.right) // 2, "y": (rc.top + rc.bottom) // 2}
    ok, _ = run([{"id": "s", "enabled": True, "type": "scroll", "coords": mid, "amount": "-5"}])
    first = user32.SendMessageW(EDIT, 0xCE, 0, 0)  # EM_GETFIRSTVISIBLELINE
    check('B1 scroll 5 notches down over the text', ok and first >= 5, first)

    ok, _ = run([{"id": "m", "enabled": True, "type": "move", "coords": {"x": mid["x"] + 40, "y": mid["y"] - 30}}])
    check('B1 move ends on the target point', ok and cursor() == (mid["x"] + 40, mid["y"] - 30), cursor())

    presses = []
    listener = mouse.Listener(on_click=lambda x, y, b, p: presses.append((p, time.time())))
    listener.start()
    time.sleep(0.2)
    set_text('0123456789')
    ok, _ = run([click(3, holdTime='0,6')])
    listener.stop()
    held = presses[-1][1] - presses[-2][1] if len(presses) >= 2 and presses[-2][0] and not presses[-1][0] else 0
    check('B1 click Hold keeps the button down ~0.6 s', ok and 0.55 <= held <= 0.9, round(held, 2))

    set_text('0123456789')
    ok, _ = run([{"id": "d", "enabled": True, "type": "drag", "coords": at(0), "to": at(5), "button": "Left click",
                  "duration": "0,5"}, typed('Z')])
    check('B1 drag selects text (typing replaces the selection)', ok and text() == 'Z56789', repr(text()))

    # B6: run settings ----------------------------------------------------------------------------------
    set_text('')
    run([click(0)])  # click once: a click repeated on the same spot would be a double click (selects the word)
    run([typed('a')], runMode='repeat', repeatCount=3)
    check('B6 repeat 3 times', text() == 'aaa', repr(text()))
    set_text('')
    run([click(0), typed('b', chance='0'), typed('c')])
    check('B6 chance 0% skips the step', text() == 'c', repr(text()))
    set_text('')
    run([click(0), {"id": "L", "enabled": True, "type": "loop", "times": "4"}, typed('r'),
         {"id": "L-end", "enabled": True, "type": "loopEnd", "loopOwnerId": "L"}, typed('!')])
    check('B6 repeat block runs its body 4 times', text() == 'rrrr!', repr(text()))
    t0 = time.time()
    ok, statuses = run([{"id": "w", "enabled": True, "type": "delay", "duration": "0,4"}], runMode='loop', timeLimit='0,05')
    check('B6 Stop after 0.05 min ends a loop after ~3 s', ok and 2.5 <= time.time() - t0 <= 5
          and any('Time limit' in s for s in statuses), round(time.time() - t0, 1))

    # B3: Record real input, then replay it -----------------------------------------------------------------
    class FakeShell:
        def _hwnd(self): return 0
        def _hotkey_name(self, key): return None
        def _emit(self, *a): pass

    set_text('')
    rec = shell.Recorder(FakeShell())
    rec.start()
    time.sleep(0.5)
    MS.position = char_point(0)
    MS.click(mouse.Button.left)
    time.sleep(0.5)
    MS.press(mouse.Button.left); time.sleep(0.6); MS.release(mouse.Button.left)  # long press
    time.sleep(0.5)
    MS.press(mouse.Button.left)
    for i in range(1, 9):
        MS.position = (char_point(0)[0] + i * 10, char_point(0)[1]); time.sleep(0.03)
    MS.release(mouse.Button.left)  # drag
    time.sleep(0.5)
    KB.type('hello')
    time.sleep(1.3)
    with KB.pressed(keyboard.Key.ctrl):
        KB.press('a'); KB.release('a')
    time.sleep(0.6)
    KB.type('bye')
    time.sleep(1.3)
    MS.position = (mid["x"], mid["y"])
    MS.scroll(0, -2)
    time.sleep(0.6)
    steps = rec.stop()
    recorded_text = text()
    kinds = [s['type'] for s in steps if s['type'] != 'delay']
    hold = next((s for s in steps if s['type'] == 'click' and s.get('holdTime', '0') != '0'), {})
    check('B3 record: click, long press, drag, text, Ctrl+A, text, scroll',
          kinds == ['click', 'click', 'drag', 'text', 'key', 'text', 'scroll']
          and [s.get('textValue') for s in steps if s['type'] == 'text'] == ['hello', 'bye']
          and next(s for s in steps if s['type'] == 'key').get('modifiers') == ['Ctrl']
          and 0.5 <= float(hold.get('holdTime', '0').replace(',', '.')) <= 0.9, json.dumps([s for s in steps if s['type'] != 'delay'])[:600])
    set_text('')
    ok, _ = run(steps, _timeout=60)
    check('B3 replaying the recording gives the same result', ok and text() == recorded_text == 'bye', (repr(recorded_text), repr(text())))

    # B7: Background Mode into the test window: real cursor and foreground stay where they are --------------
    set_text('0123456789')
    r = window_rect(MAIN)
    p5 = char_point(5)
    MS.position = (50, 50)
    fg = user32.GetForegroundWindow()
    ok, _ = run([{"id": "bc", "enabled": True, "type": "click", "button": "Left click", "times": "1",
                  "coords": {"x": 0, "y": 0, "rel": {"x": p5[0] - r.left, "y": p5[1] - r.top}}}, typed('BG')],
                backgroundEnabled=True, targetHwnd=MAIN)
    check('B7 background click + text land in the target window', ok and text() == '01234BG56789', repr(text()))
    check('B7 background run did not move the real cursor or change focus',
          cursor() == (50, 50) and user32.GetForegroundWindow() == fg, cursor())
finally:
    user32.PostMessageW(MAIN, 0x10, 0, 0)
    proc.wait(10)

# B4: picker on every monitor, Esc / right-click cancel ------------------------------------------------------
from ui.picker import ScreenPicker  # noqa: E402

monitors = []
CB = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(wt.RECT), ctypes.c_void_p)
user32.EnumDisplayMonitors(None, None, CB(lambda h, d, rc, l: monitors.append(
    ((rc.contents.left + rc.contents.right) // 2 + 37, (rc.contents.top + rc.contents.bottom) // 2 - 23)) or 1), 0)


def pick(action):
    got, done = [], threading.Event()
    p = ScreenPicker(lambda r: (got.append(r), done.set()))
    p.start()
    time.sleep(0.6)
    action()
    done.wait(5)
    return got[0] if got else 'timeout'


for point in monitors:
    MS.position = point
    result = pick(lambda: (time.sleep(0.2), MS.click(mouse.Button.left)))
    check(f'B4 picker returns the exact point on monitor at {point}', result == point, result)
check('B4 Esc cancels the picker', pick(lambda: (KB.press(keyboard.Key.esc), KB.release(keyboard.Key.esc))) is None)
check('B4 right click cancels the picker', pick(lambda: MS.click(mouse.Button.right)) is None)

# B2: drag a desktop folder into another one ------------------------------------------------------------
buf = ctypes.create_unicode_buffer(260)
ctypes.windll.shell32.SHGetFolderPathW(None, 0x10, None, 0, buf)  # CSIDL_DESKTOPDIRECTORY
desk = buf.value
src, dst = os.path.join(desk, 'NotAFK_test_drag'), os.path.join(desk, 'NotAFK_test_target')
os.makedirs(src, exist_ok=True)
os.makedirs(dst, exist_ok=True)
time.sleep(2)


def desktop_listview():
    found = []
    def visit(hwnd, _):
        view = user32.FindWindowExW(hwnd, None, 'SHELLDLL_DefView', None)
        if view:
            found.append(user32.FindWindowExW(view, None, 'SysListView32', None))
        return 1
    user32.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_int, wt.HWND, wt.LPARAM)(visit), 0)
    return next((h for h in found if h), None)


class LVITEMW(ctypes.Structure):
    _fields_ = [('mask', wt.UINT), ('iItem', ctypes.c_int), ('iSubItem', ctypes.c_int), ('state', wt.UINT),
                ('stateMask', wt.UINT), ('pszText', ctypes.c_void_p), ('cchTextMax', ctypes.c_int), ('iImage', ctypes.c_int),
                ('lParam', ctypes.c_ssize_t), ('iIndent', ctypes.c_int), ('iGroupId', ctypes.c_int), ('cColumns', wt.UINT),
                ('puColumns', ctypes.c_void_p), ('piColFmt', ctypes.c_void_p), ('iGroup', ctypes.c_int)]


def icon_centers(lv):
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(lv, ctypes.byref(pid))
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.VirtualAllocEx.restype = ctypes.c_void_p
    kernel32.VirtualAllocEx.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, wt.DWORD, wt.DWORD]
    kernel32.WriteProcessMemory.argtypes = kernel32.ReadProcessMemory.argtypes = \
        [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
    kernel32.VirtualFreeEx.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, wt.DWORD]
    hp = kernel32.OpenProcess(0x0008 | 0x0010 | 0x0020 | 0x0400, False, pid.value)
    mem = kernel32.VirtualAllocEx(hp, None, 4096, 0x3000, 0x04)
    out = {}
    try:
        for i in range(user32.SendMessageW(lv, 0x1004, 0, 0)):  # LVM_GETITEMCOUNT
            item = LVITEMW(mask=1, iItem=i, pszText=mem + 1024, cchTextMax=260)
            kernel32.WriteProcessMemory(hp, mem, ctypes.byref(item), ctypes.sizeof(item), None)
            user32.SendMessageW(lv, 0x1073, i, mem)  # LVM_GETITEMTEXTW
            name = ctypes.create_unicode_buffer(260)
            kernel32.ReadProcessMemory(hp, mem + 1024, name, 520, None)
            rect = wt.RECT(1, 0, 0, 0)  # left = LVIR_ICON
            kernel32.WriteProcessMemory(hp, mem, ctypes.byref(rect), ctypes.sizeof(rect), None)
            user32.SendMessageW(lv, 0x100E, i, mem)  # LVM_GETITEMRECT
            kernel32.ReadProcessMemory(hp, mem, ctypes.byref(rect), ctypes.sizeof(rect), None)
            pt = wt.POINT((rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2)
            user32.ClientToScreen(lv, ctypes.byref(pt))
            out[name.value] = (pt.x, pt.y)
    finally:
        kernel32.VirtualFreeEx(hp, mem, 0, 0x8000)
        kernel32.CloseHandle(ctypes.c_void_p(hp))
    return out


try:
    lv = desktop_listview()
    icons = icon_centers(lv) if lv else {}
    a, b = icons.get('NotAFK_test_drag'), icons.get('NotAFK_test_target')
    user32.WindowFromPoint.argtypes = [wt.POINT]
    visible = a and b and all(user32.WindowFromPoint(wt.POINT(*p)) == lv for p in (a, b))
    if not visible:
        check('B2 desktop folder drag (icons must be visible on the desktop)', False, (a, b, 'covered or hidden'))
    else:
        ok, _ = run([{"id": "fd", "enabled": True, "type": "drag", "coords": {"x": a[0], "y": a[1]},
                      "to": {"x": b[0], "y": b[1]}, "button": "Left click", "duration": "0,9"}])
        moved = False
        for _ in range(20):
            moved = os.path.isdir(os.path.join(dst, 'NotAFK_test_drag')) and not os.path.exists(src)
            if moved:
                break
            time.sleep(0.25)
        check('B2 Drag step moves a desktop folder into another folder', ok and moved, (a, b))
finally:
    shutil.rmtree(src, ignore_errors=True)
    shutil.rmtree(dst, ignore_errors=True)
    check('B2 test folders removed from the desktop', not os.path.exists(src) and not os.path.exists(dst))

# B7: Spotify in Background Mode (Space = play/pause, sent twice so it ends as it started) ---------------
spotify = []
user32.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_int, wt.HWND, wt.LPARAM)(
    lambda h, _: (spotify.append(h) if user32.IsWindowVisible(h) and 'Spotify' in window_title(h)
                  and not user32.GetWindow(h, 4) else None) or 1), 0)
if not spotify:
    print('SKIP B7 Spotify is not open')
else:
    hwnd = spotify[0]
    was_minimized = user32.IsIconic(hwnd)
    if was_minimized:  # Background Mode needs a window that is open (it may stay behind others)
        user32.ShowWindow(hwnd, 4)  # SW_SHOWNOACTIVATE
        time.sleep(1.5)
    before = window_title(hwnd)
    MS.position = (60, 60)
    fg = user32.GetForegroundWindow()
    r = window_rect(hwnd)
    play = {"x": 0, "y": 0, "rel": {"x": (r.right - r.left) // 2 - 1, "y": (r.bottom - r.top) - 56}}  # player bar Play button
    tap = lambda: run([{"id": "sp", "enabled": True, "type": "click", "button": "Left click", "times": "1", "coords": play}],  # noqa: E731
                      backgroundEnabled=True, targetHwnd=hwnd)
    tap()
    time.sleep(2.5)
    middle = window_title(hwnd)
    tap()
    time.sleep(2.5)
    after = window_title(hwnd)
    check('B7 Spotify: background click on Play starts, second click pauses', middle != before and after == before,
          (before, middle, after))
    check('B7 Spotify run did not move the cursor or take focus', cursor() == (60, 60) and user32.GetForegroundWindow() == fg)
    run([key('Space')], backgroundEnabled=True, targetHwnd=hwnd)
    time.sleep(2)
    print('INFO B7 after a background click into Spotify, a background Space also toggles playback:',
          window_title(hwnd) != before)
    if window_title(hwnd) != before:
        run([key('Space')], backgroundEnabled=True, targetHwnd=hwnd)
    if was_minimized:
        user32.ShowWindow(hwnd, 7)  # back to minimized, without activating
    check('B7 Spotify reacts to Space sent in Background Mode (play, then pause)', middle != before and after == before,
          (before, middle, after))
    check('B7 Spotify run did not move the cursor or take focus', cursor() == (60, 60) and user32.GetForegroundWindow() == fg)

print('ALL PASS' if not failures else f'{failures} FAILED')
sys.exit(1 if failures else 0)
