"""
Automate - Action Models
Defines the card-based step models and serialization.
"""

import uuid
from enum import Enum
from typing import Dict, Any

class ActionType(str, Enum):
    CLICK = "CLICK"
    MOVE = "MOVE"
    TYPE = "TYPE"
    DELAY = "DELAY"
    KEY = "KEY"
    SCROLL = "SCROLL"
    DRAG = "DRAG"

class Action:
    def __init__(self, action_type: ActionType, action_id: str = None):
        self.id = action_id or str(uuid.uuid4())
        self.type = action_type
        self.enabled = True
        self.rel = None  # background mode: (x, y) relative to the target window's top-left
        self.chance = 100  # % chance to run each time it comes up (random step skipping)

    def to_dict(self) -> Dict[str, Any]:
        raise NotImplementedError

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "Action":
        atype = data.get("type")
        if atype == ActionType.CLICK:
            return ClickAction(
                x=data.get("x", 0),
                y=data.get("y", 0),
                button=data.get("button", "left"),
                double=data.get("double", False),
                double_click_interval_ms=data.get("double_click_interval_ms", 120),
                times=data.get("times", 1),
                click_interval_ms=data.get("click_interval_ms", 100),
                smooth_move=data.get("smooth_move", True),
                jitter_radius=data.get("jitter_radius", 3),
                action_id=data.get("id")
            )
        elif atype == ActionType.MOVE:
            return MoveAction(
                x=data.get("x", 0),
                y=data.get("y", 0),
                smooth_move=data.get("smooth_move", True),
                jitter_radius=data.get("jitter_radius", 3),
                action_id=data.get("id")
            )
        elif atype == ActionType.TYPE:
            return TypeAction(
                text=data.get("text", ""),
                min_delay_ms=data.get("min_delay_ms", 60),
                max_delay_ms=data.get("max_delay_ms", 140),
                action_id=data.get("id")
            )
        elif atype == ActionType.DELAY:
            return DelayAction(
                min_ms=data.get("min_ms", 1000),
                max_ms=data.get("max_ms", 2500),
                action_id=data.get("id")
            )
        elif atype == ActionType.KEY:
            return KeyAction(
                key=data.get("key", "Space"), mode=data.get("mode", "press"),
                hold_ms=data.get("hold_ms", 0), action_id=data.get("id")
            )
        raise ValueError(f"Unknown action type: {atype}")

class ClickAction(Action):
    def __init__(self, x: int = 0, y: int = 0, button: str = "left",
                 double: bool = False, double_click_interval_ms: int = 120, smooth_move: bool = True,
                 jitter_radius: int = 3, times: int = 1, click_interval_ms: int = 100,
                 action_id: str = None, hold_ms: int = 0):
        super().__init__(ActionType.CLICK, action_id)
        self.hold_ms = max(0, int(hold_ms))  # keep the button down this long (0 = normal quick click)
        self.x = int(x)
        self.y = int(y)
        self.button = button  # 'left', 'right', 'middle'
        self.double = bool(double)
        self.double_click_interval_ms = int(double_click_interval_ms)
        self.smooth_move = bool(smooth_move)
        self.jitter_radius = int(jitter_radius)
        self.times = max(1, int(times))
        self.click_interval_ms = max(0, int(click_interval_ms))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "x": self.x,
            "y": self.y,
            "button": self.button,
            "double": self.double,
            "double_click_interval_ms": self.double_click_interval_ms,
            "times": self.times,
            "click_interval_ms": self.click_interval_ms,
            "smooth_move": self.smooth_move,
            "jitter_radius": self.jitter_radius
        }

class MoveAction(Action):
    def __init__(self, x: int = 0, y: int = 0, smooth_move: bool = True,
                 jitter_radius: int = 3, action_id: str = None):
        super().__init__(ActionType.MOVE, action_id)
        self.x = int(x)
        self.y = int(y)
        self.smooth_move = bool(smooth_move)
        self.jitter_radius = int(jitter_radius)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "x": self.x,
            "y": self.y,
            "smooth_move": self.smooth_move,
            "jitter_radius": self.jitter_radius
        }

class TypeAction(Action):
    def __init__(self, text: str = "", min_delay_ms: int = 60,
                 max_delay_ms: int = 140, action_id: str = None):
        super().__init__(ActionType.TYPE, action_id)
        self.text = str(text)
        self.min_delay_ms = int(min_delay_ms)
        self.max_delay_ms = int(max_delay_ms)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "text": self.text,
            "min_delay_ms": self.min_delay_ms,
            "max_delay_ms": self.max_delay_ms
        }

class DelayAction(Action):
    def __init__(self, min_ms: int = 1000, max_ms: int = 2500, action_id: str = None):
        super().__init__(ActionType.DELAY, action_id)
        self.min_ms = int(min_ms)
        self.max_ms = int(max_ms)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "min_ms": self.min_ms,
            "max_ms": self.max_ms
        }

class KeyAction(Action):
    def __init__(self, key: str = "Space", mode: str = "press", hold_ms: int = 0,
                 action_id: str = None, modifiers=()):
        super().__init__(ActionType.KEY, action_id)
        self.key = str(key)
        self.mode = mode if mode in ("press", "hold") else "press"
        self.hold_ms = max(0, int(hold_ms))
        self.modifiers = [m for m in modifiers if m in ("Ctrl", "Shift", "Alt", "Win")]  # held around the key

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "type": self.type.value, "key": self.key,
                "mode": self.mode, "hold_ms": self.hold_ms}



class ScrollAction(Action):
    """Mouse wheel at (x, y): amount in notches, positive = up."""
    def __init__(self, x: int = 0, y: int = 0, amount: int = -3, action_id: str = None):
        super().__init__(ActionType.SCROLL, action_id)
        self.x, self.y, self.amount = int(x), int(y), int(amount)

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "type": self.type.value, "x": self.x, "y": self.y, "amount": self.amount}


class DragAction(Action):
    """Press at (x, y), move to (to_x, to_y) over duration_ms, release (drag & drop, selecting, sliders)."""
    def __init__(self, x: int = 0, y: int = 0, to_x: int = 0, to_y: int = 0, button: str = "left",
                 duration_ms: int = 600, action_id: str = None):
        super().__init__(ActionType.DRAG, action_id)
        self.x, self.y, self.to_x, self.to_y = int(x), int(y), int(to_x), int(to_y)
        self.button = button
        self.duration_ms = max(100, int(duration_ms))
        self.rel_to = None  # background mode: end point relative to the target window

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "type": self.type.value, "x": self.x, "y": self.y, "to_x": self.to_x,
                "to_y": self.to_y, "button": self.button, "duration_ms": self.duration_ms}
