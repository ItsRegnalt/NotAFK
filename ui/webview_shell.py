"""WebView2 (Edge) desktop shell: hosts the React UI (v2/dist) and drives the native automation engine.

JS calls the methods of `Api` through `window.pywebview.api`; Python pushes events back as
`notafk:*` CustomEvents (same events the UI already listens to)."""
import ctypes
import ctypes.wintypes
import json
import math
import os
import sys
import threading
import time

# Per-monitor DPI aware (v2), before any window or input library loads: every coordinate (picker, recorder,
# playback, window rects) is then in real screen pixels on every monitor, also when monitors use different
# scaling. pywebview's own SetProcessDPIAware() call later does nothing.
try:
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # PER_MONITOR_AWARE_V2
except (AttributeError, OSError):  # Windows 10 before 1703
    pass

import webview
from pynput import keyboard, mouse

from core.actions import ClickAction, MoveAction, TypeAction, DelayAction, KeyAction, ScrollAction, DragAction
from core.background import top_window_at, window_rect, window_title
from core.humanizer import get_real_cursor_pos
from core.worker import ExecutionWorker
from ui.picker import ScreenPicker
from ui import updater
from version import VERSION, GITHUB_REPO

ROOT = getattr(sys, '_MEIPASS', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# fixed: localStorage (saved automations) is keyed by origin, so the port must not change. Tests use their own.
HTTP_PORT = int(os.environ.get('NOTAFK_PORT', 47823))
BG = '#0d0f14'
user32 = ctypes.windll.user32
WM_NCLBUTTONDOWN, HTCAPTION = 0xA1, 2
# UI edge flags (Top=1, Left=2, Right=4, Bottom=8) -> Win32 hit-test codes for a native resize
HIT = {1: 12, 8: 15, 2: 10, 4: 11, 3: 13, 5: 14, 10: 16, 12: 17}


def seconds(value, fallback=0.0):
    try:
        return max(0.0, float(str(value).replace(',', '.')))
    except (TypeError, ValueError):
        return fallback


MAX_REPEAT = 1000


def expand_repeats(rows):
    """Unroll 'loop' ... 'loopEnd' blocks (nestable) into a flat list; a disabled block runs its body once."""
    out, i = [], 0
    while i < len(rows):
        row = rows[i]
        if row.get('type') == 'loop':
            end = next((j for j in range(i + 1, len(rows)) if rows[j].get('type') == 'loopEnd'
                        and rows[j].get('loopOwnerId') == row.get('id')), len(rows))
            body = expand_repeats(rows[i + 1:end])
            times = max(1, min(MAX_REPEAT, int(row.get('times') or 1))) if row.get('enabled', True) else 1
            out += body * times
            i = end + 1
        else:
            if row.get('type') != 'loopEnd':
                out.append(row)
            i += 1
    return out


def build_worker(config):
    """Translate the UI's JSON config into an ExecutionWorker (None if nothing is enabled)."""
    rows = expand_repeats(config.get('steps', []))
    moving = bool(config.get('movementEnabled', True))
    jitter = int(config.get('targetJitter', 0)) if moving else 0
    actions = []
    for row in rows:
        if not row.get('enabled', True) or row.get('holdOwnerId'):
            continue
        kind, coords, rid = row.get('type'), row.get('coords') or {}, row.get('id')
        if kind == 'click':
            button = row.get('button', 'Left click')
            actions.append(ClickAction(
                x=coords.get('x', 0), y=coords.get('y', 0),
                button={'Left click': 'left', 'Right click': 'right', 'Middle click': 'middle'}.get(button, 'left'),
                double=button == 'Double click', times=max(1, int(row.get('times') or 1)),
                click_interval_ms=round(seconds(row.get('clickInterval'), .1) * 1000),
                smooth_move=moving, jitter_radius=jitter, action_id=rid,
                hold_ms=round(seconds(row.get('holdTime'), 0) * 1000)))
        elif kind == 'drag':
            end = row.get('to') or {}
            actions.append(DragAction(
                x=coords.get('x', 0), y=coords.get('y', 0), to_x=end.get('x', 0), to_y=end.get('y', 0),
                button={'Left click': 'left', 'Right click': 'right', 'Middle click': 'middle'}.get(row.get('button'), 'left'),
                duration_ms=round(seconds(row.get('duration'), .6) * 1000), action_id=rid))
            if end.get('rel'):
                actions[-1].rel_to = (int(end['rel']['x']), int(end['rel']['y']))
        elif kind == 'move':
            actions.append(MoveAction(x=coords.get('x', 0), y=coords.get('y', 0),
                                      smooth_move=moving, jitter_radius=jitter, action_id=rid))
        elif kind == 'text':
            value = row.get('textValue', '') + ('\n' if row.get('pressEnter') else '')
            gap = round(seconds(row.get('keyDelay'), .05) * 1000)
            actions.append(TypeAction(text=value, min_delay_ms=gap, max_delay_ms=gap, action_id=rid))
        elif kind == 'key' and row.get('keyMode') != 'release':
            mode, hold_ms = row.get('keyMode', 'press'), 0
            if mode == 'hold':  # hold length comes from the auto-inserted delay row owned by this key
                delay = next((r for r in rows if r.get('holdOwnerId') == rid and r.get('type') == 'delay'), None)
                hold_ms = round(seconds((delay or {}).get('duration', row.get('holdDuration', '0,5'))) * 1000)
            actions.append(KeyAction(key=row.get('keyName', 'Space'), mode=mode, hold_ms=hold_ms, action_id=rid,
                                     modifiers=row.get('modifiers') or ()))
        elif kind == 'scroll':
            try:
                amount = int(str(row.get('amount', '-3')).strip())
            except ValueError:
                amount = -3
            actions.append(ScrollAction(x=coords.get('x', 0), y=coords.get('y', 0),
                                        amount=max(-100, min(100, amount)), action_id=rid))
        elif kind == 'delay':
            duration = seconds(row.get('duration'), .5)
            variance = seconds(row.get('variance')) if row.get('randomize') else 0
            actions.append(DelayAction(min_ms=round(max(0, duration - variance) * 1000),
                                       max_ms=round((duration + variance) * 1000), action_id=rid))
        if actions and actions[-1].id == rid:
            actions[-1].chance = max(0, min(100, int(seconds(row.get('chance'), 100))))
            rel = coords.get('rel')
            if rel and kind in ('click', 'move', 'scroll', 'drag'):
                actions[-1].rel = (int(rel['x']), int(rel['y']))
    if not actions:
        return None
    run_mode = config.get('runMode')
    return ExecutionWorker(
        actions,
        global_delay_min=round(seconds(config.get('minDelay')) * 1000),
        global_delay_max=round(seconds(config.get('maxDelay')) * 1000),
        repeat_mode='infinite' if run_mode == 'loop' else 'count',
        repeat_count=1 if run_mode == 'once' else max(1, int(config.get('repeatCount') or 1)),
        speed_factor=max(.2, seconds(config.get('mouseSpeed'), 1)),
        deviation=max(0, float(config.get('curvePercent', 0)) / 100),
        jitter_radius=int(config.get('targetJitter', 0)),
        global_delay_enabled=bool(config.get('globalDelayEnabled', True)),
        movement_enabled=moving,
        background_hwnd=int(config['targetHwnd']) if config.get('backgroundEnabled') and config.get('targetHwnd') else None,
        time_limit_s=seconds(config.get('timeLimit')) * 60)  # UI value is minutes, 0/empty = off


UI_KEYS = {keyboard.Key.tab: 'Tab', keyboard.Key.delete: 'Delete', keyboard.Key.up: 'Arrow Up',
           keyboard.Key.down: 'Arrow Down', keyboard.Key.left: 'Arrow Left', keyboard.Key.right: 'Arrow Right',
           keyboard.Key.home: 'Home', keyboard.Key.end: 'End', keyboard.Key.page_up: 'Page Up',
           keyboard.Key.page_down: 'Page Down', keyboard.Key.insert: 'Insert', keyboard.Key.enter: 'Enter',
           keyboard.Key.backspace: 'Backspace', keyboard.Key.space: 'Space',
           **{getattr(keyboard.Key, f'f{i}'): f'F{i}' for i in range(1, 13)}}
UI_BUTTONS = {mouse.Button.left: 'Left click', mouse.Button.right: 'Right click', mouse.Button.middle: 'Middle click'}
MODIFIERS = {keyboard.Key.ctrl: 'Ctrl', keyboard.Key.ctrl_l: 'Ctrl', keyboard.Key.ctrl_r: 'Ctrl',
             keyboard.Key.shift: 'Shift', keyboard.Key.shift_l: 'Shift', keyboard.Key.shift_r: 'Shift',
             keyboard.Key.alt: 'Alt', keyboard.Key.alt_l: 'Alt', keyboard.Key.alt_r: 'Alt', keyboard.Key.alt_gr: 'Alt',
             keyboard.Key.cmd: 'Win', keyboard.Key.cmd_l: 'Win', keyboard.Key.cmd_r: 'Win'}
HOLD_S = 0.35        # a key held at least this long is recorded as Hold (with its real duration)
TYPING_GAP_S = 1.0   # quick consecutive character taps are one Text step


def _secs(value):
    return f'{value:.2f}'.replace('.', ',')


def _key_label(key):
    """pynput key -> UI key name ('A', '7', 'Space', 'F5'...) or None."""
    if key in UI_KEYS:
        return UI_KEYS[key]
    vk = getattr(key, 'vk', None)
    if vk and (0x41 <= vk <= 0x5A or 0x30 <= vk <= 0x39):  # letters/digits, also when Ctrl turns the char into \x03
        return chr(vk)
    char = getattr(key, 'char', None)
    return char.upper() if char and len(char) == 1 and char.isalnum() else None


class Recorder:
    """Turns real mouse/keyboard use into UI steps.
    - quick character taps -> one Text step; a single isolated tap -> Key press (works in games too)
    - a key held >= 0.35 s -> Key Hold with its real duration (auto-repeat is ignored)
    - Ctrl / Alt / Win + key -> Key press with those modifiers (Shift + letter stays typed text)
    - mouse: click (double clicks merged), long press (button held >= 0.35 s), drag (moved while held),
      wheel scrolling, and pauses between actions -> Delay"""

    def __init__(self, shell, target_hwnd=None):
        self.shell, self.target = shell, target_hwnd
        self.steps, self.text, self.text_start, self.last, self.n = [], '', 0.0, time.time(), 0
        self.down, self.mods = {}, set()
        self.press = None  # (x, y, time, button) of the mouse button that is down
        self.mouse = mouse.Listener(on_click=self._on_click, on_scroll=self._on_scroll, daemon=True)
        self.keys = keyboard.Listener(on_press=self._on_press, on_release=self._on_release, daemon=True)

    def start(self):
        self.mouse.start()
        self.keys.start()

    def stop(self):
        self.mouse.stop()
        self.keys.stop()
        self._flush_text()
        return self.steps

    def _add(self, step):
        self.n += 1
        sid = f'rec-{int(time.time() * 1000)}-{self.n}'
        self.steps.append({'id': sid, 'enabled': True, **step})
        return sid

    def _flush_text(self):
        if not self.text:
            return
        if len(self.text) == 1 and (self.text.isalnum() or self.text == ' '):
            name = 'Space' if self.text == ' ' else self.text.upper()  # a lone tap is a key press, not typing
            self._add({'type': 'key', 'keyName': name, 'keyMode': 'press', 'holdDuration': '0,50'})
        else:
            self._add({'type': 'text', 'textValue': self.text, 'keyDelay': '0,05', 'pressEnter': False})
        self.text = ''

    def _gap(self, at=None):
        """A pause before this action becomes a Delay step (short gaps are ignored)."""
        at = at or time.time()
        gap, self.last = at - self.last, at
        if gap >= 0.2:
            self._flush_text()
            self._add({'type': 'delay', 'duration': _secs(min(gap, 600)), 'randomize': False, 'variance': '0'})

    def _coords(self, x, y):
        coords = {'x': x, 'y': y, 'picked': True}
        if self.target:
            r = window_rect(self.target)
            coords['rel'] = {'x': x - r.left, 'y': y - r.top}
        return coords

    def _on_click(self, x, y, button, pressed):
        if button not in UI_BUTTONS:
            return
        if pressed:  # decide on release: click, long press or drag
            self.press = None if top_window_at(x, y) == self.shell._hwnd() else (x, y, time.time(), button)
            return
        if not self.press or self.press[3] != button:
            return
        x0, y0, t0, _ = self.press
        self.press = None
        now = time.time()
        self._flush_text()  # typing before this click comes first
        if math.hypot(x - x0, y - y0) > 6:
            self._gap(t0)
            self._add({'type': 'drag', 'coords': self._coords(x0, y0), 'to': self._coords(x, y),
                       'button': UI_BUTTONS[button], 'duration': _secs(max(0.2, now - t0))})
            self.last = now
            return
        prev = self.steps[-1] if self.steps else None
        if (prev and prev['type'] == 'click' and prev['button'] == UI_BUTTONS[button] == 'Left click'
                and t0 - self.last < 0.35 and prev.get('holdTime', '0') == '0'
                and abs(prev['coords']['x'] - x) <= 4 and abs(prev['coords']['y'] - y) <= 4):
            prev['button'] = 'Double click'
            self.last = now
            return
        self._gap(t0)
        held = now - t0
        self._add({'type': 'click', 'coords': self._coords(x0, y0), 'button': UI_BUTTONS[button], 'times': '1',
                   'clickInterval': '0,10', 'holdTime': _secs(held) if held >= HOLD_S else '0'})
        self.last = now

    def _on_scroll(self, x, y, dx, dy):
        if not dy or top_window_at(x, y) == self.shell._hwnd():
            return
        self._flush_text()
        prev = self.steps[-1] if self.steps else None
        if (prev and prev['type'] == 'scroll' and time.time() - self.last < 0.6
                and abs(prev['coords']['x'] - x) <= 20 and abs(prev['coords']['y'] - y) <= 20
                and (int(prev['amount']) > 0) == (dy > 0)):
            prev['amount'] = str(int(prev['amount']) + int(dy))  # one wheel gesture = one step
            self.last = time.time()
            return
        self._gap()
        self._add({'type': 'scroll', 'coords': self._coords(x, y), 'amount': str(int(dy))})

    def _on_press(self, key):
        if self.shell._hotkey_name(key):
            return  # start/stop/esc are handled by the shell's hotkey listener
        if key in MODIFIERS:
            self.mods.add(MODIFIERS[key])
        elif key not in self.down:  # ignore auto-repeat while a key is held
            self.down[key] = time.time()

    def _on_release(self, key):
        if key in MODIFIERS:
            self.mods.discard(MODIFIERS[key])
            return
        start = self.down.pop(key, None)
        if start is None:
            return
        now = time.time()
        held = now - start
        label = _key_label(key)
        combo = sorted(self.mods & {'Ctrl', 'Alt', 'Win'})
        char = ' ' if key == keyboard.Key.space else getattr(key, 'char', None)
        if label and held >= HOLD_S:
            self._gap(start)
            self._flush_text()
            sid = self._add({'type': 'key', 'keyName': label, 'keyMode': 'hold', 'holdDuration': _secs(held),
                             **({'modifiers': combo} if combo else {})})
            self.steps.append({'id': f'{sid}-hold-delay', 'enabled': True, 'type': 'delay', 'duration': _secs(held),
                               'randomize': False, 'variance': '0', 'holdOwnerId': sid})
            self.steps.append({'id': f'{sid}-hold-release', 'enabled': True, 'type': 'key', 'keyName': label,
                               'keyMode': 'release', 'holdOwnerId': sid})
            self.last = now
        elif label and combo:
            self._gap(start)
            self._flush_text()
            self._add({'type': 'key', 'keyName': label, 'keyMode': 'press', 'holdDuration': '0,50', 'modifiers': combo})
            self.last = now
        elif char and char.isprintable():
            if self.text and start - self.last < TYPING_GAP_S:
                self.text += char
            else:
                self._gap(start)
                self._flush_text()
                self.text = char
            self.last = now
        elif key == keyboard.Key.backspace and self.text:
            self.text = self.text[:-1]
            self.last = now
        elif label:
            self._gap(start)
            self._flush_text()
            self._add({'type': 'key', 'keyName': label, 'keyMode': 'press', 'holdDuration': '0,50'})
            self.last = now


class Api:
    """Methods exposed to JS as window.pywebview.api.* (names match the old Qt bridge)."""

    def __init__(self):
        self._window = None
        self._worker = None
        self._picker = None
        self._pick_id = None
        self._maximized = False
        self._listener = None
        self._recorder = None
        self._pick_target = None
        self._hotkeys = {'start': 'F6', 'stop': 'F7'}

    # --- plumbing -------------------------------------------------------------------------
    def _emit(self, name, detail=None):
        if self._window:
            self._window.run_js(
                f"window.dispatchEvent(new CustomEvent('notafk:{name}',{{detail:{json.dumps(detail)}}}))")

    def _hwnd(self):
        return int(self._window.native.Handle.ToInt64())

    def _on_ui_thread(self, fn):
        from System import Action
        self._window.native.Invoke(Action(fn))

    def _start(self, window):
        window.events.loaded.wait()  # (not shown: also works for a hidden window)
        self._window = window
        # pywebview sizes the form before dropping its border, so a frameless window opens 16x20px small.
        # Fix it ourselves: window.resize() uses SWP_SHOWWINDOW, which would also reveal a hidden window.
        scale = user32.GetDpiForWindow(self._hwnd()) / 96
        SWP_NOMOVE, SWP_NOZORDER, SWP_NOACTIVATE = 0x2, 0x4, 0x10
        user32.SetWindowPos(self._hwnd(), None, 0, 0, round(window.initial_width * scale),
                            round(window.initial_height * scale), SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE)
        def on_press(key):  # must return None: returning False stops a pynput listener
            name = self._hotkey_name(key)
            if name == 'esc' and self._picker:
                self._picker.cancel()
            elif name and self._recorder:
                if name in ('stop', 'esc'):
                    self.stopRecording()
            elif name:
                self._emit('hotkey', name)
        self._listener = keyboard.Listener(on_press=on_press, daemon=True)
        self._listener.start()
        window.events.maximized += lambda *_: self._set_maximized(True)
        window.events.restored += lambda *_: self._set_maximized(False)
        window.events.closing += self._shutdown
        try:  # Windows 11: rounded corners for the borderless window (DWMWA_WINDOW_CORNER_PREFERENCE=33, ROUND=2)
            pref = ctypes.c_int(2)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(self._hwnd(), 33, ctypes.byref(pref), ctypes.sizeof(pref))
        except Exception:
            pass

    def _hotkey_name(self, key):
        if key == keyboard.Key.esc:
            return 'esc'
        label = (getattr(key, 'name', None) or '').upper()
        return next((n for n, k in self._hotkeys.items() if k == label), None)

    def _set_maximized(self, value):
        self._maximized = value
        self._window.run_js(f"document.documentElement.classList.toggle('maximized', {str(value).lower()})")

    def _shutdown(self, *_):
        if self._listener:
            self._listener.stop()
        if self._worker and self._worker.isRunning():
            self._worker.stop()
            self._worker.wait(2000)

    # --- automation -----------------------------------------------------------------------
    def startMacro(self, raw):
        if self._worker and self._worker.isRunning():
            return
        try:
            worker = build_worker(json.loads(raw))
            if worker is None:
                self._emit('status', 'Error: Add at least one enabled action')
                self._emit('finished', False)
                return
            # callbacks run on the worker thread; run_js is thread-safe
            worker.status_changed.connect(lambda s: self._emit('status', s))
            worker.step_started.connect(lambda i, a: self._emit('step', {'index': i, 'id': a}))
            worker.cycle_completed.connect(lambda c, t: self._emit('cycle', {'current': c, 'total': t}))
            worker.execution_finished.connect(lambda ok: self._emit('finished', ok))
            self._worker = worker
            worker.start()
        except Exception as exc:
            self._emit('status', f'Error: {exc}')
            self._emit('finished', False)

    def stopMacro(self):
        if self._worker and self._worker.isRunning():
            self._worker.stop()

    def setHotkeys(self, start, stop):
        allowed = {f'F{i}' for i in range(1, 13)}
        if start in allowed and stop in allowed and start != stop:
            self._hotkeys = {'start': start, 'stop': stop}
            return True
        return False

    # --- recording ------------------------------------------------------------------------
    def startRecording(self, target_hwnd=None):
        if self._recorder or (self._worker and self._worker.isRunning()):
            return False
        self._window.minimize()
        self._recorder = Recorder(self, int(target_hwnd) if target_hwnd else None)
        self._recorder.start()
        return True

    def stopRecording(self):
        recorder, self._recorder = self._recorder, None
        if recorder:
            steps = recorder.stop()
            self._window.restore()
            self._emit('recorded', steps)

    # --- import / export ------------------------------------------------------------------
    def exportAutomation(self, raw, name):
        safe = ''.join(c for c in str(name) if c not in '<>:"/\\|?*').strip() or 'automation'
        path = self._window.create_file_dialog(webview.FileDialog.SAVE, save_filename=f'{safe}.json',
                                               file_types=('NotAFK automation (*.json)',))
        path = path[0] if isinstance(path, (list, tuple)) else path
        if not path:
            return False
        with open(path, 'w', encoding='utf-8') as f:
            f.write(raw)
        return True

    def importAutomation(self):
        paths = self._window.create_file_dialog(webview.FileDialog.OPEN, file_types=('NotAFK automation (*.json)',))
        if not paths:
            return None
        with open(paths[0], encoding='utf-8') as f:
            return f.read()

    def listWindows(self):
        """Open, visible app windows (z-order, front first) for the background-target dropdown."""
        found = []
        own = self._hwnd()
        cloaked = ctypes.c_int()

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
        def visit(hwnd, _):
            if hwnd == own or not user32.IsWindowVisible(hwnd) or user32.GetWindow(hwnd, 4):  # GW_OWNER
                return True
            if user32.GetWindowLongW(hwnd, -20) & 0x80:  # WS_EX_TOOLWINDOW
                return True
            ctypes.windll.dwmapi.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(cloaked), 4)  # DWMWA_CLOAKED
            title = window_title(hwnd)
            if title and not cloaked.value:
                found.append({'hwnd': hwnd, 'title': title})
            return True
        user32.EnumWindows(visit, 0)
        return found

    def resolveTarget(self, hwnd, title):
        """Saved background target -> live window handle (same window if still open, else found by title)."""
        if hwnd and user32.IsWindow(int(hwnd)) and window_title(int(hwnd)) == title:
            return int(hwnd)
        found = user32.FindWindowW(None, title) if title else 0
        return found or None

    # --- window ---------------------------------------------------------------------------
    def minimizeWindow(self):
        self._window.minimize()

    def restoreWindow(self):
        self._window.restore()

    def toggleMaximize(self):
        if self._maximized:
            self._window.restore()
            return

        def maximize():  # a borderless form would cover the taskbar unless capped to the work area
            from System.Windows.Forms import Screen
            form = self._window.native
            form.MaximizedBounds = Screen.FromHandle(form.Handle).WorkingArea
        self._on_ui_thread(maximize)
        self._window.maximize()

    def closeWindow(self):
        self._window.destroy()

    def _close_soon(self):  # let the JS call return before the window goes away
        threading.Timer(0.3, self._window.destroy).start()

    # --- startup: admin mode, updates -----------------------------------------------------
    def startupInfo(self):
        return {'admin': bool(ctypes.windll.shell32.IsUserAnAdmin()), 'version': VERSION,
                'updates': bool(GITHUB_REPO), 'test': HTTP_PORT != 47823}

    def relaunchAsAdmin(self):
        """Start an elevated copy (it waits until this one has exited) and close. False if UAC was declined."""
        if getattr(sys, 'frozen', False):
            exe, params = sys.executable, '--relaunch'
        else:
            exe, params = sys.executable, f'"{os.path.join(ROOT, "main.py")}" --relaunch'
        shell32 = ctypes.windll.shell32
        shell32.ShellExecuteW.restype = ctypes.c_void_p
        if (shell32.ShellExecuteW(None, 'runas', exe, params, ROOT, 1) or 0) <= 32:
            return False
        self._close_soon()
        return True

    def checkUpdate(self):
        try:
            return updater.check()
        except Exception as e:  # offline, rate limited, repo renamed...
            return {'available': False, 'current': VERSION, 'error': f'Update check failed: {e}'}

    def installUpdate(self):
        try:
            version = updater.install()
        except Exception as e:
            return {'ok': False, 'error': str(e)}
        self._close_soon()
        return {'ok': True, 'version': version}

    def startDrag(self):
        self._on_ui_thread(lambda: (user32.ReleaseCapture(),
                                    user32.SendMessageW(self._hwnd(), WM_NCLBUTTONDOWN, HTCAPTION, 0)))

    def startResize(self, edges):
        hit = HIT.get(int(edges))
        if hit and not self._maximized:
            self._on_ui_thread(lambda: (user32.ReleaseCapture(),
                                        user32.SendMessageW(self._hwnd(), WM_NCLBUTTONDOWN, hit, 0)))

    # --- coordinate picker ----------------------------------------------------------------
    def pickCoordinate(self, step_id, target_hwnd=None):
        self._pick_target = int(target_hwnd) if target_hwnd else None
        self._open_picker(step_id)

    def _open_picker(self, step_id):
        if self._picker:
            return
        self._pick_id = step_id
        self._window.minimize()  # get the app out of the way so the user can click what is behind it
        self._picker = ScreenPicker(self._pick_finished)
        self._picker.start()

    def _pick_finished(self, point):
        self._picker = None
        self._window.restore()
        if point:
            picked = {'id': self._pick_id, 'x': point[0], 'y': point[1]}
            if self._pick_target and user32.IsWindow(self._pick_target):
                r = window_rect(self._pick_target)
                picked['rel'] = {'x': point[0] - r.left, 'y': point[1] - r.top}
            self._emit('picked', picked)
        else:
            self._emit('pick-cancelled', self._pick_id)
        self._pick_id = None


def initial_size():
    """1440x900, or less on small / high-scaling screens (logical px, like pywebview expects)."""
    work = ctypes.wintypes.RECT()
    user32.SystemParametersInfoW(0x30, 0, ctypes.byref(work), 0)  # SPI_GETWORKAREA
    scale = user32.GetDpiForSystem() / 96  # 1.0 while the process is not DPI aware yet
    w, h = (work.right - work.left) / scale, (work.bottom - work.top) / scale
    return int(min(1440, w * .92)), int(min(900, h * .92))


def run():
    api = Api()
    storage = os.path.join(os.environ.get('LOCALAPPDATA', ROOT), 'NotAFK', 'webview')
    width, height = initial_size()
    window = webview.create_window(
        'NotAFK', os.path.join(ROOT, 'v2', 'dist', 'index.html'), js_api=api,
        width=width, height=height, min_size=(960, 600),  # below 1280x880 the UI scales itself down (v2/src/main.jsx)
        frameless=True, easy_drag=False, background_color=BG)
    icon = os.path.join(ROOT, 'assets', 'icon.ico')
    webview.start(api._start, [window], http_server=True, http_port=HTTP_PORT, private_mode=False, storage_path=storage,
                  icon=icon if os.path.exists(icon) else None)
