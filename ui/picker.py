"""Native screen picker.

A full-screen window at 1/255 opacity catches the click while the desktop stays fully visible (a WebView2
overlay cannot be see-through and showed up grey). Thin crosshair lines follow the cursor across all
monitors, and a small HUD next to it shows the coordinates and the color under the cursor. Sizes follow
the DPI of the monitor under the cursor (the process is per-monitor DPI aware, see main.py)."""
import ctypes
import ctypes.wintypes as wt
import threading

from core.background import screen_pixel

user32, gdi32, kernel32 = ctypes.windll.user32, ctypes.windll.gdi32, ctypes.windll.kernel32
WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)
user32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.DefWindowProcW.restype = ctypes.c_ssize_t
user32.CreateWindowExW.restype = wt.HWND
user32.CreateWindowExW.argtypes = [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_int, wt.HWND, wt.HMENU, wt.HINSTANCE, wt.LPVOID]
user32.LoadCursorW.restype = wt.HANDLE
user32.LoadCursorW.argtypes = [wt.HINSTANCE, wt.LPVOID]
user32.SetCursor.argtypes = [wt.HANDLE]
user32.BeginPaint.restype = wt.HDC
user32.FillRect.argtypes = [wt.HDC, ctypes.POINTER(wt.RECT), wt.HBRUSH]
user32.DrawTextW.argtypes = [wt.HDC, wt.LPCWSTR, ctypes.c_int, ctypes.POINTER(wt.RECT), wt.UINT]
user32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
gdi32.CreateSolidBrush.restype = wt.HBRUSH
gdi32.CreateFontW.restype = wt.HFONT
gdi32.SelectObject.restype = wt.HGDIOBJ
gdi32.SelectObject.argtypes = [wt.HDC, wt.HGDIOBJ]
gdi32.DeleteObject.argtypes = [wt.HGDIOBJ]
gdi32.SetTextColor.argtypes = [wt.HDC, wt.COLORREF]
gdi32.SetBkMode.argtypes = [wt.HDC, ctypes.c_int]
gdi32.GetTextExtentPoint32W.argtypes = [wt.HDC, wt.LPCWSTR, ctypes.c_int, ctypes.POINTER(wt.SIZE)]
user32.GetDC.restype = wt.HDC
user32.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
user32.MonitorFromPoint.restype = wt.HANDLE
user32.MonitorFromPoint.argtypes = [wt.POINT, wt.DWORD]
ctypes.windll.shcore.GetDpiForMonitor.argtypes = [wt.HANDLE, ctypes.c_int, ctypes.POINTER(wt.UINT), ctypes.POINTER(wt.UINT)]

WM_DESTROY, WM_CLOSE, WM_PAINT, WM_SETCURSOR, WM_KEYDOWN = 0x2, 0x10, 0xF, 0x20, 0x100
WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_RBUTTONDOWN = 0x200, 0x201, 0x204
WS_POPUP, WS_VISIBLE = 0x80000000, 0x10000000
WS_EX_LAYERED, WS_EX_TOPMOST, WS_EX_TOOLWINDOW, WS_EX_TRANSPARENT, WS_EX_NOACTIVATE = \
    0x80000, 0x8, 0x80, 0x20, 0x08000000
LINE_COLOR, LINE_GAP = '#0A84FF', 10  # crosshair lines leave the pixel under the cursor visible


def monitor_dpi(x, y):
    """DPI of the monitor that contains screen point (x, y) (96 = 100% scaling)."""
    mon = user32.MonitorFromPoint(wt.POINT(x, y), 2)  # MONITOR_DEFAULTTONEAREST
    dx, dy = wt.UINT(96), wt.UINT(96)
    ctypes.windll.shcore.GetDpiForMonitor(mon, 0, ctypes.byref(dx), ctypes.byref(dy))  # MDT_EFFECTIVE_DPI
    return dx.value or 96


def hud_layout(hint, coords_text, dpi):
    """HUD size for the given texts at this DPI, measured with the real font so nothing is cut off.
    Returns (width, height, font_px, scale)."""
    scale = dpi / 96
    font_px = round(13 * scale)
    font = gdi32.CreateFontW(-font_px, 0, 0, 0, 600, 0, 0, 0, 0, 0, 0, 5, 0, 'Segoe UI')
    hdc = user32.GetDC(None)
    old = gdi32.SelectObject(hdc, font)
    widths = []
    for text in (hint, coords_text):
        size = wt.SIZE()
        gdi32.GetTextExtentPoint32W(hdc, text, len(text), ctypes.byref(size))
        widths.append(size.cx)
    gdi32.SelectObject(hdc, old)
    user32.ReleaseDC(None, hdc)
    gdi32.DeleteObject(font)
    pad = round(12 * scale)
    width = max(widths[0] + 2 * pad, widths[1] + round(38 * scale) + pad)
    return width, round(54 * scale), font_px, scale


class PAINTSTRUCT(ctypes.Structure):
    _fields_ = [('hdc', wt.HDC), ('fErase', wt.BOOL), ('rcPaint', wt.RECT), ('fRestore', wt.BOOL),
                ('fIncUpdate', wt.BOOL), ('rgbReserved', ctypes.c_byte * 32)]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [('style', wt.UINT), ('lpfnWndProc', WNDPROC), ('cbClsExtra', ctypes.c_int), ('cbWndExtra', ctypes.c_int),
                ('hInstance', wt.HINSTANCE), ('hIcon', wt.HICON), ('hCursor', wt.HANDLE), ('hbrBackground', wt.HBRUSH),
                ('lpszMenuName', wt.LPCWSTR), ('lpszClassName', wt.LPCWSTR)]


def _rgb(hex_color):
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return r | g << 8 | b << 16


_active = None  # the picker that owns the window procs right now (one picker at a time)


def _overlay_proc(hwnd, msg, wp, lp):
    p = _active
    if p:
        if msg == WM_SETCURSOR:
            user32.SetCursor(user32.LoadCursorW(None, ctypes.c_void_p(32515)))  # IDC_CROSS
            return 1
        if msg == WM_MOUSEMOVE:
            p._update_hud()
            return 0
        if msg == WM_LBUTTONDOWN:
            p._finish(p._cursor())
            return 0
        if msg == WM_RBUTTONDOWN or (msg == WM_KEYDOWN and wp == 0x1B) or msg == WM_CLOSE:
            p._finish(None)
            return 0
    return user32.DefWindowProcW(hwnd, msg, wp, lp)


def _hud_proc(hwnd, msg, wp, lp):
    p = _active
    if p and msg == WM_PAINT:
        p._paint_hud(hwnd)
        return 0
    return user32.DefWindowProcW(hwnd, msg, wp, lp)


def _line_proc(hwnd, msg, wp, lp):
    return user32.DefWindowProcW(hwnd, msg, wp, lp)


_procs = (WNDPROC(_overlay_proc), WNDPROC(_hud_proc), WNDPROC(_line_proc))  # keep references alive
_registered = False


def _register():
    global _registered
    if _registered:
        return
    hinst = kernel32.GetModuleHandleW(None)
    line_brush = gdi32.CreateSolidBrush(_rgb(LINE_COLOR))  # lives as long as the class
    for name, proc, brush in (('NotAFKPickOverlay', _procs[0], None), ('NotAFKPickHud', _procs[1], None),
                              ('NotAFKPickLine', _procs[2], line_brush)):
        wc = WNDCLASSW(lpfnWndProc=proc, hInstance=hinst, lpszClassName=name, hbrBackground=brush)
        user32.RegisterClassW(ctypes.byref(wc))
    _registered = True


class ScreenPicker:
    """pick(on_done): on_done((x, y)) after a left click, on_done(None) if cancelled. Runs its own UI thread."""

    def __init__(self, on_done, hint='Left click: pick  ·  Esc / right click: cancel', visible=True):
        self.on_done, self.hint = on_done, hint
        self.visible = visible  # False only for tests: windows exist but are never shown
        self.overlay = self.hud = None
        self.lines = []  # left, right, top, bottom crosshair segments
        self.result, self._done = None, False
        self._font, self._font_px = None, 0
        self.hud_size, self.scale = (0, 0), 1.0
        self._color = '#000000'

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def cancel(self):
        if self.overlay:
            user32.PostMessageW(self.overlay, WM_CLOSE, 0, 0)

    @staticmethod
    def _cursor():
        pt = wt.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        return pt.x, pt.y

    def _run(self):
        global _active
        _active = self
        _register()
        hinst = kernel32.GetModuleHandleW(None)
        vx, vy, vw, vh = (user32.GetSystemMetrics(i) for i in (76, 77, 78, 79))  # whole virtual desktop
        self.overlay = user32.CreateWindowExW(WS_EX_LAYERED | WS_EX_TOPMOST | WS_EX_TOOLWINDOW, 'NotAFKPickOverlay',
                                              'NotAFK Pick', WS_POPUP, vx, vy, vw, vh, None, None, hinst, None)
        user32.SetLayeredWindowAttributes(self.overlay, 0, 1, 2)  # LWA_ALPHA 1/255: invisible, still catches clicks
        passive = WS_EX_LAYERED | WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE  # click-through
        for _ in range(4):
            line = user32.CreateWindowExW(passive, 'NotAFKPickLine', '', WS_POPUP, 0, 0, 1, 1, None, None, hinst, None)
            user32.SetLayeredWindowAttributes(line, 0, 200, 2)
            self.lines.append(line)
        self.hud = user32.CreateWindowExW(passive, 'NotAFKPickHud', '', WS_POPUP, 0, 0, 1, 1, None, None, hinst, None)
        user32.SetLayeredWindowAttributes(self.hud, 0, 240, 2)
        if self.visible:
            user32.ShowWindow(self.overlay, 5)  # SW_SHOW
            for w in (*self.lines, self.hud):
                user32.ShowWindow(w, 4)  # SW_SHOWNOACTIVATE
            user32.SetForegroundWindow(self.overlay)
        self._update_hud()
        msg = wt.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        if self._font:
            gdi32.DeleteObject(self._font)
        _active = None
        self.on_done(self.result)

    def _finish(self, point):
        if self._done:
            return
        self._done, self.result = True, point
        for w in (self.hud, *self.lines, self.overlay):
            user32.DestroyWindow(w)
        user32.PostQuitMessage(0)

    def _coords_text(self, x, y):
        return f'X: {x}   Y: {y}   {self._color}'

    def _update_hud(self):
        x, y = self._cursor()
        self._color = screen_pixel(x, y)
        w, h, font_px, self.scale = hud_layout(self.hint, self._coords_text(-99999, -99999), monitor_dpi(x, y))
        self.hud_size = (w, h)
        if font_px != self._font_px:  # first call, or moved to a monitor with another scaling
            if self._font:
                gdi32.DeleteObject(self._font)
            self._font = gdi32.CreateFontW(-font_px, 0, 0, 0, 600, 0, 0, 0, 0, 0, 0, 5, 0, 'Segoe UI')
            self._font_px = font_px
        vx, vy, vw, vh = (user32.GetSystemMetrics(i) for i in (76, 77, 78, 79))
        off = round(22 * self.scale)
        hx = x + off if x + off + w < vx + vw else x - off - w
        hy = y + off if y + off + h < vy + vh else y - off - h
        flags = 0x10 | (0 if self.visible else 0x80)  # NOACTIVATE (|HIDEWINDOW in tests)
        top = wt.HWND(-1)  # HWND_TOPMOST
        t, gap = max(1, round(self.scale)), round(LINE_GAP * self.scale)
        self.segments = ((vx, y, x - gap - vx, t), (x + gap + 1, y, vx + vw - x - gap - 1, t),
                         (x, vy, t, y - gap - vy), (x, y + gap + 1, t, vy + vh - y - gap - 1))
        for line, (lx, ly, lw, lh) in zip(self.lines, self.segments):
            user32.SetWindowPos(line, top, lx, ly, max(lw, 0), max(lh, 0), flags)
        user32.SetWindowPos(self.hud, top, hx, hy, w, h, flags)  # topmost, next to the cursor
        user32.InvalidateRect(self.hud, None, True)

    def _paint_hud(self, hwnd):
        ps = PAINTSTRUCT()
        hdc = user32.BeginPaint(hwnd, ctypes.byref(ps))
        (w, h), k = self.hud_size, self.scale

        def sc(v):
            return round(v * k)
        bg = gdi32.CreateSolidBrush(_rgb('#13161F'))
        user32.FillRect(hdc, ctypes.byref(wt.RECT(0, 0, w, h)), bg)
        border = gdi32.CreateSolidBrush(_rgb('#0A84FF'))
        user32.FillRect(hdc, ctypes.byref(wt.RECT(0, 0, max(1, sc(3)), h)), border)
        swatch = gdi32.CreateSolidBrush(_rgb(self._color))
        user32.FillRect(hdc, ctypes.byref(wt.RECT(sc(12), sc(10), sc(30), sc(28))), swatch)
        old = gdi32.SelectObject(hdc, self._font)
        gdi32.SetBkMode(hdc, 1)  # TRANSPARENT
        gdi32.SetTextColor(hdc, _rgb('#FFFFFF'))
        x, y = self._cursor()
        user32.DrawTextW(hdc, self._coords_text(x, y), -1, ctypes.byref(wt.RECT(sc(38), sc(10), w, sc(28))), 0x24)  # SINGLELINE|VCENTER
        gdi32.SetTextColor(hdc, _rgb('#8E8E93'))
        user32.DrawTextW(hdc, self.hint, -1, ctypes.byref(wt.RECT(sc(12), sc(32), w, sc(50))), 0x24)
        gdi32.SelectObject(hdc, old)
        for b in (bg, border, swatch):
            gdi32.DeleteObject(b)
        user32.EndPaint(hwnd, ctypes.byref(ps))
