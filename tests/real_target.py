"""Visible test window for tests/real_test.py: a topmost Win32 window with a multi-line EDIT control
(like Notepad, but nothing is saved anywhere). Prints 'READY <main hwnd> <edit hwnd>' and pumps messages
until WM_CLOSE. Position/size come from argv: x y w h."""
import ctypes, ctypes.wintypes as wt, sys

x, y, w, h = (int(v) for v in sys.argv[1:5])
user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
user32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.DefWindowProcW.restype = ctypes.c_ssize_t
user32.CreateWindowExW.restype = wt.HWND
user32.CreateWindowExW.argtypes = [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_int, wt.HWND, wt.HMENU, wt.HINSTANCE, wt.LPVOID]
WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)


def proc(hwnd, msg, wp, lp):
    if msg == 0x10:  # WM_CLOSE
        user32.PostQuitMessage(0)
        return 0
    return user32.DefWindowProcW(hwnd, msg, wp, lp)


wndproc = WNDPROC(proc)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [('style', wt.UINT), ('lpfnWndProc', WNDPROC), ('cbClsExtra', ctypes.c_int), ('cbWndExtra', ctypes.c_int),
                ('hInstance', wt.HINSTANCE), ('hIcon', wt.HICON), ('hCursor', wt.HANDLE), ('hbrBackground', wt.HBRUSH),
                ('lpszMenuName', wt.LPCWSTR), ('lpszClassName', wt.LPCWSTR)]


hinst = kernel32.GetModuleHandleW(None)
user32.RegisterClassW(ctypes.byref(WNDCLASSW(lpfnWndProc=wndproc, hInstance=hinst, lpszClassName='NotAFKRealTarget',
                                             hbrBackground=6)))
WS_OVERLAPPED_CAPTION, WS_CHILD, WS_VISIBLE, WS_VSCROLL = 0xC00000, 0x40000000, 0x10000000, 0x200000
main = user32.CreateWindowExW(0x8, 'NotAFKRealTarget', 'NotAFK Real Test', WS_OVERLAPPED_CAPTION | WS_VISIBLE,
                              x, y, w, h, None, None, hinst, None)  # WS_EX_TOPMOST
rc = wt.RECT()
user32.GetClientRect(main, ctypes.byref(rc))
edit = user32.CreateWindowExW(0x200, 'EDIT', '', WS_CHILD | WS_VISIBLE | WS_VSCROLL | 0x4 | 0x1000 | 0x40,
                              0, 0, rc.right, rc.bottom, main, None, hinst, None)  # MULTILINE|WANTRETURN|AUTOVSCROLL
font = ctypes.windll.gdi32.CreateFontW(-20, 0, 0, 0, 400, 0, 0, 0, 0, 0, 0, 5, 0, 'Consolas')
user32.SendMessageW(edit, 0x30, font, 1)  # WM_SETFONT
user32.SetForegroundWindow(main)
user32.SetFocus(edit)
print('READY', main, edit, flush=True)
msg = wt.MSG()
while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
    user32.TranslateMessage(ctypes.byref(msg))
    user32.DispatchMessageW(ctypes.byref(msg))
