"""
Automate - Humanizer Engine
Simulates realistic human mouse movement, randomized micro-delays,
coordinate jitter, and natural keyboard typing patterns.
"""

import time
import math
import random
import ctypes
from typing import List, Tuple
from pynput.mouse import Controller as MouseController, Button
from pynput.keyboard import Controller as KeyboardController, Key

# Windows API structures for accurate cursor positioning & inputs
class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

def get_real_cursor_pos() -> Tuple[int, int]:
    pt = POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y

def set_real_cursor_pos(x: int, y: int):
    ctypes.windll.user32.SetCursorPos(int(x), int(y))

# Cubic Bezier calculation
def cubic_bezier(p0: Tuple[float, float], p1: Tuple[float, float],
                 p2: Tuple[float, float], p3: Tuple[float, float], t: float) -> Tuple[float, float]:
    u = 1.0 - t
    tt = t * t
    uu = u * u
    uuu = uu * u
    ttt = tt * t
    
    x = uuu * p0[0] + 3 * uu * t * p1[0] + 3 * u * tt * p2[0] + ttt * p3[0]
    y = uuu * p0[1] + 3 * uu * t * p1[1] + 3 * u * tt * p2[1] + ttt * p3[1]
    return x, y

def _wavy_path(x0, y0, x1, y1, irregularity, steps):
    """Points from (x0, y0) to (x1, y1): an S-shaped sideways drift plus small wobbles of random
    frequency/phase (both scale with irregularity), eased speed and a light hand tremor."""
    dx, dy = x1 - x0, y1 - y0
    dist = math.hypot(dx, dy)
    nx, ny = -dy / dist, dx / dist  # unit normal of the straight line
    side = random.choice((-1, 1))
    reach = min(dist, 900)  # very long moves should not swing wildly
    s_amp = reach * irregularity * random.uniform(0.10, 0.22) * side          # S-curve (one bend each way)
    bow = reach * irregularity * random.uniform(-0.12, 0.12)                  # uneven: one bend bigger
    waves = [(reach * irregularity * random.uniform(0.008, 0.025), random.uniform(3, 9), random.uniform(0, 2 * math.pi))
             for _ in range(2)]                                               # small irregular wobbles
    skew = random.uniform(0.4, 0.6)  # where the peak speed is: not always in the exact middle
    path = []
    for i in range(1, steps + 1):
        raw = i / steps
        t = raw ** (math.log(0.5) / math.log(skew))   # skewed timing
        t = t * t * (3.0 - 2.0 * t)                    # ease in/out
        env = math.sin(math.pi * t)                    # 0 at both ends: start/end exactly on target
        off = s_amp * math.sin(2 * math.pi * t) + bow * env
        off += env * sum(a * math.sin(f * math.pi * t + ph) for a, f, ph in waves)
        tremor = (1.0 - raw ** 3) * 0.6
        path.append((int(round(x0 + dx * t + nx * off + random.gauss(0, tremor))),
                     int(round(y0 + dy * t + ny * off + random.gauss(0, tremor)))))
    path[-1] = (x1, y1)
    return path


def generate_human_path(start: Tuple[int, int], end: Tuple[int, int],
                        deviation_factor: float = 0.25,
                        steps: int = 0) -> List[Tuple[int, int]]:
    """
    Human-like mouse path from start to end. deviation_factor (0..1) is the path irregularity:
    0 = straight line; higher = S-shaped, wobbly route, and on long moves sometimes a small
    overshoot past the target followed by a short correction.
    """
    x0, y0 = start
    x3, y3 = end
    dx, dy = x3 - x0, y3 - y0
    dist = math.hypot(dx, dy)
    if dist < 4:
        return [end]
    if steps <= 0:
        steps = max(20, int(dist / random.uniform(8.0, 14.0)))
    if deviation_factor <= 0:
        return [(int(round(x0 + dx * i / steps)), int(round(y0 + dy * i / steps))) for i in range(1, steps + 1)]
    irregularity = min(1.0, deviation_factor)
    if dist > 150 and random.random() < irregularity * 0.5:
        over = dist * random.uniform(0.02, 0.06)
        ox = int(round(x3 + dx / dist * over + random.uniform(-over, over) * 0.5))
        oy = int(round(y3 + dy / dist * over + random.uniform(-over, over) * 0.5))
        main = _wavy_path(x0, y0, ox, oy, irregularity, steps)
        fix = max(4, int(math.hypot(x3 - ox, y3 - oy) / 3))
        return main + _wavy_path(ox, oy, x3, y3, irregularity * 0.3, fix) if (ox, oy) != (x3, y3) else main
    return _wavy_path(x0, y0, x3, y3, irregularity, steps)

class Humanizer:
    def __init__(self):
        self.mouse = MouseController()
        self.keyboard = KeyboardController()
        
    def add_jitter(self, x: int, y: int, radius_px: int = 3) -> Tuple[int, int]:
        """Adds a subtle random offset within radius_px so target is never identical."""
        if radius_px <= 0:
            return x, y
        angle = random.uniform(0, 2 * math.pi)
        r = random.uniform(0, radius_px)
        return int(x + r * math.cos(angle)), int(y + r * math.sin(angle))
        
    def smooth_move(self, target_x: int, target_y: int,
                    speed_factor: float = 1.0,
                    deviation: float = 0.25,
                    stop_flag_callback=None) -> bool:
        """
        Moves the mouse to (target_x, target_y) with realistic human curvature and speed.
        Returns False if cancelled by stop_flag_callback.
        """
        start = get_real_cursor_pos()
        if start == (target_x, target_y):
            return True
            
        path = generate_human_path(start, (target_x, target_y), deviation_factor=deviation)
        
        total_steps = len(path)
        base_interval = (0.007 / max(0.2, speed_factor))
        
        for i, pt in enumerate(path):
            if stop_flag_callback and stop_flag_callback():
                return False
                
            set_real_cursor_pos(pt[0], pt[1])
            
            # Non-linear sleep to mimic muscle inertia
            progress = (i + 1) / total_steps
            speed_mod = 1.0 + 0.5 * math.sin(progress * math.pi)
            sleep_time = (base_interval / speed_mod) * random.uniform(0.85, 1.15)
            time.sleep(sleep_time)
            
        return True
        
    def click(self, button_name: str = "left", double: bool = False,
              double_click_interval_ms: int = 120,
              down_up_delay_range: Tuple[int, int] = (45, 110),
              stop_flag_callback=None, hold_ms: int = 0) -> bool:
        """
        Simulates a human mouse click with realistic down-up hold delay.
        """
        if stop_flag_callback and stop_flag_callback():
            return False
            
        btn_map = {
            "left": Button.left,
            "right": Button.right,
            "middle": Button.middle
        }
        btn = btn_map.get(button_name.lower(), Button.left)
        
        clicks = 2 if double else 1
        for c in range(clicks):
            if stop_flag_callback and stop_flag_callback():
                return False
                
            self.mouse.press(btn)
            try:
                if hold_ms:  # long press: keep it down, but stay stoppable
                    self.random_sleep(hold_ms, hold_ms, stop_flag_callback)
                else:
                    time.sleep(random.uniform(down_up_delay_range[0], down_up_delay_range[1]) / 1000.0)
            finally:
                self.mouse.release(btn)
            
            if double and c == 0:
                if stop_flag_callback and stop_flag_callback():
                    return False
                between_clicks = max(0, double_click_interval_ms) / 1000.0
                time.sleep(between_clicks)
                
        return True

    def type_text(self, text: str,
                  min_delay_ms: int = 50,
                  max_delay_ms: int = 150,
                  stop_flag_callback=None) -> bool:
        """
        Simulates human typing with variable inter-keystroke intervals
        and occasional human pauses (e.g. after spaces or punctuation).
        """
        for i, char in enumerate(text):
            if stop_flag_callback and stop_flag_callback():
                return False
                
            self.keyboard.type(char)
            
            delay = random.uniform(min_delay_ms, max_delay_ms) / 1000.0
            if char in " .!?,;\n":
                delay += random.uniform(60, 200) / 1000.0
            elif random.random() < 0.05:
                delay += random.uniform(100, 250) / 1000.0
                
            time.sleep(delay)
            
        return True

    SPECIAL_KEYS = {
        "Space": Key.space, "Enter": Key.enter, "Tab": Key.tab,
        "Escape": Key.esc, "Backspace": Key.backspace, "Delete": Key.delete,
        "Arrow Up": Key.up, "Arrow Down": Key.down,
        "Arrow Left": Key.left, "Arrow Right": Key.right,
        "Home": Key.home, "End": Key.end, "Page Up": Key.page_up, "Page Down": Key.page_down,
        "Insert": Key.insert, "Shift": Key.shift, "Ctrl": Key.ctrl, "Alt": Key.alt, "Win": Key.cmd,
    }

    def press_key(self, key_name: str, hold_ms: int = 0, stop_flag_callback=None, modifiers=()) -> bool:
        key = self.SPECIAL_KEYS.get(key_name, getattr(Key, key_name.lower(), None))
        if key is None:
            key = key_name.lower() if len(key_name) == 1 else None
        if key is None:
            return False
        if stop_flag_callback and stop_flag_callback():
            return False
        mods = [self.SPECIAL_KEYS[m] for m in modifiers if m in self.SPECIAL_KEYS]  # e.g. Ctrl + C
        for m in mods:
            self.keyboard.press(m)
        self.keyboard.press(key)
        try:
            if hold_ms:
                return self.random_sleep(hold_ms, hold_ms, stop_flag_callback)
            return True
        finally:
            self.keyboard.release(key)
            for m in reversed(mods):
                self.keyboard.release(m)

    def drag(self, to_x: int, to_y: int, button_name: str = "left", duration_ms: int = 600,
             deviation: float = 0.25, stop_flag_callback=None) -> bool:
        """Press at the current cursor position, glide to (to_x, to_y) in about duration_ms, release."""
        btn = {"left": Button.left, "right": Button.right, "middle": Button.middle}.get(button_name, Button.left)
        path = generate_human_path(get_real_cursor_pos(), (to_x, to_y), deviation_factor=deviation * 0.5)
        self.mouse.press(btn)
        try:
            time.sleep(random.uniform(0.10, 0.16))  # apps (Explorer) need a moment before the move counts as a drag
            pause = duration_ms / 1000.0 / max(1, len(path))
            for x, y in path:
                if stop_flag_callback and stop_flag_callback():
                    return False
                set_real_cursor_pos(x, y)
                time.sleep(pause * random.uniform(0.8, 1.2))
            time.sleep(random.uniform(0.06, 0.12))  # settle on the drop target before letting go
            return True
        finally:
            self.mouse.release(btn)

    def scroll(self, amount: int, stop_flag_callback=None) -> bool:
        """Mouse wheel, one notch at a time with small human pauses (positive = up)."""
        step = 1 if amount > 0 else -1
        for _ in range(abs(amount)):
            if stop_flag_callback and stop_flag_callback():
                return False
            self.mouse.scroll(0, step)
            time.sleep(random.uniform(0.03, 0.08))
        return True

    def random_sleep(self, min_ms: int, max_ms: int, stop_flag_callback=None) -> bool:
        """
        Sleeps for a random duration between min_ms and max_ms in small slices
        so that cancellation via stop_flag_callback is responsive.
        """
        if max_ms < min_ms:
            min_ms, max_ms = max_ms, min_ms
            
        target_sec = random.uniform(min_ms, max_ms) / 1000.0
        start_time = time.time()
        
        while time.time() - start_time < target_sec:
            if stop_flag_callback and stop_flag_callback():
                return False
            time.sleep(0.01)
            
        return True
