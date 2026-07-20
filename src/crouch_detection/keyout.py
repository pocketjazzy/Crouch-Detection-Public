"""Key/mouse output: hold or release one configured control.

Windows: SendInput with hardware scan codes (KEYEVENTF_SCANCODE) so
DirectInput-era apps like MAME see the press exactly like a real key
(MAME still needs -keyboardprovider dinput). Mouse buttons go out as
mouse events.

Linux: a virtual input device created through /dev/uinput, implemented
with the standard library only (SteamOS has no compiler for C-extension
packages). Kernel-level events are indistinguishable from real hardware,
so games and MAME need no special flags. Needs access to /dev/uinput -
see the README's Linux section if permission is denied.
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
    # Pure-stdlib uinput/evdev: SteamOS has no compiler, so packages with
    # C extensions (python-evdev) can't install there. The kernel protocol
    # is just device files + a few ioctls; os/struct/fcntl cover it.
    import fcntl
    import glob
    import os
    import struct

    EV_SYN, EV_KEY = 0x00, 0x01
    SYN_REPORT = 0
    UI_SET_EVBIT = 0x40045564
    UI_SET_KEYBIT = 0x40045565
    UI_DEV_SETUP = 0x405C5503
    UI_DEV_CREATE = 0x5501
    UI_DEV_DESTROY = 0x5502
    BUS_USB = 0x03

    # Linux input-event-codes.h values.
    KEY_CODES = {
        "Left_Alt": 56, "Left_Ctrl": 29, "Left_Shift": 42, "Space": 57,
        "Z": 44, "X": 45,
        "Mouse_Left": 272, "Mouse_Right": 273, "Mouse_Middle": 274,
    }
    _F_KEY_CODES = {1: 59, 2: 60, 3: 61, 4: 62, 5: 63, 6: 64, 7: 65,
                    8: 66, 9: 67, 10: 68, 11: 87, 12: 88}

    # struct input_event: struct timeval (2 native longs) + u16 type +
    # u16 code + s32 value. Native 'l' matches the kernel's long size.
    _EVENT_FMT = "llHHi"
    _EVENT_SIZE = struct.calcsize(_EVENT_FMT)

    class Output:
        """Holds/releases one named control via a uinput virtual device.
        Kernel-level events look exactly like real hardware."""

        def __init__(self, name: str) -> None:
            self.name = name
            self.down = False
            self._code = KEY_CODES.get(name)
            self._fd = None
            self.supported = False
            if self._code is None:
                print(f"WARNING: output '{name}' not recognized - "
                      f"key output disabled")
                return
            try:
                fd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK)
            except OSError as exc:
                print(f"WARNING: cannot open /dev/uinput ({exc}) - key "
                      f"output disabled. See the README's Linux section.")
                return
            try:
                fcntl.ioctl(fd, UI_SET_EVBIT, EV_KEY)
                fcntl.ioctl(fd, UI_SET_KEYBIT, self._code)
                # struct uinput_setup: input_id (4x u16), name[80], u32.
                fcntl.ioctl(fd, UI_DEV_SETUP, struct.pack(
                    "=HHHH80sI", BUS_USB, 0x0001, 0x0001, 1,
                    b"Crouch-Detection", 0))
                fcntl.ioctl(fd, UI_DEV_CREATE)
            except OSError as exc:
                os.close(fd)
                print(f"WARNING: cannot create the virtual input device "
                      f"({exc}) - key output disabled. See the README's "
                      f"Linux section.")
                return
            self._fd = fd
            self.supported = True

        def _emit(self, etype: int, code: int, value: int) -> None:
            os.write(self._fd,
                     struct.pack(_EVENT_FMT, 0, 0, etype, code, value))

        def set(self, down: bool) -> None:
            if not self.supported or down == self.down:
                return
            self._emit(EV_KEY, self._code, 1 if down else 0)
            self._emit(EV_SYN, SYN_REPORT, 0)
            self.down = down

        def release(self) -> None:
            self.set(False)

        def close(self) -> None:
            self.release()
            if self._fd is not None:
                try:
                    fcntl.ioctl(self._fd, UI_DEV_DESTROY)
                except OSError:
                    pass
                os.close(self._fd)
                self._fd = None
                self.supported = False

    class GlobalHotkey:
        """Watches /dev/input/event* for the hotkey (needs read access,
        i.e. membership in the 'input' group). When unavailable, the
        viewer falls back to the hotkey working while its window is
        focused."""

        def __init__(self, vk: int) -> None:
            self._vk = vk
            self._fds = []
            for path in sorted(glob.glob("/dev/input/event*")):
                try:
                    self._fds.append(
                        os.open(path, os.O_RDONLY | os.O_NONBLOCK))
                except OSError:
                    continue
            self.available = bool(self._fds)
            if not self.available:
                print("NOTE: global arm hotkey unavailable (no readable "
                      "input devices - see the README's Linux section). "
                      "The hotkey still works while the viewer window is "
                      "focused.")

        def poll(self) -> bool:
            fired = False
            for fd in self._fds:
                while True:
                    try:
                        data = os.read(fd, _EVENT_SIZE * 64)
                    except (BlockingIOError, InterruptedError):
                        break
                    except OSError:
                        break
                    if not data:
                        break
                    for off in range(0, len(data) - _EVENT_SIZE + 1,
                                     _EVENT_SIZE):
                        _s, _u, etype, code, value = struct.unpack_from(
                            _EVENT_FMT, data, off)
                        if (etype == EV_KEY and code == self._vk
                                and value == 1):
                            fired = True
            return fired

    def hotkey_vk(name: str) -> int:
        """'f1'..'f12' -> Linux key code; unrecognized falls back to F8."""
        name = name.lower().strip()
        if name.startswith("f") and name[1:].isdigit():
            code = _F_KEY_CODES.get(int(name[1:]))
            if code is not None:
                return code
        return _F_KEY_CODES[8]

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
