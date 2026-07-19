"""In-window settings menu: navigate with Up/Down, change with Left/Right
or Enter, close with M or Esc. The viewer supplies the items; every change
is expected to apply live and persist immediately.
"""

import cv2

# Windows + Linux waitKeyEx codes.
KEYS_UP = {2490368, 65362}
KEYS_DOWN = {2621440, 65364}
KEYS_LEFT = {2424832, 65361}
KEYS_RIGHT = {2555904, 65363}
KEY_ENTER = 13
KEY_ESC = 27

FONT = cv2.FONT_HERSHEY_SIMPLEX


class MenuItem:
    def __init__(self, label: str, get_value, change) -> None:
        self.label = label
        self.get_value = get_value   # () -> display string
        self.change = change         # (direction: +1 | -1) -> None


class SettingsMenu:
    def __init__(self, items) -> None:
        self.items = items
        self.open = False
        self.index = 0

    def handle_key(self, key: int) -> bool:
        """Feed a waitKeyEx code; returns True if the menu consumed it."""
        if not self.open or key == -1:
            return False
        if key in KEYS_UP:
            self.index = (self.index - 1) % len(self.items)
        elif key in KEYS_DOWN:
            self.index = (self.index + 1) % len(self.items)
        elif key in KEYS_LEFT:
            self.items[self.index].change(-1)
        elif key in KEYS_RIGHT or key == KEY_ENTER:
            self.items[self.index].change(+1)
        elif key == KEY_ESC or key == ord("m"):
            self.open = False
        return True   # swallow everything else while open

    def draw(self, frame) -> None:
        if not self.open:
            return
        x0, y0, width = 12, 60, 470
        row_h = 30
        height = row_h * len(self.items) + 76
        cv2.rectangle(frame, (x0, y0), (x0 + width, y0 + height),
                      (24, 24, 24), -1)
        cv2.rectangle(frame, (x0, y0), (x0 + width, y0 + height),
                      (180, 180, 180), 1)
        cv2.putText(frame, "SETTINGS", (x0 + 12, y0 + 26),
                    FONT, 0.7, (255, 255, 255), 2)
        for i, item in enumerate(self.items):
            y = y0 + 56 + i * row_h
            selected = i == self.index
            color = (0, 255, 255) if selected else (200, 200, 200)
            marker = ">" if selected else " "
            cv2.putText(frame, f"{marker} {item.label}", (x0 + 12, y),
                        FONT, 0.55, color, 2 if selected else 1)
            cv2.putText(frame, item.get_value(), (x0 + 250, y),
                        FONT, 0.55, color, 2 if selected else 1)
        cv2.putText(frame, "arrows: select/change   Enter: toggle   M/Esc: close",
                    (x0 + 12, y0 + height - 12), FONT, 0.45, (150, 150, 150), 1)
