"""
Automate - Execution Worker
Background thread handling action pipelines, loops, global random delays,
and real-time status reporting. Plain Python (no Qt) so the app bundle stays small.
"""

import time
import random
import threading
from typing import List

from .actions import Action, ClickAction, MoveAction, TypeAction, DelayAction, KeyAction, ScrollAction, DragAction
from .humanizer import Humanizer
from .background import BackgroundInput

class Signal:
    """Minimal stand-in for Qt's Signal. Callbacks run on the worker thread."""
    def __init__(self):
        self._slots = []

    def connect(self, slot, *_):
        self._slots.append(slot)

    def emit(self, *args):
        for slot in self._slots:
            slot(*args)


class ExecutionWorker(threading.Thread):

    def __init__(self, actions: List[Action],
                 global_delay_min: int = 200,
                 global_delay_max: int = 500,
                 repeat_mode: str = "count",   # 'count' or 'infinite'
                 repeat_count: int = 1,
                 speed_factor: float = 1.0,
                 deviation: float = 0.25,
                 jitter_radius: int = 3,
                 global_delay_enabled: bool = True,
                 movement_enabled: bool = True,
                 background_hwnd: int = None,
                 time_limit_s: float = 0,
                 parent=None):
        super().__init__(daemon=True)
        self.step_started = Signal()        # (index, action_id)
        self.step_completed = Signal()      # (index, action_id)
        self.cycle_completed = Signal()     # (current_cycle, total_target)
        self.status_changed = Signal()      # descriptive text
        self.execution_finished = Signal()  # True if completed normally, False if stopped
        self.actions = actions
        self.global_delay_min = global_delay_min
        self.global_delay_max = global_delay_max
        self.repeat_mode = repeat_mode
        self.repeat_count = repeat_count
        self.speed_factor = speed_factor
        self.deviation = deviation
        self.jitter_radius = jitter_radius
        self.global_delay_enabled = global_delay_enabled
        self.movement_enabled = movement_enabled
        
        self.humanizer = Humanizer()
        # Background mode: input goes to this window via PostMessage, the real mouse/keyboard stay free
        self.background = BackgroundInput(background_hwnd) if background_hwnd else None
        self._is_stopped = False
        self.time_limit_s = time_limit_s  # 0 = no limit
        self._deadline = None
        self._timed_out = False

    def stop(self):
        self._is_stopped = True

    def isRunning(self) -> bool:
        return self.is_alive()

    def wait(self, ms: int = None):
        self.join(None if ms is None else ms / 1000)

    def is_stop_requested(self) -> bool:
        if self._deadline and not self._is_stopped and time.time() >= self._deadline:
            self._timed_out = self._is_stopped = True
        return self._is_stopped

    def run(self):
        self._is_stopped = False
        self._deadline = time.time() + self.time_limit_s if self.time_limit_s else None
        current_cycle = 0
        total_cycles = self.repeat_count if self.repeat_mode == "count" else 0
        
        self.status_changed.emit("Status: Running")
        
        try:
            while not self._is_stopped:
                current_cycle += 1
                self.status_changed.emit(f"Cycle {current_cycle}" + (f" / {total_cycles}" if total_cycles > 0 else " (unlimited)"))
                
                # Execute each enabled action in sequence
                for idx, action in enumerate(self.actions):
                    if self._is_stopped:
                        break
                    if not action.enabled:
                        continue
                    if action.chance < 100 and random.uniform(0, 100) >= action.chance:
                        continue  # randomly skipped this time: makes each cycle a little different
                        
                    self.step_started.emit(idx, action.id)
                    success = self._execute_single_action(action)
                    if not success or self._is_stopped:
                        break
                    self.step_completed.emit(idx, action.id)
                    
                    # Inter-step global random delay (if not the last step or if repeating)
                    if not self._is_stopped and self.global_delay_enabled and (self.global_delay_min > 0 or self.global_delay_max > 0):
                        inter_delay = random.uniform(self.global_delay_min, self.global_delay_max)
                        if inter_delay > 0:
                            self.humanizer.random_sleep(self.global_delay_min, self.global_delay_max,
                                                       stop_flag_callback=self.is_stop_requested)
                
                if self._is_stopped:
                    break
                    
                self.cycle_completed.emit(current_cycle, total_cycles)
                
                # Check cycle completion
                if self.repeat_mode == "count" and current_cycle >= total_cycles:
                    break
                    
                # Short pause between full cycles if continuing
                if not self._is_stopped and self.global_delay_enabled and (self.global_delay_min > 0 or self.global_delay_max > 0):
                    self.humanizer.random_sleep(self.global_delay_min, self.global_delay_max,
                                               stop_flag_callback=self.is_stop_requested)
                    
        except Exception as e:
            self.status_changed.emit(f"Error: {str(e)}")
            self.execution_finished.emit(False)
            return

        if self._timed_out:  # time limit reached counts as a normal finish
            self.status_changed.emit("Status: Time limit reached")
            self.execution_finished.emit(True)
            return
        normally = not self._is_stopped
        if normally:
            self.status_changed.emit("Status: Complete")
        else:
            self.status_changed.emit("Status: Stopped")
            
        self.execution_finished.emit(normally)

    def _execute_background(self, action: Action) -> bool:
        bg, stop = self.background, self.is_stop_requested
        if isinstance(action, ScrollAction):
            x, y = bg.to_screen(*action.rel) if action.rel else (action.x, action.y)
            return bg.scroll(x, y, action.amount, stop)
        if isinstance(action, DragAction):
            x, y = bg.to_screen(*action.rel) if action.rel else (action.x, action.y)
            tx, ty = bg.to_screen(*action.rel_to) if action.rel_to else (action.to_x, action.to_y)
            return bg.drag(x, y, tx, ty, action.button, action.duration_ms, stop)
        if isinstance(action, (ClickAction, MoveAction)):
            bx, by = bg.to_screen(*action.rel) if action.rel else (action.x, action.y)
            x, y = self.humanizer.add_jitter(bx, by, max(action.jitter_radius, self.jitter_radius))
            if isinstance(action, MoveAction):
                return bg.move(x, y)
            for i in range(max(1, action.times)):
                if not bg.click(x, y, action.button, action.double, action.double_click_interval_ms, stop, action.hold_ms):
                    return False
                if i + 1 < max(1, action.times) and not self.humanizer.random_sleep(
                        action.click_interval_ms, action.click_interval_ms, stop):
                    return False
            return True
        if isinstance(action, TypeAction):
            return bg.type_text(action.text, action.min_delay_ms, action.max_delay_ms, stop)
        if isinstance(action, KeyAction):
            return bg.press_key(action.key, action.hold_ms if action.mode == "hold" else 0, stop, action.modifiers)
        if isinstance(action, DelayAction):
            return self.humanizer.random_sleep(action.min_ms, action.max_ms, stop)
        return True

    def _execute_single_action(self, action: Action) -> bool:
        if self.background:
            return self._execute_background(action)
        if isinstance(action, ClickAction):
            # Calculate target point with random human jitter
            jitter = max(action.jitter_radius, self.jitter_radius)
            target_x, target_y = self.humanizer.add_jitter(action.x, action.y, jitter)
            
            if self.movement_enabled and action.smooth_move:
                ok = self.humanizer.smooth_move(
                    target_x, target_y,
                    speed_factor=self.speed_factor,
                    deviation=self.deviation,
                    stop_flag_callback=self.is_stop_requested
                )
                if not ok:
                    return False
            else:
                from .humanizer import set_real_cursor_pos
                set_real_cursor_pos(target_x, target_y)
                
            for click_index in range(max(1, action.times)):
                if not self.humanizer.click(button_name=action.button,
                        double=action.double,
                        double_click_interval_ms=action.double_click_interval_ms,
                        stop_flag_callback=self.is_stop_requested,
                        hold_ms=action.hold_ms):
                    return False
                if click_index + 1 < max(1, action.times) and not self.humanizer.random_sleep(
                        action.click_interval_ms, action.click_interval_ms, self.is_stop_requested):
                    return False
            return True

        elif isinstance(action, MoveAction):
            jitter = max(action.jitter_radius, self.jitter_radius)
            target_x, target_y = self.humanizer.add_jitter(action.x, action.y, jitter)
            
            if self.movement_enabled and action.smooth_move:
                return self.humanizer.smooth_move(
                    target_x, target_y,
                    speed_factor=self.speed_factor,
                    deviation=self.deviation,
                    stop_flag_callback=self.is_stop_requested
                )
            else:
                from .humanizer import set_real_cursor_pos
                set_real_cursor_pos(target_x, target_y)
                return True

        elif isinstance(action, TypeAction):
            return self.humanizer.type_text(
                text=action.text,
                min_delay_ms=action.min_delay_ms,
                max_delay_ms=action.max_delay_ms,
                stop_flag_callback=self.is_stop_requested
            )

        elif isinstance(action, DelayAction):
            return self.humanizer.random_sleep(
                min_ms=action.min_ms,
                max_ms=action.max_ms,
                stop_flag_callback=self.is_stop_requested
            )

        elif isinstance(action, KeyAction):
            return self.humanizer.press_key(action.key,
                action.hold_ms if action.mode == "hold" else 0,
                self.is_stop_requested, action.modifiers)

        elif isinstance(action, DragAction):
            start = self.humanizer.add_jitter(action.x, action.y, self.jitter_radius)
            if self.movement_enabled:
                if not self.humanizer.smooth_move(*start, speed_factor=self.speed_factor,
                                                  deviation=self.deviation, stop_flag_callback=self.is_stop_requested):
                    return False
            else:
                from .humanizer import set_real_cursor_pos
                set_real_cursor_pos(*start)
            return self.humanizer.drag(action.to_x, action.to_y, action.button, action.duration_ms,
                                       self.deviation if self.movement_enabled else 0, self.is_stop_requested)

        elif isinstance(action, ScrollAction):
            target = self.humanizer.add_jitter(action.x, action.y, self.jitter_radius)
            if self.movement_enabled:
                if not self.humanizer.smooth_move(*target, speed_factor=self.speed_factor,
                                                  deviation=self.deviation, stop_flag_callback=self.is_stop_requested):
                    return False
            else:
                from .humanizer import set_real_cursor_pos
                set_real_cursor_pos(*target)
            return self.humanizer.scroll(action.amount, self.is_stop_requested)

        return True
