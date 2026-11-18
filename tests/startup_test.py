"""Startup test: runs the real entry path (main.main -> ui.webview_shell.run) with the GUI loop stubbed out,
so no window ever appears. Catches errors in how the window is created.  Usage: python tests/startup_test.py
If NotAFK is already open, main() correctly stops at the single-instance check, so run() is called directly."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import webview
import main

captured = {}
webview.start = lambda func=None, args=None, **kw: captured.update(func=func, args=args, kw=kw)  # no GUI
main.main()
if not captured:  # another NotAFK is running (single instance): exercise the window setup directly
    import ui.webview_shell
    ui.webview_shell.run()
win = (captured.get("args") or [None])[0]
ok = bool(captured) and win is not None and win.initial_width > 0 and win.initial_height > 0 \
    and captured["kw"].get("http_port") == 47823 and captured["kw"].get("private_mode") is False
print(("PASS" if ok else "FAIL") + " startup creates the window and starts the app",
      f"[{getattr(win, 'initial_width', None)}x{getattr(win, 'initial_height', None)} {captured.get('kw', {}).get('http_port')}]")
sys.exit(0 if ok else 1)
