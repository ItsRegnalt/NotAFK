"""End-to-end test of NotAFK (WebView2 shell + React v2).
Default: non-intrusive - the window stays hidden, never takes focus, no real mouse/keyboard input
(hotkeys and picks are simulated as the events the shell would send).
--real-input: also drives the real mouse/keyboard (move/click/type, F6/F7, pick overlay, maximize,
window drag/resize); only clicks inside the app's own window. Don't touch input meanwhile.
Usage: python tests/e2e.py [main|persist-check] [--real-input]"""
import ctypes, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tempfile as _tf
os.environ['NOTAFK_PORT'] = '47833'
TEST_STORAGE = os.path.join(_tf.gettempdir(), 'notafk_test_storage')
import webview
from pynput.keyboard import Controller as KB, Key
from pynput.mouse import Controller as MS, Button
import ui.webview_shell as shell
from core.humanizer import get_real_cursor_pos, set_real_cursor_pos

PHASE = next((a for a in sys.argv[1:] if not a.startswith("--")), "main")
REAL = "--real-input" in sys.argv
user32 = ctypes.windll.user32
api = shell.Api()
win = webview.create_window('NotAFK', os.path.join(shell.ROOT, 'v2', 'dist', 'index.html'), js_api=api,
                            x=100, y=100, width=1440, height=900, min_size=(1280, 880), frameless=True,
                            easy_drag=False, background_color=shell.BG,
                            on_top=REAL, hidden=not REAL, focus=REAL)
results = []


class RECT(ctypes.Structure):
    _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long), ("r", ctypes.c_long), ("b", ctypes.c_long)]


def rect():
    r = RECT(); user32.GetWindowRect(api._hwnd(), ctypes.byref(r)); return r


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


def n_events():
    return js("window.__ev.length")


def screen_center(selector_js):
    r = json.loads(js(f"(()=>{{const r=({selector_js}).getBoundingClientRect();return JSON.stringify([r.left,r.top,r.width,r.height])}})()"))
    w = rect()
    dpr = js("devicePixelRatio")
    return int(w.l + (r[0] + r[2] / 2) * dpr), int(w.t + (r[1] + r[3] / 2) * dpr)


SET_INPUT = """(v=>{const i=document.querySelector('form input');
 Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(i,v);
 i.dispatchEvent(new Event('input',{bubbles:true}));})"""
HL = "[...document.querySelectorAll('[data-step-id]')].filter(e=>e.className.includes('border-[#0A84FF]')).map(e=>e.dataset.stepId).join()"
RECENT = "[...document.querySelectorAll('.left-col div[class*=cursor-pointer] span.truncate')].map(s=>s.textContent).join()"


def click_text(text, scope="document"):
    return js(f"(()=>{{const b=[...{scope}.querySelectorAll('button')].find(b=>b.textContent.trim()==={json.dumps(text)});if(b)b.click();return !!b}})()")


def store():
    return json.loads(js("localStorage.getItem('notafk.macros')||'{}'"))


def main():
    r = json.loads(js("JSON.stringify({bridge:!!window.notafkBridge, desktop:document.documentElement.classList.contains('desktop'), steps:document.querySelectorAll('[data-step-id]').length})"))
    check("UI loaded + bridge connected", r["bridge"] and r["desktop"], r)
    w = rect()
    check("window default size", (w.r - w.l, w.b - w.t) == (1440, 900), f"{w.r - w.l}x{w.b - w.t}")
    sh, ch = json.loads(js("(()=>{const c=document.querySelector('.left-col');return JSON.stringify([c.scrollHeight,c.clientHeight])})()"))
    check("left menu fits (no scroll)", sh <= ch, f"content {sh}px / area {ch}px")

    # test steps arrive the way a recording does (the app starts with the user's last session)
    js("[...document.querySelectorAll('button')].find(b=>b.textContent.trim()==='Clear All Steps').click()")
    api._emit('recorded', [{"id": f"step-{i}", "enabled": True, "type": "delay", "duration": "0,5"} for i in range(1, 6)])
    time.sleep(0.3)
    check("recorded steps appended to timeline", js("document.querySelectorAll('[data-step-id]').length") == 5)

    # 1) delay automation: highlight + telemetry + cycle counter + finish
    n = n_events()
    api.startMacro(json.dumps({"steps": [{"id": "step-1", "enabled": True, "type": "delay", "duration": "0,6"},
                                         {"id": "step-5", "enabled": True, "type": "delay", "duration": "0,6"}],
                               "runMode": "repeat", "repeatCount": 2, "globalDelayEnabled": False}))
    time.sleep(0.3)
    check("running step highlighted (#1)", js(HL) == "step-1", js(HL))
    time.sleep(0.6)
    check("highlight moved to next step (#5)", js(HL) == "step-5", js(HL))
    check("automation finished normally", wait_event("finished", n) is True)
    log = js("document.body.textContent.split('Live Telemetry')[1]||''")
    check("telemetry shows steps/cycles", "Step #1" in log and "Cycle 2 / 2" in log and "Status: Complete" in log)
    cyc = json.loads(js(f"JSON.stringify(window.__ev.slice({n}).filter(e=>e[0]==='cycle').map(e=>[e[1].current,e[1].total]))"))
    check("cycle events 1/2 and 2/2", cyc == [[1, 2], [2, 2]], cyc)
    check("highlight cleared after finish", js(HL) == "", js(HL))

    # 2) loop mode stops on Stop
    n = n_events()
    api.startMacro(json.dumps({"steps": [{"id": "step-5", "enabled": True, "type": "delay", "duration": "0,3"}],
                               "runMode": "loop", "globalDelayEnabled": False}))
    time.sleep(1.0)
    api.stopMacro()
    check("loop mode stops on Stop", wait_event("finished", n, 3) is False)

    # 3) real mouse/keyboard: move + click into the rename input, type, Backspace
    if not REAL:
        js("document.querySelector('button[title=Rename]').click()"); time.sleep(0.3)  # section 4 needs the dialog open
    else:
        js("document.querySelector('button[title=Rename]').click()"); time.sleep(0.3)
        js(f"{SET_INPUT}('base')")
        ix, iy = screen_center("document.querySelector('form input')")
        n = n_events()
        api.startMacro(json.dumps({"steps": [
            {"id": "m", "enabled": True, "type": "move", "coords": {"x": ix - 120, "y": iy + 60}},
            {"id": "c", "enabled": True, "type": "click", "coords": {"x": ix, "y": iy}, "button": "Left click", "times": "1"},
            {"id": "t", "enabled": True, "type": "text", "textValue": "XYZ", "keyDelay": "0,03"},
            {"id": "k", "enabled": True, "type": "key", "keyName": "Backspace", "keyMode": "press"},
        ], "runMode": "once", "globalDelayEnabled": True, "minDelay": "0,1", "maxDelay": "0,2",
            "movementEnabled": True, "mouseSpeed": "1,5", "curvePercent": 25, "targetJitter": "2"}))
        check("move/click/text/key automation finished", wait_event("finished", n, 15) is True)
        cx, cy = get_real_cursor_pos()
        check("cursor ended on click target (+-jitter)", abs(cx - ix) <= 3 and abs(cy - iy) <= 3, f"target {ix},{iy} got {cx},{cy}")
        val = js("document.querySelector('form input')?.value")
        check("click focused input, text typed, Backspace pressed", isinstance(val, str) and val.endswith("XY") and not val.endswith("XYZ"), repr(val))


    # 4) rename -> save -> recent list -> delete (own test name, removed again)
    js(f"{SET_INPUT}('__e2e_test__')")
    js("document.querySelector('form button[type=submit]').click()"); time.sleep(0.2)
    check("rename dialog applied", js("document.querySelector('.left-col button span.truncate')?.textContent") == "__e2e_test__")
    click_text("Save", "document.querySelector('.left-col')"); time.sleep(0.3)
    check("automation saved to storage", "__e2e_test__" in store())
    check("saved automation listed in Recently used", "__e2e_test__" in js(RECENT), js(RECENT))
    js("[...document.querySelectorAll('.left-col div[class*=cursor-pointer]')].find(d=>d.textContent.includes('__e2e_test__')).querySelector('button[title=Delete]').click()")
    time.sleep(0.2)
    check("delete asks for confirmation (in-app dialog)", js("document.body.textContent.includes('Delete Automation')"))
    js("document.querySelector('form button[type=submit]').click()"); time.sleep(0.3)
    check("automation deleted from storage + list", "__e2e_test__" not in store() and "__e2e_test__" not in js(RECENT))

    # 5) global hotkeys F6/F7 (F6 runs the UI's own steps: replace demo steps with one delay first)
    click_text("Clear All Steps"); time.sleep(0.2)
    js("[...document.querySelectorAll('.left-col button')].find(b=>b.textContent.includes('Add Delay')).click()"); time.sleep(0.3)
    check("UI steps replaced by single delay", js("document.querySelectorAll('[data-step-id]').length") == 1)
    n = n_events()
    if REAL:
        kb = KB()
        kb.press(Key.f6); kb.release(Key.f6)
        check("F6 hotkey reaches UI", wait_event("hotkey", n, 2) == "start")
    else:
        api._emit('hotkey', 'start')  # what the pynput listener sends on F6
    check("F6 started a run", wait_event("status", n, 2) is not None)
    if REAL:
        kb.press(Key.f7); kb.release(Key.f7)
    else:
        api._emit('hotkey', 'stop')
    check("F7 stopped the run", wait_event("finished", n, 15) is not None)
    time.sleep(0.5)

    # 6) coordinate picker: window minimizes, overlay click returns coords, window restores
    js("[...document.querySelectorAll('.left-col button')].find(b=>b.textContent.includes('Add Move')).click()"); time.sleep(0.3)
    move_id = js("[...document.querySelectorAll('[data-step-id]')].at(-1).dataset.stepId")
    n = n_events()
    px, py = 400, 300
    if REAL:
        api.pickCoordinate(move_id)
        time.sleep(1.5)
        check("pick: app minimized + overlay shown", user32.IsIconic(api._hwnd()) and api._picker is not None)
        ms = MS(); ms.position = (px, py); time.sleep(0.2)
        ms.click(Button.left)
        got = wait_event("picked", n, 4)
        check("pick returns clicked coords", got == {"id": move_id, "x": px, "y": py}, got)
        time.sleep(0.8)
        check("pick: window restored", not user32.IsIconic(api._hwnd()))
    else:
        api._emit('picked', {'id': move_id, 'x': px, 'y': py})  # what the overlay sends on click
        time.sleep(0.3)
    coords = js(f"[...document.querySelectorAll('[data-step-id=\"{move_id}\"] button')].map(b=>b.textContent).join()")
    check("picked coords shown on Move step", f"X:{px}" in coords and f"Y:{py}" in coords, coords)

    if REAL:  # 7) + 8) need a visible window and the real mouse
        # 7) maximize respects the taskbar, restore returns
        api.toggleMaximize(); time.sleep(1.0)
        m = rect()
        work = RECT(); user32.SystemParametersInfoW(0x30, 0, ctypes.byref(work), 0)  # SPI_GETWORKAREA (primary)
        m1 = js("document.documentElement.classList.contains('maximized')")
        check("maximize fills work area (taskbar visible)", (m.l, m.t, m.r, m.b) == (work.l, work.t, work.r, work.b), f"{(m.l, m.t, m.r, m.b)} vs {(work.l, work.t, work.r, work.b)}")
        api.toggleMaximize(); time.sleep(1.0)
        m2 = js("document.documentElement.classList.contains('maximized')")
        check("maximize/restore toggles UI state", m1 is True and m2 is False, f"{m1},{m2}")

        # 8) title-bar drag moves the window; edge drag resizes it
        w = rect()
        tx, ty = w.l + 300, w.t + 15
        ms.position = (tx, ty); time.sleep(0.2); ms.press(Button.left); time.sleep(0.15)
        for i in range(1, 21):
            ms.position = (tx + i * 5, ty + i * 3); time.sleep(0.02)
        ms.release(Button.left); time.sleep(0.4)
        w2 = rect()
        check("title bar drag moves window", (w2.l - w.l, w2.t - w.t) == (100, 60), f"moved {w2.l - w.l},{w2.t - w.t}")
        ex, ey = w2.r - 3, w2.t + 400
        ms.position = (ex, ey); time.sleep(0.2); ms.press(Button.left); time.sleep(0.15)
        for i in range(1, 21):
            ms.position = (ex + i * 5, ey); time.sleep(0.02)
        ms.release(Button.left); time.sleep(0.4)
        w3 = rect()
        check("edge drag resizes window", (w3.r - w3.l) - (w2.r - w2.l) == 100, f"width {w2.r - w2.l} -> {w3.r - w3.l}")

    js("localStorage.setItem('notafk.e2e.persist','1')")


def persist_check():
    check("storage persists across app restart", js("localStorage.getItem('notafk.e2e.persist')") == "1")
    js("localStorage.removeItem('notafk.e2e.persist')")


def run(window):
    api._start(window)
    time.sleep(3)
    session = js("localStorage.getItem('notafk.session')")  # the test edits steps; give the user theirs back
    js("window.__ev=[];['status','step','cycle','finished','picked','pick-cancelled','hotkey'].forEach(n=>addEventListener('notafk:'+n,e=>window.__ev.push([n,e.detail])))")
    user = get_real_cursor_pos() if REAL else None
    try:
        main() if PHASE == "main" else persist_check()
    except Exception as exc:
        check("test crashed", False, repr(exc))
    finally:
        if session is not None:
            js(f"localStorage.setItem('notafk.session', {json.dumps(session)})")
        if user:
            set_real_cursor_pos(*user)
        print(f"SUMMARY {sum(results)}/{len(results)} passed", flush=True)
        time.sleep(0.3)
        window.destroy()


storage = os.path.join(os.environ['LOCALAPPDATA'], 'NotAFK', 'webview')
webview.start(run, [win], http_server=True, http_port=shell.HTTP_PORT, private_mode=False, storage_path=TEST_STORAGE)
