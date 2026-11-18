"""
Automate - Background input
Sends clicks and keys straight to one window's message queue (PostMessage), so the real
cursor and keyboard stay free. Works for apps that read input from window messages
(Notepad, Office, most desktop apps); games reading Raw Input/DirectInput will ignore it.
Coordinates are stored relative to the target window, so it can be moved; it may sit
behind other windows, but must not be minimized.
"""
import ctypes
import ctypes.wintypes as wt
import random
import time

user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
user32.GetDC.restype = wt.HDC
user32.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
gdi32.GetPixel.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int]
user32.ChildWindowFromPointEx.argtypes = [wt.HWND, wt.POINT, wt.UINT]
user32.ChildWindowFromPointEx.restype = wt.HWND
user32.GetAncestor.restype = wt.HWND
user32.WindowFromPoint.argtypes = [wt.POINT]
user32.WindowFromPoint.restype = wt.HWND
user32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]

WM_MOUSEMOVE, WM_KEYDOWN, WM_KEYUP, WM_CHAR, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x200, 0x100, 0x101, 0x102, 0x104, 0x105
BUTTONS = {  # name: (down, up, double-click, MK_* flag)
    'left': (0x201, 0x202, 0x203, 0x1),
    'right': (0x204, 0x205, 0x206, 0x2),
    'middle': (0x207, 0x208, 0x209, 0x10),
}
CWP_SKIPINVISIBLE, CWP_SKIPDISABLED, CWP_SKIPTRANSPARENT = 0x1, 0x2, 0x4
VK = {'Space': 0x20, 'Enter': 0x0D, 'Tab': 0x09, 'Escape': 0x1B, 'Backspace': 0x08, 'Delete': 0x2E,
      'Arrow Left': 0x25, 'Arrow Up': 0x26, 'Arrow Right': 0x27, 'Arrow Down': 0x28,
      'Home': 0x24, 'End': 0x23, 'Page Up': 0x21, 'Page Down': 0x22, 'Insert': 0x2D,
      'Shift': 0x10, 'Ctrl': 0x11, 'Alt': 0x12, 'Win': 0x5B, **{f'F{i}': 0x6F + i for i in range(1, 13)}}
EXTENDED = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E, 0x5B}


def window_title(hwnd) -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(hwnd, buf, 256)
    return buf.value


def top_window_at(x, y, skip=()):
    """Top-level window under a screen point, ignoring the given top-level handles."""
    hwnd = user32.WindowFromPoint(wt.POINT(x, y))
    root = user32.GetAncestor(hwnd, 2) if hwnd else None  # GA_ROOT
    return None if not root or root in skip else root


def _hex(colorref) -> str:
    """COLORREF (0x00BBGGRR) -> '#RRGGBB'."""
    return '#%02X%02X%02X' % (colorref & 0xFF, colorref >> 8 & 0xFF, colorref >> 16 & 0xFF)


def screen_pixel(x, y) -> str:
    hdc = user32.GetDC(None)
    try:
        return _hex(gdi32.GetPixel(hdc, x, y))
    finally:
        user32.ReleaseDC(None, hdc)


def window_rect(hwnd):
    r = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r


def _lparam(x, y):
    return (y & 0xFFFF) << 16 | (x & 0xFFFF)


class BackgroundInput:
    def __init__(self, hwnd: int):
        if not user32.IsWindow(hwnd):
            raise RuntimeError('Target window not found (it may have been closed). Pick it again.')
        if user32.IsIconic(hwnd):
            raise RuntimeError('Target window is minimized. It can stay behind other windows, but not minimized.')
        self.hwnd = hwnd
        self.focus = hwnd  # control that receives keys: last clicked child, else the window itself

    def to_screen(self, rx, ry):
        """Window-relative point (saved at pick time) -> current screen point, so moving the window is fine."""
        r = window_rect(self.hwnd)
        return r.left + rx, r.top + ry

    def _child_at(self, x, y):
        """Deepest visible child of the target under screen point -> (hwnd, client x, client y)."""
        hwnd = self.hwnd
        while True:
            pt = wt.POINT(x, y)
            user32.ScreenToClient(hwnd, ctypes.byref(pt))
            child = user32.ChildWindowFromPointEx(hwnd, pt, CWP_SKIPINVISIBLE | CWP_SKIPDISABLED | CWP_SKIPTRANSPARENT)
            if not child or child == hwnd:
                return hwnd, pt.x, pt.y
            hwnd = child

    def move(self, x, y):
        hwnd, cx, cy = self._child_at(x, y)
        user32.PostMessageW(hwnd, WM_MOUSEMOVE, 0, _lparam(cx, cy))
        return True

    def click(self, x, y, button='left', double=False, double_interval_ms=120, stop=None, hold_ms=0):
        down, up, dbl, flag = BUTTONS.get(button, BUTTONS['left'])
        hwnd, cx, cy = self._child_at(x, y)
        pos = _lparam(cx, cy)
        user32.PostMessageW(hwnd, WM_MOUSEMOVE, 0, pos)
        user32.PostMessageW(hwnd, down, flag, pos)
        # A control that captures the mouse on button-down (edit boxes, lists) also gets moves of the REAL
        # cursor, which would drag a selection to wherever the user's mouse is. A tap sends down+up together;
        # a long press keeps re-sending our own position so the last move before button-up is ours.
        end = time.time() + hold_ms / 1000
        while time.time() < end:
            time.sleep(0.015)
            user32.PostMessageW(hwnd, WM_MOUSEMOVE, flag, pos)
        user32.PostMessageW(hwnd, up, 0, pos)
        if double:
            time.sleep(double_interval_ms / 1000)
            user32.PostMessageW(hwnd, dbl, flag, pos)
            user32.PostMessageW(hwnd, up, 0, pos)
        self.focus = hwnd
        return not (stop and stop())

    def drag(self, x, y, to_x, to_y, button='left', duration_ms=600, stop=None):
        """Button down at (x, y), moves, button up at (to_x, to_y), all sent to the control under the start
        point (like real mouse capture). Drag & drop between apps (Explorer) needs real input instead."""
        down, up, _, flag = BUTTONS.get(button, BUTTONS['left'])
        hwnd, cx, cy = self._child_at(x, y)
        user32.PostMessageW(hwnd, WM_MOUSEMOVE, 0, _lparam(cx, cy))
        user32.PostMessageW(hwnd, down, flag, _lparam(cx, cy))
        steps = max(8, duration_ms // 25)
        for i in range(1, steps + 1):
            if stop and stop():
                break
            pt = wt.POINT(round(x + (to_x - x) * i / steps), round(y + (to_y - y) * i / steps))
            user32.ScreenToClient(hwnd, ctypes.byref(pt))
            user32.PostMessageW(hwnd, WM_MOUSEMOVE, flag, _lparam(pt.x, pt.y))
            time.sleep(duration_ms / 1000 / steps)
        user32.PostMessageW(hwnd, WM_MOUSEMOVE, flag, _lparam(pt.x, pt.y))  # ours is the last move (see click)
        user32.PostMessageW(hwnd, up, 0, _lparam(pt.x, pt.y))
        self.focus = hwnd
        return not (stop and stop())

    def type_text(self, text, min_delay_ms=50, max_delay_ms=150, stop=None):
        for char in text:
            if stop and stop():
                return False
            if char == '\n':
                self.press_key('Enter')
            else:
                user32.PostMessageW(self.focus, WM_CHAR, ord(char), 1)
            time.sleep(random.uniform(min_delay_ms, max_delay_ms) / 1000)
        return True

    def _key(self, vk, down, alt=False):
        scan = user32.MapVirtualKeyW(vk, 0)
        lp = 1 | scan << 16 | (1 << 24 if vk in EXTENDED else 0) | (1 << 29 if alt else 0)
        if not down:
            lp |= 0xC0000000
        sys_key = vk == 0x12 or alt  # Alt and Alt+key go as WM_SYSKEY*
        msg = (WM_SYSKEYDOWN if down else WM_SYSKEYUP) if sys_key else (WM_KEYDOWN if down else WM_KEYUP)
        user32.PostMessageW(self.focus, msg, vk, lp)  # the app's TranslateMessage turns key downs into WM_CHAR

    def press_key(self, key_name, hold_ms=0, stop=None, modifiers=()):
        vk = VK.get(key_name) or (ord(key_name.upper()) if len(key_name) == 1 else None)
        if vk is None:
            return False
        # note: apps that check the live modifier state (GetKeyState) may not see Ctrl/Shift in background mode
        mods = [VK[m] for m in modifiers if m in VK]
        alt = 'Alt' in modifiers
        for m in mods:
            self._key(m, True)
        self._key(vk, True, alt)
        end = time.time() + hold_ms / 1000
        while time.time() < end:
            if stop and stop():
                break
            time.sleep(0.01)
        self._key(vk, False, alt)
        for m in reversed(mods):
            self._key(m, False)
        return not (stop and stop())

    def scroll(self, x, y, amount, stop=None):
        """Mouse wheel over the control at screen (x, y); WM_MOUSEWHEEL carries screen coordinates."""
        hwnd, _, _ = self._child_at(x, y)
        delta = 120 if amount > 0 else -120
        for _ in range(abs(amount)):
            if stop and stop():
                return False
            user32.PostMessageW(hwnd, 0x20A, (delta & 0xFFFF) << 16, _lparam(x, y))
            time.sleep(random.uniform(0.03, 0.08))
        return True
