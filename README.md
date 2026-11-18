# NotAFK

Desktop automation for simple, repetitive tasks on Windows: clicks, typing, key presses and waits,
with human-like mouse movement and timing. The UI is React (`v2/`) inside a WebView2 window (`ui/webview_shell.py`);
the engine is plain Python (`core/`).

## Download

1. Download `NotAFK-x.y.z.zip` from [Releases](https://github.com/ItsRegnalt/NotAFK/releases) and unzip it anywhere.
2. Run `NotAFK.exe`. The EXE is not code-signed, so Windows SmartScreen may warn on first start:
   click **More info → Run anyway**.
3. Updates: NotAFK checks GitHub for a newer release at startup and offers to install it
   (Settings → Check for updates now). Your saved automations are kept.

## Run from source

- Double-click `Automate_Baslat.bat`, or `python main.py`
- Needs the Microsoft Edge WebView2 Runtime (built into Windows 11; NotAFK offers the download if it is missing)
- Dev requirements: Python 3.10+, `pip install pywebview pynput`, Node.js for the UI (`cd v2 && npm install`)

## Features

- **Steps:** click (left/right/middle/double, repeat), move, text, key (press/hold), delay, **repeat blocks** (nestable),
  per-step run chance (randomly skip a step now and then); human-like, irregular mouse paths
- **Record:** captures your clicks and typing as steps; finish with the stop hotkey or Esc
- **Background mode:** sends input to one chosen window (PostMessage), so your mouse and keyboard stay free.
  Works with most desktop apps (Notepad, Office...), not with games that read raw input
- **Run options:** once / N times / loop, global random delay, stop after N minutes, minimize while running
- **Saved automations** (steps + settings), import/export as `.json`, configurable start/stop hotkeys (Esc always stops)
- Opens where you left off; scales down to fit small or high-DPI screens; single instance

## Build the EXE

`Build_EXE.bat` builds the UI and packages everything with PyInstaller (`Automate.spec`) into `dist\NotAFK\NotAFK.exe` (~26 MB).

## Tests

All tests run in a hidden window, never take focus, use no real mouse/keyboard input, and use their own
port (47833) and storage, so they don't touch a running NotAFK or your saved automations:

```bash
python tests/startup_test.py
python tests/e2e.py
python tests/features_test.py
python tests/background_test.py
```

`python tests/e2e.py --real-input` additionally drives the real mouse/keyboard (don't touch them meanwhile).

## License

MIT, see [LICENSE](LICENSE).
