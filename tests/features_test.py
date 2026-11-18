"""Feature tests: repeat blocks, time limit, window-relative background clicks, saved settings,
import/export, hotkey settings, target re-finding, recorder, session restore, English UI.
Non-intrusive: hidden app window, off-screen target that never takes focus, no real mouse/keyboard input.
The user's saved automations, session and preferences are restored afterwards.
Usage: python tests/features_test.py"""
import ctypes, json, os, re, subprocess, sys, tempfile, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import tempfile as _tf
os.environ['NOTAFK_PORT'] = '47833'
TEST_STORAGE = os.path.join(_tf.gettempdir(), 'notafk_test_storage')
import webview
from pynput import keyboard, mouse
import ui.webview_shell as shell

user32 = ctypes.windll.user32
results = []
api = shell.Api()
win = webview.create_window('NotAFK', os.path.join(shell.ROOT, 'v2', 'dist', 'index.html'), js_api=api,
                            width=1440, height=900, frameless=True, easy_drag=False,
                            background_color=shell.BG, hidden=True, focus=False)
STORE_KEYS = ('notafk.macros', 'notafk.session', 'notafk.prefs')


def check(name, ok, detail=""):
    results.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""), flush=True)


def js(code):
    return win.evaluate_js(code)


def n_events():
    return js("window.__ev.length")


def events(since, name):
    return json.loads(js(f"JSON.stringify(window.__ev.slice({since}).filter(e=>e[0]==='{name}').map(e=>e[1]))"))


def wait_event(name, since, timeout=8.0):
    end = time.time() + timeout
    while time.time() < end:
        hit = events(since, name)
        if hit:
            return hit[0]
        time.sleep(0.05)
    return None


def click(selector_js):
    return js(f"(()=>{{const b={selector_js};if(b)b.click();return !!b}})()")


def button_with_text(text, scope="document"):
    return f"[...{scope}.querySelectorAll('button')].find(b=>b.textContent.trim()==={json.dumps(text)})"


def set_value(selector_js, value, tag='Input'):
    """Set a React-controlled input/select the way typing would."""
    js(f"""(()=>{{const el={selector_js};
      Object.getOwnPropertyDescriptor(HTML{tag}Element.prototype,'value').set.call(el,{json.dumps(value)});
      el.dispatchEvent(new Event('{'change' if tag == 'Select' else 'input'}',{{bubbles:true}}));}})()""")


def run_steps(steps, **config):
    n = n_events()
    api.startMacro(json.dumps({"steps": steps, "runMode": "once", "globalDelayEnabled": False, **config}))
    return n


def delay(i, d="0,1"):
    return {"id": i, "enabled": True, "type": "delay", "duration": d}


def start_target():
    out = tempfile.mktemp(suffix='.json')
    proc = subprocess.Popen([sys.executable, os.path.join(ROOT, 'tests', 'bg_target.py'), out], stdout=subprocess.PIPE, text=True)
    _, hwnd, tx, ty = proc.stdout.readline().split()
    return proc, out, int(hwnd), int(tx), int(ty)


def main():
    check("test window stays hidden", not user32.IsWindowVisible(api._hwnd()))

    # English UI
    text = js("document.body.textContent")
    check("UI text is English (no Turkish letters)", not re.search("[çğıöşüÇĞİÖŞÜ]", text))

    # Repeat block: [loop x3: a, b] c -> 7 steps
    n = run_steps([{"id": "L", "enabled": True, "type": "loop", "times": "3"}, delay("a"), delay("b"),
                   {"id": "L-end", "enabled": True, "type": "loopEnd", "loopOwnerId": "L"}, delay("c")])
    wait_event("finished", n)
    ids = [e["id"] for e in events(n, "step")]
    check("repeat block runs its body 3 times", ids == ["a", "b"] * 3 + ["c"], ids)

    # Random step skipping: 0% never runs, 100% always, 50% roughly half of 200 times
    def chance_step(i, c):
        return {**delay(i, "0"), "chance": c}
    n = run_steps([{"id": "R", "enabled": True, "type": "loop", "times": "200"},
                   chance_step("never", "0"), chance_step("always", "100"), chance_step("half", "50"),
                   {"id": "R-end", "enabled": True, "type": "loopEnd", "loopOwnerId": "R"}])
    wait_event("finished", n, 20)
    ids = [e["id"] for e in events(n, "step")]
    counts = {k: ids.count(k) for k in ("never", "always", "half")}
    check("run chance: 0% never, 100% always, 50% about half", counts["never"] == 0 and counts["always"] == 200
          and 60 <= counts["half"] <= 140, counts)
    api._emit('recorded', [delay("ch1")])
    time.sleep(0.3)
    box = "document.querySelector('[data-step-id=ch1] input[aria-label=\"Run chance in percent\"]')"
    set_value(box, "35")
    time.sleep(0.3)
    sess = json.loads(js("localStorage.getItem('notafk.session')"))
    check("run chance input on step cards is saved", next(x for x in sess["steps"] if x["id"] == "ch1").get("chance") == "35")

    # Time limit: endless loop stops by itself (0,05 min = 3 s)
    t0 = time.time()
    n = n_events()
    api.startMacro(json.dumps({"steps": [delay("d", "0,3")], "runMode": "loop", "globalDelayEnabled": False, "timeLimit": "0,05"}))
    fin = wait_event("finished", n, 8)
    took = time.time() - t0
    check("time limit stops an endless run", fin is True and 2.5 <= took <= 5 and "Status: Time limit reached" in events(n, "status"),
          f"{took:.1f}s {events(n, 'status')[-1:]}")

    # Background target: click relative to the window after it moved
    proc, out, hwnd, tx, ty = start_target()
    r = shell.window_rect(hwnd)
    rel_char5 = {"x": tx - r.left, "y": ty - r.top}
    bg = {"backgroundEnabled": True, "targetHwnd": hwnd}
    user32.SetWindowPos(hwnd, 0, -7200, -6400, 0, 0, 0x1 | 0x4 | 0x10)  # move it: NOSIZE|NOZORDER|NOACTIVATE
    n = run_steps([{"id": "c", "enabled": True, "type": "click", "coords": {"x": 0, "y": 0, "rel": rel_char5},
                    "button": "Left click", "times": "1"},
                   {"id": "t", "enabled": True, "type": "text", "textValue": "OK", "keyDelay": "0,02"}],
                  targetJitter="0", **bg)
    wait_event("finished", n, 8)
    check("target re-found by title (new handle)", api.resolveTarget(1, "NotAFK BG Target") == hwnd)
    n = run_steps([{"id": "dr", "enabled": True, "type": "drag", "button": "Left click", "duration": "0,3",
                    "coords": {"x": 0, "y": 0, "rel": rel_char5},
                    "to": {"x": 0, "y": 0, "rel": {"x": rel_char5["x"] + 25, "y": rel_char5["y"]}}},
                   {"id": "z", "enabled": True, "type": "text", "textValue": "Z", "keyDelay": "0,02"}], **bg)
    wait_event("finished", n, 8)
    user32.PostMessageW(hwnd, 0x10, 0, 0)
    proc.wait(10)
    got = json.load(open(out, encoding='utf-8'))["text"]
    check("click hits the same spot after the window moved", got.startswith("01234"), repr(got))
    check("background drag selects text (typing replaces the selection)",
          "Z" in got and "OK" not in got and len(got) < len("01234OK56789"), repr(got))

    # Saved automation keeps its settings
    js("document.querySelector('button[title=Rename]').click()")
    time.sleep(0.2)
    set_value("document.querySelector('form input')", "__feat_test__")
    click("document.querySelector('form button[type=submit]')")
    time.sleep(0.2)
    limit_input = "document.querySelector('input[aria-label=\"Time limit in minutes\"]')"
    set_value(limit_input, "7")
    click(button_with_text("Save", "document.querySelector('.left-col')"))
    time.sleep(0.3)
    set_value(limit_input, "9")
    time.sleep(0.2)
    click("[...document.querySelectorAll('.left-col div[class*=cursor-pointer]')].find(d=>d.textContent.includes('__feat_test__'))")
    time.sleep(0.3)
    check("loading an automation restores its settings", js(f"{limit_input}.value") == "7", js(f"{limit_input}.value"))

    # Export / import (file dialogs answered by the test)
    path = os.path.join(tempfile.gettempdir(), 'notafk_feat_export.json')
    win.create_file_dialog = lambda *a, **k: path
    click("document.querySelector('button[title=\"Export to file\"]')")
    time.sleep(0.8)
    data = json.load(open(path, encoding='utf-8'))
    check("export writes steps + settings", data.get("name") == "__feat_test__" and data["settings"].get("timeLimit") == "7"
          and isinstance(data.get("steps"), list), {k: data.get(k) for k in ("name", "version")})
    data["name"] = "__feat_import__"
    json.dump(data, open(path, "w", encoding='utf-8'))
    win.create_file_dialog = lambda *a, **k: [path]
    click("document.querySelector('button[title=\"Import from file\"]')")
    time.sleep(0.8)
    saved = json.loads(js("localStorage.getItem('notafk.macros')") or "{}")
    check("import loads and saves the automation", "__feat_import__" in saved
          and js("document.querySelector('.left-col button span.truncate')?.textContent") == "__feat_import__")
    json.dump({"hello": 1}, open(path, "w", encoding='utf-8'))
    click("document.querySelector('button[title=\"Import from file\"]')")
    time.sleep(0.6)
    toast = js("[...document.querySelectorAll('div.fixed span')].map(s=>s.textContent).join(' | ')")
    check("import rejects a non-NotAFK file", "not a NotAFK automation" in toast, toast)
    os.remove(path)

    # Hotkey settings reach the native listener
    click("document.querySelector('button[title=Settings]')")
    time.sleep(0.2)
    set_value("[...document.querySelectorAll('select')].find(s=>s.closest('label')?.textContent.includes('Start hotkey'))", "F8", "Select")
    time.sleep(0.4)
    check("start hotkey changed to F8", api._hotkeys == {"start": "F8", "stop": "F7"} and api._hotkey_name(keyboard.Key.f8) == "start"
          and js("document.body.textContent.includes('Start (F8)')"), api._hotkeys)
    set_value("[...document.querySelectorAll('select')].find(s=>s.closest('label')?.textContent.includes('Start hotkey'))", "F7", "Select")
    time.sleep(0.4)
    check("picking the stop key for start swaps them", api._hotkeys == {"start": "F7", "stop": "F8"}, api._hotkeys)
    click(button_with_text("Done"))

    # Recorder (fed synthetic events, no real input)
    K, KC = keyboard.Key, keyboard.KeyCode

    def tap(rec, key, hold=0.0):
        rec._on_press(key)
        if hold:
            for _ in range(5):
                rec._on_press(key)  # auto-repeat while held must be ignored
            time.sleep(hold)
        rec._on_release(key)

    def summary(steps):
        return [(x["type"], x.get("button") or x.get("textValue") or x.get("keyName") or x.get("amount") or "",
                 x.get("keyMode", ""), "+".join(x.get("modifiers", []))) for x in steps]

    rec = shell.Recorder(api)
    def mouse_click(rec, x, y, hold=0.0, to=None):
        rec._on_click(x, y, mouse.Button.left, True)
        time.sleep(hold)
        rec._on_click(*(to or (x, y)), mouse.Button.left, False)

    mouse_click(rec, 100, 100)
    mouse_click(rec, 101, 100)  # quick second click -> double click
    time.sleep(0.3)
    for ch in "hi x":
        tap(rec, K.space if ch == " " else KC.from_char(ch))
    tap(rec, K.backspace)
    tap(rec, K.enter)
    tap(rec, K.f7)  # the stop hotkey is not recorded
    got = summary(rec.stop())
    check("recorder: double click, pause, typed text, Enter",
          [g[:2] for g in got] == [("click", "Double click"), ("delay", ""), ("text", "hi "), ("key", "Enter")], got)

    rec = shell.Recorder(api)
    tap(rec, KC.from_char('w'), hold=0.5)  # held W (e.g. walking in a game)
    time.sleep(0.3)
    tap(rec, KC.from_char('e'))  # a lone tap
    time.sleep(1.2)
    rec._on_press(K.ctrl_l)
    tap(rec, KC(vk=0x43, char='\x03'))  # Ctrl+C (Windows reports a control char, the letter comes from the vk)
    rec._on_release(K.ctrl_l)
    rec._on_press(K.shift)
    tap(rec, KC.from_char('A'))  # Shift+a is just typing a capital letter
    tap(rec, KC.from_char('B'))
    rec._on_release(K.shift)
    for dy in (-1, -1, -1):
        rec._on_scroll(300, 300, 0, dy)  # one wheel gesture
    time.sleep(0.3)
    mouse_click(rec, 500, 500, hold=0.5)  # long press
    time.sleep(0.3)
    mouse_click(rec, 600, 600, hold=0.3, to=(900, 650))  # drag a file / folder
    steps = rec.stop()
    press = next(x for x in steps if x["type"] == "click")
    drag = next((x for x in steps if x["type"] == "drag"), {})
    check("recorder: long press keeps its hold time, moving while pressed is a drag",
          0.45 <= float(press.get("holdTime", "0").replace(",", ".")) <= 0.8
          and drag.get("coords", {}).get("x") == 600 and drag.get("to", {}).get("x") == 900, (press.get("holdTime"), drag))
    steps = [x for x in steps if x["type"] not in ("click", "drag")]
    got = summary(steps)
    kinds = [g for g in got if g[0] != "delay"]
    hold = next(x for x in steps if x.get("keyMode") == "hold")
    hold_len = float(next(x for x in steps if x.get("holdOwnerId") == hold["id"] and x["type"] == "delay")["duration"].replace(",", "."))
    check("recorder: held key -> Hold with its real length (auto-repeat ignored)",
          kinds[0] == ("key", "W", "hold", "") and kinds[1] == ("key", "W", "release", "") and 0.45 <= hold_len <= 0.8, (kinds[:2], hold_len))
    check("recorder: lone tap -> key press, Ctrl+C -> shortcut, Shift letters -> text, wheel -> one scroll step",
          kinds[2:] == [("key", "E", "press", ""), ("key", "C", "press", "Ctrl"), ("text", "AB", "", ""), ("scroll", "-3", "", "")], kinds[2:])

    # Engine: Ctrl+C presses Ctrl around C; scroll turns the wheel (fake devices, nothing real happens)
    import core.humanizer as hz
    log, times = [], []

    def note(*entry):
        log.append(entry)
        times.append(time.time())

    class FakeKeyboard:
        def press(self, k): note("down", str(k))
        def release(self, k): note("up", str(k))
        def type(self, c): note("type", c)

    class FakeMouse:
        def scroll(self, dx, dy): note("wheel", dy)
        def press(self, b): note("mdown", str(b))
        def release(self, b): note("mup", str(b))

    real = (hz.KeyboardController, hz.MouseController, hz.set_real_cursor_pos, hz.Humanizer.smooth_move)
    hz.KeyboardController, hz.MouseController = FakeKeyboard, FakeMouse
    hz.set_real_cursor_pos = lambda x, y: note("cursor", x, y)
    hz.Humanizer.smooth_move = lambda self, x, y, **k: note("move", x, y) or True
    real_pos = hz.get_real_cursor_pos
    hz.get_real_cursor_pos = lambda: (100, 100)  # drag starts where the (fake) cursor is
    try:
        n = run_steps([{"id": "k", "enabled": True, "type": "key", "keyName": "C", "keyMode": "press", "modifiers": ["Ctrl"]},
                       {"id": "s", "enabled": True, "type": "scroll", "coords": {"x": 400, "y": 300}, "amount": "-2"},
                       {"id": "h", "enabled": True, "type": "click", "coords": {"x": 10, "y": 10}, "button": "Left click",
                        "times": "1", "holdTime": "0,4"},
                       {"id": "g", "enabled": True, "type": "drag", "coords": {"x": 100, "y": 100}, "to": {"x": 300, "y": 120},
                        "button": "Left click", "duration": "0,3"}],
                      targetJitter="0")
        wait_event("finished", n, 10)
    finally:
        hz.KeyboardController, hz.MouseController, hz.set_real_cursor_pos, hz.Humanizer.smooth_move = real
        hz.get_real_cursor_pos = real_pos
    keys = [e for e in log if e[0] in ("down", "up")]
    check("engine: Ctrl+C = Ctrl down, C down, C up, Ctrl up",
          keys == [("down", "Key.ctrl"), ("down", "c"), ("up", "c"), ("up", "Key.ctrl")], keys)
    downs = [i for i, e in enumerate(log) if e[0] == "mdown"]
    ups = [i for i, e in enumerate(log) if e[0] == "mup"]
    hold_s = times[ups[0]] - times[downs[0]] if len(downs) >= 2 and len(ups) >= 2 else 0
    moves_while_down = [e for e in log[downs[-1]:ups[-1]] if e[0] == "cursor"] if downs and ups else []
    check("engine: long press holds the button ~0.4 s", 0.35 <= hold_s <= 0.7, round(hold_s, 2))
    check("engine: drag = press, glide to the end point, release",
          len(downs) == 2 and moves_while_down and moves_while_down[-1][1:] == (300, 120), moves_while_down[-1:] if moves_while_down else None)
    check("engine: scroll moves to the point and turns the wheel 2 notches down",
          ("move", 400, 300) in log and [e for e in log if e[0] == "wheel"] == [("wheel", -1), ("wheel", -1)], log[-4:])

    # Native picker (windows created but never shown): click -> cursor point, Esc -> cancelled
    from ui.picker import ScreenPicker
    import threading
    for msg, wp, expect_point in ((0x201, 0, True), (0x100, 0x1B, False)):  # WM_LBUTTONDOWN / WM_KEYDOWN Esc
        done = threading.Event(); got = {}
        picker = ScreenPicker(lambda pt: (got.update(pt=pt), done.set()), visible=False)
        picker.start()
        time.sleep(0.4)
        user32.PostMessageW(picker.overlay, 0x200, 0, 0)  # mouse move -> HUD update
        user32.SendMessageW(picker.hud, 0xF, 0, 0)  # paint the HUD once
        user32.PostMessageW(picker.overlay, msg, wp, 0)
        done.wait(3)
        ok = (isinstance(got.get("pt"), tuple) and len(got["pt"]) == 2) if expect_point else ("pt" in got and got["pt"] is None)
        check(f"picker {'click returns a point' if expect_point else 'Esc cancels'}", ok and not user32.IsWindow(picker.overlay), got)

    # Background target dropdown lists open windows
    wins = api.listWindows()
    check("window list for the target dropdown", isinstance(wins, list) and all(w["title"] and w["hwnd"] != api._hwnd() for w in wins), len(wins))
    click("[...document.querySelectorAll('button')].find(b=>b.closest('div.rounded-xl')?.textContent.includes('Background Mode') && b.querySelector('svg.lucide-chevron-down'))")
    time.sleep(0.6)
    check("dropdown lists windows (no 'Pick on screen')", not js("document.body.textContent.includes('Pick on screen')")
          and (not wins or wins[0]["title"] in js("document.body.textContent")))
    if wins:
        click(f"[...document.querySelectorAll('button')].find(b=>b.textContent==={json.dumps(wins[0]['title'])})")
        time.sleep(0.3)
        check("choosing a window from the list sets the target", wins[0]["title"] in js("document.body.textContent")
              and json.loads(js("localStorage.getItem('notafk.session')"))["target"]["hwnd"] == wins[0]["hwnd"])

    # Repeat block: On/Off switches "Repeat" and "End repeat" together
    click("[...document.querySelectorAll('.left-col button')].find(b=>b.textContent.includes('Add Repeat'))")
    time.sleep(0.3)
    loop_id = js("[...document.querySelectorAll('[data-step-id]')].map(e=>e.dataset.stepId).filter(i=>!i.endsWith('-end')).at(-1)")
    click(f"document.querySelector('[data-step-id=\"{loop_id}\"] label button')")
    time.sleep(0.3)
    rows = {x["id"]: x["enabled"] for x in json.loads(js("localStorage.getItem('notafk.session')"))["steps"]}
    check("turning Repeat off also turns End repeat off", rows.get(loop_id) is False and rows.get(f"{loop_id}-end") is False)

    # Record countdown shows 3-2-1 and can be cancelled (cancelled before it would really record)
    click("[...document.querySelectorAll('button')].find(b=>b.textContent.trim()==='Record')")
    time.sleep(0.3)
    shown = js("document.body.textContent.includes('Recording starts')")
    click("[...document.querySelectorAll('div')].find(d=>d.className.includes('z-[80]'))")
    time.sleep(1.5)
    check("record shows a countdown and cancel works", shown and api._recorder is None
          and not js("document.body.textContent.includes('Recording starts')"))

    # Irregular path: straight at 0 %, more sideways movement at higher %, always ends on target
    import math, random
    from core.humanizer import generate_human_path
    def spread(irr):
        worst = 0
        for _ in range(100):
            a, b = (random.randint(0, 1500), random.randint(0, 900)), (random.randint(0, 1500), random.randint(0, 900))
            if math.hypot(b[0] - a[0], b[1] - a[1]) < 100:
                continue  # pixel rounding dominates on tiny moves
            p = generate_human_path(a, b, irr)
            assert p[-1] == b
            d = math.hypot(b[0] - a[0], b[1] - a[1]) or 1
            worst = max(worst, max(abs((x - a[0]) * -(b[1] - a[1]) / d + (y - a[1]) * (b[0] - a[0]) / d) for x, y in p) / d)
        return worst
    s0, s5, s10 = spread(0), spread(0.5), spread(1.0)
    check("path irregularity scales (0% straight, 100% most irregular)", s0 < 0.02 < s5 < s10, f"{s0:.2f} {s5:.2f} {s10:.2f}")
    d50 = js("document.querySelector('path[stroke^=\"url(#curveGrad\"]').getAttribute('d')")
    set_value("document.querySelector('input[type=range]')", "90")
    time.sleep(0.3)
    check("path preview reacts to irregularity", d50 != js("document.querySelector('path[stroke^=\"url(#curveGrad\"]').getAttribute('d')"))

    # UI: Scroll step card, and modifier chips on Key steps
    click("[...document.querySelectorAll('.left-col button')].find(b=>b.textContent.includes('Add Scroll'))")
    click("[...document.querySelectorAll('.left-col button')].find(b=>b.textContent.includes('Add Key'))")
    time.sleep(0.3)
    key_id = js("[...document.querySelectorAll('[data-step-id]')].at(-1).dataset.stepId")
    click(f"[...document.querySelectorAll('[data-step-id=\"{key_id}\"] button')].find(b=>b.textContent==='Ctrl')")
    time.sleep(0.3)
    steps_now = json.loads(js("localStorage.getItem('notafk.session')"))["steps"]
    check("Scroll step card + Ctrl chip on a Key step", js("document.body.textContent.includes('notches')")
          and next(x for x in steps_now if x["id"] == key_id).get("modifiers") == ["Ctrl"])

    # Session restore after a reload
    api._emit('recorded', [delay("s1"), delay("s2")])
    time.sleep(0.3)
    count = js("document.querySelectorAll('[data-step-id]').length")
    js("location.reload()")
    time.sleep(3)
    check("steps survive a restart (session)", js("document.querySelectorAll('[data-step-id]').length") == count, count)


def run(window):
    api._start(window)
    time.sleep(3)
    backup = {k: js(f"localStorage.getItem('{k}')") for k in STORE_KEYS}
    js("window.__ev=[];['status','step','finished'].forEach(n=>addEventListener('notafk:'+n,e=>window.__ev.push([n,e.detail])))")
    try:
        main()
    except Exception as exc:
        check("test crashed", False, repr(exc))
    finally:
        for k, v in backup.items():
            js(f"localStorage.setItem('{k}', {json.dumps(v)})" if v is not None else f"localStorage.removeItem('{k}')")
        print(f"SUMMARY {sum(results)}/{len(results)} passed", flush=True)
        window.destroy()


webview.start(run, [win], http_server=True, http_port=shell.HTTP_PORT, private_mode=False,
              storage_path=TEST_STORAGE)
