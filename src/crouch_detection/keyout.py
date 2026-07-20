"""Key/mouse output: hold or release one configured control.

Windows: SendInput with hardware scan codes (KEYEVENTF_SCANCODE) so
DirectInput-era apps like MAME see the press exactly like a real key
(MAME still needs -keyboardprovider dinput). Mouse buttons go out as
mouse events.

Linux: a virtual input device created through uinput (python-evdev).
Kernel-level events are indistinguishable from real hardware, so games
and MAME need no special flags. Needs access to /dev/uinput - usually
automatic on the Steam Deck; see the README's Linux section otherwise.
"""

import sys

# DirectInput (scan code set 1) make codes - Windows.
SCAN_CODES = {
    "Left_Alt": 0x38,
    "Left_Ctrl": 0x1D,
    "Left_Shift": 0x2A,
    "Space": 0x39,
    "Z": 0x2C,
    "X": 0x2D,
}
MOUSE_FLAGS = {  # (down flag, up flag) - Windows.
    "Mouse_Left": (0x0002, 0x0004),
    "Mouse_Right": (0x0008, 0x0010),
    "Mouse_Middle": (0x0020, 0x0040),
}

if sys.platform == "win32":
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

    class Output:
        """Holds/releases one named control; idempotent."""

        def __init__(self, name: str) -> None:
            self.name = name
            self.down = False
            self._scan = SCAN_CODES.get(name)
            self._mouse = MOUSE_FLAGS.get(name)
            self.supported = (self._scan or self._mouse) is not None
            if not self.supported:
                print(f"WARNING: output '{name}' not recognized - "
                      f"key output disabled")

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

        def close(self) -> None:
            self.release()

    class GlobalHotkey:
        """Edge-detects a key system-wide - works while a game has focus."""

        available = True

        def __init__(self, vk: int) -> None:
            self._vk = vk
            self._was_down = False

        def poll(self) -> bool:
            down = bool(_user32.GetAsyncKeyState(self._vk) & 0x8000)
            fired = down and not self._was_down
            self._was_down = down
            return fired

    def hotkey_vk(name: str) -> int:
        """'f1'..'f12' -> Windows VK code; unrecognized falls back to F8."""
        name = name.lower().strip()
        if name.startswith("f") and name[1:].isdigit():
            n = int(name[1:])
            if 1 <= n <= 12:
                return 0x6F + n
        return 0x77

elif sys.platform.startswith("linux"):
    import os

    try:
        import evdev
        from evdev import ecodes as _ec
        _HAVE_EVDEV = True
    except ImportError:
        _HAVE_EVDEV = False

    def _key_code(name: str):
        if not _HAVE_EVDEV:
            return None
        return {
            "Left_Alt": _ec.KEY_LEFTALT,
            "Left_Ctrl": _ec.KEY_LEFTCTRL,
            "Left_Shift": _ec.KEY_LEFTSHIFT,
            "Space": _ec.KEY_SPACE,
            "Z": _ec.KEY_Z,
            "X": _ec.KEY_X,
            "Mouse_Left": _ec.BTN_LEFT,
            "Mouse_Right": _ec.BTN_RIGHT,
            "Mouse_Middle": _ec.BTN_MIDDLE,
        }.get(name)

    class Output:
        """Holds/releases one named control via a uinput virtual device."""

        def __init__(self, name: str) -> None:
            self.name = name
            self.down = False
            self._code = _key_code(name)
            self._ui = None
            self.supported = False
            if not _HAVE_EVDEV:
                print("WARNING: python-evdev not installed - key output "
                      "disabled (pip install -e . again to pick it up)")
            elif self._code is None:
                print(f"WARNING: output '{name}' not recognized - "
                      f"key output disabled")
            else:
                try:
                    self._ui = evdev.UInput({_ec.EV_KEY: [self._code]},
                                            name="Crouch-Detection")
                    self.supported = True
                except Exception as exc:
                    print(f"WARNING: cannot create the virtual input device "
                          f"({exc}) - key output disabled. See the README's "
                          f"Linux section (uinput access).")

        def set(self, down: bool) -> None:
            if not self.supported or down == self.down:
                return
            self._ui.write(_ec.EV_KEY, self._code, 1 if down else 0)
            self._ui.syn()
            self.down = down

        def release(self) -> None:
            self.set(False)

        def close(self) -> None:
            self.release()
            if self._ui is not None:
                self._ui.close()
                self._ui = None
                self.supported = False

    class GlobalHotkey:
        """Watches real keyboards via evdev (needs /dev/input read access,
        i.e. membership in the 'input' group). When unavailable, the viewer
        falls back to handling the hotkey while its window is focused."""

        def __init__(self, vk: int) -> None:
            self._vk = vk
            self._devices = []
            if _HAVE_EVDEV:
                for path in evdev.list_devices():
                    try:
                        dev = evdev.InputDevice(path)
                        if vk in (dev.capabilities().get(_ec.EV_KEY) or []):
                            os.set_blocking(dev.fd, False)
                            self._devices.append(dev)
                        else:
                            dev.close()
                    except OSError:
                        continue
            self.available = bool(self._devices)
            if not self.available:
                print("NOTE: global arm hotkey unavailable (no readable "
                      "keyboards - see the README's Linux section). The "
                      "hotkey still works while the viewer window is "
                      "focused.")

        def poll(self) -> bool:
            fired = False
            for dev in self._devices:
                try:
                    while True:
                        event = dev.read_one()
                        if event is None:
                            break
                        if (event.type == _ec.EV_KEY
                                and event.code == self._vk
                                and event.value == 1):
                            fired = True
                except OSError:
                    continue
            return fired

    def hotkey_vk(name: str) -> int:
        """'f1'..'f12' -> evdev key code; unrecognized falls back to F8."""
        name = name.lower().strip()
        if _HAVE_EVDEV:
            if name.startswith("f") and name[1:].isdigit():
                n = int(name[1:])
                if 1 <= n <= 12:
                    return getattr(_ec, f"KEY_F{n}")
            return _ec.KEY_F8
        return 0

else:
    class Output:
        def __init__(self, name: str) -> None:
            self.name = name
            self.down = False
            self.supported = False
            print(f"WARNING: key output not supported on {sys.platform}")

        def set(self, down: bool) -> None:
            pass

        def release(self) -> None:
            pass

        def close(self) -> None:
            pass

    class GlobalHotkey:
        available = False

        def __init__(self, vk: int) -> None:
            pass

        def poll(self) -> bool:
            return False

    def hotkey_vk(name: str) -> int:
        return 0
