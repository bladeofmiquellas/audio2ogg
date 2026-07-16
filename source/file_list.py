import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import ttk


class FileListPanel(tk.Frame):
    ROW_HEIGHT = 38
    BG_EVEN = "#ffffff"
    BG_ODD = "#f6f7f9"
    BG_SELECTED = "#e8f1ff"
    BG_PLAYING = "#dff5e8"
    FG_NAME = "#1f2937"
    FG_DURATION = "#6b7280"
    FG_PENDING = "#9ca3af"
    SEP_COLOR = "#e8ebf0"

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)
        self._paths: list[Path] = []
        self._durations: dict[Path, float] = {}
        self._selected: set[Path] = set()
        self._last_index: int | None = None
        self._row_frames: dict[Path, tk.Frame] = {}
        self._display_name = lambda path: path.name
        self._format_duration = lambda _seconds: ""
        self._pending_label = "..."
        self._playing_path: Path | None = None
        self._activate_handler: Callable[[Path], None] | None = None
        self._selection_handler: Callable[[], None] | None = None
        self._canvas_resize_after: str | None = None
        self._scrollregion_after: str | None = None
        self._pending_canvas_width = 0

        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0, background=self.BG_EVEN)
        self.scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, background=self.BG_EVEN)
        self._canvas_window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")

        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind("<Enter>", self._bind_mousewheel)
        self.canvas.bind("<Leave>", self._unbind_mousewheel)

    def configure_presenters(
        self,
        *,
        display_name: "callable[[Path], str]",
        format_duration: "callable[[float], str]",
        pending_label: str,
    ) -> None:
        self._display_name = display_name
        self._format_duration = format_duration
        self._pending_label = pending_label

    def apply_theme(
        self,
        *,
        bg_even: str,
        bg_odd: str,
        bg_selected: str,
        bg_playing: str,
        fg_name: str,
        fg_duration: str,
        fg_pending: str,
        sep_color: str,
    ) -> None:
        self.BG_EVEN = bg_even
        self.BG_ODD = bg_odd
        self.BG_SELECTED = bg_selected
        self.BG_PLAYING = bg_playing
        self.FG_NAME = fg_name
        self.FG_DURATION = fg_duration
        self.FG_PENDING = fg_pending
        self.SEP_COLOR = sep_color
        self.canvas.configure(background=self.BG_EVEN)
        self.inner.configure(background=self.BG_EVEN)
        if self._paths:
            self._rebuild_rows()
        else:
            self._update_row_styles()

    def set_activate_handler(self, handler: Callable[[Path], None] | None) -> None:
        self._activate_handler = handler

    def set_selection_handler(self, handler: Callable[[], None] | None) -> None:
        self._selection_handler = handler

    def set_playing_path(self, path: Path | None) -> None:
        self._playing_path = path.resolve() if path is not None else None
        self._update_row_styles()

    def set_items(
        self,
        paths: list[Path],
        durations: dict[Path, float],
        *,
        selected: set[Path] | None = None,
        probing: bool = False,
    ) -> None:
        self._paths = list(paths)
        self._durations = durations
        valid = {path.resolve() for path in self._paths}
        if selected is not None:
            self._selected = {path.resolve() for path in selected if path.resolve() in valid}
        else:
            self._selected = {resolved for resolved in self._selected if resolved in valid}
        self._probing = probing
        self._rebuild_rows()

    def get_selected_paths(self) -> list[Path]:
        selected_resolved = set(self._selected)
        return [path for path in self._paths if path.resolve() in selected_resolved]

    def select_all(self) -> None:
        self._selected = {path.resolve() for path in self._paths}
        self._update_row_styles()
        self._notify_selection_changed()

    def clear_selection(self) -> None:
        self._selected.clear()
        self._update_row_styles()
        self._notify_selection_changed()

    def _notify_selection_changed(self) -> None:
        if self._selection_handler is not None:
            self._selection_handler()

    def dnd_widget(self) -> tk.Misc:
        return self.canvas

    def _on_inner_configure(self, _event: tk.Event) -> None:
        if self._scrollregion_after is None:
            self._scrollregion_after = self.after(16, self._update_scrollregion)

    def _update_scrollregion(self) -> None:
        self._scrollregion_after = None
        bbox = self.canvas.bbox("all")
        if bbox:
            self.canvas.configure(scrollregion=bbox)

    def _on_canvas_configure(self, event: tk.Event) -> None:
        if event.width <= 1:
            return
        self._pending_canvas_width = event.width
        if self._canvas_resize_after is None:
            self._canvas_resize_after = self.after(16, self._apply_canvas_width)

    def _apply_canvas_width(self) -> None:
        self._canvas_resize_after = None
        self.canvas.itemconfigure(self._canvas_window, width=self._pending_canvas_width)

    def _bind_mousewheel(self, _event: tk.Event) -> None:
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _unbind_mousewheel(self, _event: tk.Event) -> None:
        self.canvas.unbind_all("<MouseWheel>")

    def _on_mousewheel(self, event: tk.Event) -> None:
        self.canvas.yview_scroll(int(-event.delta / 120), "units")

    def _resolved(self, path: Path) -> Path:
        return path.resolve()

    def _duration_text(self, path: Path) -> str:
        duration = self._durations.get(self._resolved(path))
        if duration is not None:
            return self._format_duration(duration)
        if getattr(self, "_probing", False):
            return self._pending_label
        return ""

    def _row_background(self, index: int, path: Path) -> str:
        resolved = self._resolved(path)
        if self._playing_path is not None and resolved == self._playing_path:
            return self.BG_PLAYING
        if resolved in self._selected:
            return self.BG_SELECTED
        return self.BG_ODD if index % 2 else self.BG_EVEN

    def _rebuild_rows(self) -> None:
        for child in self.inner.winfo_children():
            child.destroy()
        self._row_frames.clear()

        for index, path in enumerate(self._paths):
            row_bg = self._row_background(index, path)
            row = tk.Frame(self.inner, background=row_bg, height=self.ROW_HEIGHT)
            row.pack(fill=tk.X)
            row.pack_propagate(False)
            self._row_frames[self._resolved(path)] = row

            content = tk.Frame(row, background=row_bg)
            content.pack(fill=tk.BOTH, expand=True, padx=12, pady=7)

            name_lbl = tk.Label(
                content,
                text=self._display_name(path),
                anchor=tk.W,
                background=row_bg,
                foreground=self.FG_NAME,
                font=("", 10),
            )
            name_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)

            duration_lbl = tk.Label(
                content,
                text=self._duration_text(path),
                anchor=tk.E,
                background=row_bg,
                foreground=self.FG_PENDING if self._duration_text(path) == self._pending_label else self.FG_DURATION,
                font=("", 9),
                width=8,
            )
            duration_lbl.pack(side=tk.RIGHT)

            sep = tk.Frame(self.inner, background=self.SEP_COLOR, height=1)
            sep.pack(fill=tk.X)

            for widget in (row, content, name_lbl, duration_lbl):
                widget.bind("<Button-1>", lambda e, p=path, i=index: self._on_row_click(e, p, i))
                widget.bind("<Double-Button-1>", lambda e, p=path: self._on_row_double_click(e, p))

    def _on_row_double_click(self, event: tk.Event, path: Path) -> None:
        if event.state & 0x0004 or event.state & 0x0001:
            return
        if self._activate_handler is not None:
            self._activate_handler(path)

    def _on_row_click(self, event: tk.Event, path: Path, index: int) -> None:
        resolved = self._resolved(path)
        if event.state & 0x0004:
            if resolved in self._selected:
                self._selected.remove(resolved)
            else:
                self._selected.add(resolved)
        elif (event.state & 0x0001) and self._last_index is not None:
            start = min(self._last_index, index)
            end = max(self._last_index, index)
            self._selected = {self._resolved(self._paths[i]) for i in range(start, end + 1)}
        else:
            self._selected = {resolved}
        self._last_index = index
        self._update_row_styles()
        self._notify_selection_changed()

    def _update_row_styles(self) -> None:
        for index, path in enumerate(self._paths):
            row = self._row_frames.get(self._resolved(path))
            if row is None:
                continue
            bg = self._row_background(index, path)
            duration_text = self._duration_text(path)
            duration_fg = self.FG_PENDING if duration_text == self._pending_label else self.FG_DURATION
            self._set_widget_tree_style(row, bg, duration_text, duration_fg)

    def _set_widget_tree_style(
        self,
        frame: tk.Frame,
        background: str,
        duration_text: str,
        duration_fg: str,
    ) -> None:
        for child in frame.winfo_children():
            if isinstance(child, tk.Frame):
                child.configure(background=background)
                labels = child.winfo_children()
                if labels:
                    labels[0].configure(background=background)
                if len(labels) > 1:
                    labels[1].configure(background=background, foreground=duration_fg, text=duration_text)
            frame.configure(background=background)
