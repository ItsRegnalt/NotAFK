"""Test target for tests/background_test.py: an off-screen Win32 window with a standard EDIT control
(the same control Notepad-style apps use). It never takes focus.
Prints 'READY <hwnd> <x> <y>' = screen point of the left edge of character 5 in the text "0123456789".
On WM_CLOSE writes the edit's final text to argv[1]."""
import ctypes, ctypes.wintypes as wt, json, sys

out = sys.argv[1]
user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
user32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.DefWindowProcW.restype = ctypes.c_ssize_t
user32.SendMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.SendMessageW.restype = ctypes.c_ssize_t
user32.CreateWindowExW.restype = wt.HWND
user32.CreateWindowExW.argtypes = [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_int, wt.HWND, wt.HMENU, wt.HINSTANCE, wt.LPVOID]
WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)
edit = None


def proc(hwnd, msg, wp, lp):
    if msg == 0x10:  # WM_CLOSE
        buf = ctypes.create_unicode_buffer(1024)
        user32.GetWindowTextW(edit, buf, 1024)
        json.dump({'text': buf.value}, open(out, 'w', encoding='utf-8'))
        user32.PostQuitMessage(0)
        return 0
    return user32.DefWindowProcW(hwnd, msg, wp, lp)


wndproc = WNDPROC(proc)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [('style', wt.UINT), ('lpfnWndProc', WNDPROC), ('cbClsExtra', ctypes.c_int), ('cbWndExtra', ctypes.c_int),
                ('hInstance', wt.HINSTANCE), ('hIcon', wt.HICON), ('hCursor', wt.HANDLE), ('hbrBackground', wt.HBRUSH),
                ('lpszMenuName', wt.LPCWSTR), ('lpszClassName', wt.LPCWSTR)]


hinst = kernel32.GetModuleHandleW(None)
wc = WNDCLASSW(lpfnWndProc=wndproc, hInstance=hinst, lpszClassName='NotAFKBgTarget')
user32.RegisterClassW(ctypes.byref(wc))
WS_OVERLAPPEDWINDOW, WS_CHILD, WS_VISIBLE = 0xCF0000, 0x40000000, 0x10000000
WS_EX_NOACTIVATE, WS_EX_TOOLWINDOW = 0x08000000, 0x80
ES_MULTILINE, ES_WANTRETURN, ES_AUTOVSCROLL = 0x4, 0x1000, 0x40
main = user32.CreateWindowExW(WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW, 'NotAFKBgTarget', 'NotAFK BG Target',
                              WS_OVERLAPPEDWINDOW, -6000, -6000, 500, 300, None, None, hinst, None)  # off every monitor
edit = user32.CreateWindowExW(0, 'EDIT', '0123456789', WS_CHILD | WS_VISIBLE | ES_MULTILINE | ES_WANTRETURN | ES_AUTOVSCROLL,
                              10, 10, 460, 200, main, None, hinst, None)
user32.ShowWindow(main, 4)  # SW_SHOWNOACTIVATE
pos = user32.SendMessageW(edit, 0xD6, 5, 0)  # EM_POSFROMCHAR -> client x/y of char 5
pt = wt.POINT(pos & 0xFFFF, (pos >> 16) & 0xFFFF)
user32.ClientToScreen(edit, ctypes.byref(pt))
print('READY', main, pt.x + 1, pt.y + 6, flush=True)
msg = wt.MSG()
while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
    user32.TranslateMessage(ctypes.byref(msg))
    user32.DispatchMessageW(ctypes.byref(msg))
