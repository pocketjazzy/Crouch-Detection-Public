"""Key/mouse output: hold or release one configured control.

Windows: SendInput with hardware scan codes (KEYEVENTF_SCANCODE) so
DirectInput-era apps like MAME see the press exactly like a real key;
mouse buttons go out as mouse events. If MAME still ignores injected
input under its default rawinput provider, launch it with
-keyboardprovider win32. The Linux/uinput backend is milestone M6.
"""

import sys

# DirectInput (scan code set 1) make codes.
SCAN_CODES = {
    "Left_Alt": 0x38,
    "Left_Ctrl": 0x1D,
    "Left_Shift": 0x2A,
    "Space": 0x39,
    "Z": 0x2C,
    "X": 0x2D,
}
MOUSE_FLAGS = {  # (down flag, up flag)
    "Mouse_Left": (0x0002, 0x0004),
    "Mouse_Right": (0x0008, 0x0010),
    "Mouse_Middle": (0x0020, 0x0040),
}

_IS_WINDOWS = sys.platform == "win32"

if _IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    INPUT_MOUSE = 0
    INPUT_KEYBOARD = 1
    KEYEVENTF_KEYUP = 0x0002
    KEYEVENTF_SCANCODE = 0x0008

    class _KEYBDINPUT(ctypes.Structure):
        _fields_ = (("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                    ("dwExtraInfo", ctypes.c_size_t))

    class _MOUSEINPUT(ctypes.Structure):
        _fields_ = (("dx", wintypes.LONG), ("dy", wintypes.LONG),
                    ("mouseData", wintypes.DWORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                    ("dwExtraInfo", ctypes.c_size_t))

    class _INPUT_UNION(ctypes.Union):
        _fields_ = (("ki", _KEYBDINPUT), ("mi", _MOUSEINPUT))

    class _INPUT(ctypes.Structure):
        _anonymous_ = ("u",)
        _fields_ = (("type", wintypes.DWORD), ("u", _INPUT_UNION))

    _user32 = ctypes.WinDLL("user32", use_last_error=True)

    def _send_key(scan: int, down: bool) -> None:
        inp = _INPUT(type=INPUT_KEYBOARD)
        inp.ki = _KEYBDINPUT(
            0, scan, KEYEVENTF_SCANCODE | (0 if down else KEYEVENTF_KEYUP),
            0, 0)
        _user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))

    def _send_mouse(flag: int) -> None:
        inp = _INPUT(type=INPUT_MOUSE)
        inp.mi = _MOUSEINPUT(0, 0, 0, flag, 0, 0)
        _user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))

    class GlobalHotkey:
        """Edge-detects a key system-wide - works while MAME has focus."""

        def __init__(self, vk: int) -> None:
            self._vk = vk
            self._was_down = False

        def poll(self) -> bool:
            down = bool(_user32.GetAsyncKeyState(self._vk) & 0x8000)
            fired = down and not self._was_down
            self._was_down = down
            return fired
else:
    class GlobalHotkey:  # Linux backend lands in M6
        def __init__(self, vk: int) -> None:
            pass

        def poll(self) -> bool:
            return False


class Output:
    """Holds/releases one named control; idempotent, safe to spam set()."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.down = False
        self._scan = SCAN_CODES.get(name)
        self._mouse = MOUSE_FLAGS.get(name)
        self.supported = (_IS_WINDOWS
                          and (self._scan or self._mouse) is not None)
        if not self.supported:
            print(f"WARNING: output '{name}' not supported on this "
                  f"platform - key output disabled")

    def set(self, down: bool) -> None:
        if not self.supported or down == self.down:
            return
        if self._scan is not None:
            _send_key(self._scan, down)
        else:
            _send_mouse(self._mouse[0] if down else self._mouse[1])
        self.down = down

    def release(self) -> None:
        self.set(False)


def hotkey_vk(name: str) -> int:
    """'f1'..'f12' -> VK code; anything unrecognized falls back to F8."""
    name = name.lower().strip()
    if name.startswith("f") and name[1:].isdigit():
        n = int(name[1:])
        if 1 <= n <= 12:
            return 0x6F + n
    return 0x77
