"""Background-mode test. Non-intrusive: the app window stays hidden, the target window sits off-screen
and never takes focus, and no real mouse/keyboard input is used.  Usage: python tests/background_test.py"""
import ctypes, json, os, subprocess, sys, tempfile, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import tempfile as _tf
os.environ['NOTAFK_PORT'] = '47833'
TEST_STORAGE = os.path.join(_tf.gettempdir(), 'notafk_test_storage')
import webview
import ui.webview_shell as shell
import core.humanizer as humanizer

# Count every call that would touch the real mouse/keyboard (checking the cursor position
# instead would be flaky while someone is using the PC during the test).
real_input_calls = []
def _spy(name, fn):
    def wrapper(*a, **k):
        real_input_calls.append(name)
        return fn(*a, **k)
    return wrapper
humanizer.set_real_cursor_pos = _spy('set_real_cursor_pos', humanizer.set_real_cursor_pos)
for _name in ('smooth_move', 'click', 'type_text', 'press_key'):
    setattr(humanizer.Humanizer, _name, _spy(_name, getattr(humanizer.Humanizer, _name)))

user32 = ctypes.windll.user32
results = []
api = shell.Api()
win = webview.create_window('NotAFK', os.path.join(shell.ROOT, 'v2', 'dist', 'index.html'), js_api=api,
                            width=1440, height=900, frameless=True, easy_drag=False,
                            background_color=shell.BG, hidden=True, focus=False)


def check(name, ok, detail=""):
    results.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""), flush=True)


def js(code):
    return win.evaluate_js(code)


def wait_event(name, since, timeout=8.0):
    end = time.time() + timeout
    while time.time() < end:
        hit = js(f"JSON.stringify(window.__ev.slice({since}).find(e=>e[0]==='{name}')||null)")
        if hit and hit != 'null':
            return json.loads(hit)[1]
        time.sleep(0.05)
    return None


def start_target():
    out = tempfile.mktemp(suffix='.json')
    proc = subprocess.Popen([sys.executable, os.path.join(ROOT, 'tests', 'bg_target.py'), out],
                            stdout=subprocess.PIPE, text=True)
    _, hwnd, tx, ty = proc.stdout.readline().split()
    return proc, out, int(hwnd), int(tx), int(ty)


def stop_target(proc, out, hwnd):
    user32.PostMessageW(hwnd, 0x10, 0, 0)  # WM_CLOSE -> target writes what it received
    proc.wait(10)
    return json.load(open(out, encoding='utf-8'))


def main():
    proc, out, hwnd, tx, ty = start_target()

    # UI: card present, right column still fits
    fits = json.loads(js("(()=>{const c=[...document.querySelectorAll('.lg\\\\:col-span-3')].at(-1);return JSON.stringify([c.scrollHeight,c.clientHeight])})()"))
    check("Background Mode card shown", js("document.body.textContent.includes('Background Mode')"))
    check("right column fits (no scroll)", fits[0] <= fits[1], f"{fits[0]}px / {fits[1]}px")

    # Picking a window ends in a 'target' event -> UI shows it and enables the mode
    api._emit('target', {'hwnd': hwnd, 'title': 'NotAFK BG Target'})
    time.sleep(0.3)
    check("target shown in card", "NotAFK BG Target" in js("document.body.textContent"))
    check("background mode auto-enabled", js("[...document.querySelectorAll('input[type=checkbox]')].find(i=>i.closest('div.rounded-xl')?.textContent.includes('Background Mode'))?.checked") is True)

    # Start from the UI sends backgroundEnabled + targetHwnd (capture config, run a harmless delay)
    js("window.__cfg=null;const o=window.notafkBridge.startMacro;window.notafkBridge.startMacro=(raw)=>{window.__cfg=raw;return o(raw)}")
    js("[...document.querySelectorAll('button')].find(b=>b.textContent.trim()==='Clear All Steps').click()")
    time.sleep(0.2)
    js("[...document.querySelectorAll('.left-col button')].find(b=>b.textContent.includes('Add Delay')).click()")
    time.sleep(0.2)
    n = js("window.__ev.length")
    js("[...document.querySelectorAll('button')].find(b=>b.textContent.includes('Start (F6)')).click()")
    time.sleep(0.3)
    cfg = json.loads(js("window.__cfg") or "{}")
    check("UI config carries background target", cfg.get("backgroundEnabled") is True and cfg.get("targetHwnd") == hwnd,
          {k: cfg.get(k) for k in ("backgroundEnabled", "targetHwnd")})
    wait_event("finished", n, 10)
    js("window.notafkBridge.stopMacro()")
    time.sleep(0.5)

    # Real run: click into the target's text box, type (incl. non-ASCII), Backspace, Enter
    n = js("window.__ev.length")
    api.startMacro(json.dumps({"steps": [
        {"id": "c", "enabled": True, "type": "click", "coords": {"x": tx, "y": ty}, "button": "Left click", "times": "1"},
        {"id": "t", "enabled": True, "type": "text", "textValue": "Merhaba dünya", "keyDelay": "0,02"},
        {"id": "k", "enabled": True, "type": "key", "keyName": "Backspace", "keyMode": "press"},
        {"id": "e", "enabled": True, "type": "key", "keyName": "Enter", "keyMode": "press"},
        {"id": "t2", "enabled": True, "type": "text", "textValue": "2", "keyDelay": "0,02"},
    ], "runMode": "once", "globalDelayEnabled": True, "minDelay": "0,05", "maxDelay": "0,1",
        "movementEnabled": True, "targetJitter": "0", "backgroundEnabled": True, "targetHwnd": hwnd}))
    check("background automation finished", wait_event("finished", n, 15) is True)
    time.sleep(0.3)
    check("real mouse/keyboard never used", not real_input_calls, real_input_calls)
    # the user may switch windows meanwhile; what matters is that neither test window took the focus
    check("no focus stealing (app/target never in front)", user32.GetForegroundWindow() not in (api._hwnd(), hwnd))
    got = stop_target(proc, out, hwnd)
    # the click put the caret before "5", so the typing lands in the middle of "0123456789"
    check("click landed at the right spot + text, Backspace, Enter typed", got["text"] == "01234Merhaba düny\r\n256789", repr(got["text"]))

    # Closed target -> clear error instead of typing into the wrong place
    n = js("window.__ev.length")
    api.startMacro(json.dumps({"steps": [{"id": "t", "enabled": True, "type": "text", "textValue": "x"}],
                               "runMode": "once", "backgroundEnabled": True, "targetHwnd": hwnd}))
    st = wait_event("status", n, 3)
    check("closed target gives a clear error", isinstance(st, str) and "Target window not found" in st, st)


def run(window):
    api._start(window)
    time.sleep(3)
    session = js("localStorage.getItem('notafk.session')")  # the test edits steps; give the user theirs back
    js("window.__ev=[];['status','finished','target'].forEach(n=>addEventListener('notafk:'+n,e=>window.__ev.push([n,e.detail])))")
    try:
        main()
    except Exception as exc:
        check("test crashed", False, repr(exc))
    finally:
        if session is not None:
            js(f"localStorage.setItem('notafk.session', {json.dumps(session)})")
        print(f"SUMMARY {sum(results)}/{len(results)} passed", flush=True)
        window.destroy()


webview.start(run, [win], http_server=True, http_port=shell.HTTP_PORT, private_mode=False,
              storage_path=TEST_STORAGE)
