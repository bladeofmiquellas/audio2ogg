import tkinter as tk

_TIP_BG = "#ffffff"
_TIP_FG = "#333333"
_TIP_BORDER = "#d4d4d4"


def set_tooltip_theme(*, bg: str, fg: str, border: str) -> None:
    global _TIP_BG, _TIP_FG, _TIP_BORDER
    _TIP_BG = bg
    _TIP_FG = fg
    _TIP_BORDER = border


def _build_tip_content(parent: tk.Misc, text: str) -> None:
    border = tk.Frame(parent, background=_TIP_BORDER, padx=1, pady=1)
    tk.Label(
        border,
        text=text,
        justify=tk.LEFT,
        background=_TIP_BG,
        foreground=_TIP_FG,
        font=("", 9),
        padx=8,
        pady=6,
        wraplength=300,
    ).pack()
    border.pack()


def _place_tip_window(tw: tk.Toplevel, anchor: tk.Misc) -> None:
    tw.update_idletasks()
    x = anchor.winfo_rootx() + 12
    y = anchor.winfo_rooty() + anchor.winfo_height() + 4

    screen_w = tw.winfo_screenwidth()
    tip_w = tw.winfo_width()
    if x + tip_w > screen_w - 8:
        x = max(8, screen_w - tip_w - 8)

    tw.geometry(f"+{x}+{y}")


class ToolTip:
    def __init__(self, widget: tk.Misc, delay_ms: int = 500) -> None:
        self.widget = widget
        self.delay_ms = delay_ms
        self.text = ""
        self.tip_window: tk.Toplevel | None = None
        self._after_id: str | None = None
        widget.bind("<Enter>", self._schedule_show, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def set_text(self, text: str) -> None:
        self.text = text
        self._hide()

    def _schedule_show(self, _event: tk.Event | None = None) -> None:
        self._cancel_schedule()
        if self.text:
            self._after_id = self.widget.after(self.delay_ms, self._show)

    def _cancel_schedule(self) -> None:
        if self._after_id is not None:
            self.widget.after_cancel(self._after_id)
            self._after_id = None

    def _show(self) -> None:
        self._after_id = None
        if not self.text or self.tip_window is not None:
            return

        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.attributes("-topmost", True)
        _build_tip_content(tw, self.text)
        _place_tip_window(tw, self.widget)

    def _hide(self, _event: tk.Event | None = None) -> None:
        self._cancel_schedule()
        if self.tip_window is not None:
            self.tip_window.destroy()
            self.tip_window = None
