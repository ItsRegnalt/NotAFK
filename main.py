"""
Automate - Main Entry Point
Launches the human-like automation desktop application (WebView2 shell, ui/webview_shell.py).
"""

import sys
import os
import ctypes
import socket
import time
import webbrowser
import winreg

# Ensure package imports resolve properly
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# Evergreen WebView2 Runtime: Microsoft's official bootstrapper download
WEBVIEW2_DOWNLOAD = "https://go.microsoft.com/fwlink/p/?LinkId=2124703"
WEBVIEW2_CLIENT = r"Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"


def webview2_installed() -> bool:
    """True if the Edge WebView2 Runtime is installed (machine-wide or per-user)."""
    places = [(winreg.HKEY_LOCAL_MACHINE, "SOFTWARE\\WOW6432Node\\" + WEBVIEW2_CLIENT),
              (winreg.HKEY_LOCAL_MACHINE, "SOFTWARE\\" + WEBVIEW2_CLIENT),
              (winreg.HKEY_CURRENT_USER, "Software\\" + WEBVIEW2_CLIENT)]
    for hive, path in places:
        try:
            with winreg.OpenKey(hive, path) as key:
                version = winreg.QueryValueEx(key, "pv")[0]
                if version and version != "0.0.0.0":
                    return True
        except OSError:
            continue
    return False


def message(text, flags=0x30):  # MB_ICONWARNING
    return ctypes.windll.user32.MessageBoxW(None, text, "NotAFK", flags)


def port_free(port) -> bool:
    with socket.socket() as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def main():
    # Tell Windows to treat this as an independent app on the taskbar with its own icon
    try:
        app_id = "notafk.desktop.app.v1"
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass

    # Single instance: a second copy would fight over the hotkeys and the local port
    # --relaunch (restart as administrator): the old copy is still closing, so wait for its mutex and port.
    relaunch = "--relaunch" in sys.argv
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    for _ in range(60 if relaunch else 1):
        mutex = kernel32.CreateMutexW(None, False, "NotAFK.SingleInstance")  # held until exit
        running = kernel32.GetLastError() == 183  # ERROR_ALREADY_EXISTS
        if not running or not relaunch:
            break
        kernel32.CloseHandle(ctypes.c_void_p(mutex))
        time.sleep(0.25)
    if running:  # bring the running copy to the front
        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW(None, "NotAFK")
        if hwnd:
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            user32.SetForegroundWindow(hwnd)
        return

    if not webview2_installed():
        MB_YESNO, IDYES = 0x4, 6
        answer = message("NotAFK needs the Microsoft Edge WebView2 Runtime, which is not installed on this PC.\n\n"
                         "Open the free Microsoft download page? Start NotAFK again after installing it.",
                         0x30 | MB_YESNO)
        if answer == IDYES:
            webbrowser.open(WEBVIEW2_DOWNLOAD)
        return

    from ui.webview_shell import HTTP_PORT, run
    for _ in range(40 if relaunch else 1):
        if port_free(HTTP_PORT):
            break
        time.sleep(0.25)
    else:
        message(f"NotAFK could not start: local port {HTTP_PORT} is used by another program.\n"
                "Close that program (or restart the PC) and try again.")
        return
    run()

if __name__ == "__main__":
    main()
