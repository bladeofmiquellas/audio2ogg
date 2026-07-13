import os
import queue
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from tkinterdnd2 import DND_FILES, TkinterDnD

from .constants import (
    __version__,
    CHANNEL_CHOICES,
    LANGUAGE_OPTIONS,
    QUALITY_CHOICES,
    QUALITY_QA,
    SAMPLE_RATE_CHOICES,
    TRANSLATIONS,
)
from . import changelog
from .converter import (
    ConversionOptions,
    expand_input_paths,
    filter_audio_files,
    probe_audio_duration,
    resolve_ffmpeg_path,
    resolve_ffprobe_path,
    run_conversion,
)
from .file_list import FileListPanel
from . import settings
from .tooltip import ToolTip


class OggConverterApp(TkinterDnD.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.geometry("760x520")
        self.minsize(700, 440)

        self.files: list[Path] = []
        self.log_queue: "queue.Queue[str]" = queue.Queue()
        self.is_converting = False
        self.ffmpeg_path = resolve_ffmpeg_path()
        self.ffprobe_path = resolve_ffprobe_path(self.ffmpeg_path)
        self._file_durations: dict[Path, float] = {}
        self._probing_durations = False
        self._prefs = settings.load()

        self.language = self._prefs.get("language", "en")
        lang_name = next((k for k, v in LANGUAGE_OPTIONS.items() if v == self.language), "English")
        self.language_var = tk.StringVar(value=lang_name)

        default_out = str(Path.cwd() / "converted")
        self.output_dir = tk.StringVar(value=self._prefs.get("output_dir") or default_out)
        self.output_dir.trace_add("write", self._on_output_dir_changed)

        self.quality_var = tk.StringVar(value=self._prefs.get("quality", "medium"))
        self.channels_var = tk.StringVar(value=self._prefs.get("channels", "original"))
        self.sample_rate_var = tk.StringVar(value=self._prefs.get("sample_rate", "48000"))
        self.quality_display_var = tk.StringVar()
        self.channels_display_var = tk.StringVar()
        self.sample_rate_display_var = tk.StringVar()

        self._conflict_apply_all: str | None = None
        self._conflict_choice = "rename"
        self._conflict_event = threading.Event()
        self._conflict_src: Path | None = None
        self._conflict_target: Path | None = None

        self._tooltips: dict[str, list[ToolTip]] = {}

        self._build_ui()
        self._apply_language()
        self._set_icon()
        self._check_ffmpeg()
        self.after(120, self._drain_log_queue)

    # ── UI construction ────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=12)
        root.pack(fill=tk.BOTH, expand=True)

        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        self.version_label = ttk.Label(root, text=f"v{__version__}", foreground="gray", font=("", 8), cursor="hand2")
        self.version_label.pack(anchor=tk.SE, pady=(2, 0))
        self.version_label.bind("<Button-1>", lambda _e: self._show_changelog())

        self.converter_tab = ttk.Frame(self.notebook, padding=8)
        self.log_tab       = ttk.Frame(self.notebook, padding=8)
        self.settings_tab  = ttk.Frame(self.notebook, padding=8)
        self.help_tab      = ttk.Frame(self.notebook, padding=16)
        for tab in (self.converter_tab, self.log_tab, self.settings_tab, self.help_tab):
            self.notebook.add(tab)

        self._build_converter_tab()
        self._build_log_tab()
        self._build_settings_tab()
        self._build_help_tab()
        self._register_tooltips()

    def _register_tooltips(self) -> None:
        self._register_tooltip("tooltip_output_dir", self.choose_output_btn)
        self._register_tooltip("tooltip_quality", self.quality_combo)
        self._register_tooltip("tooltip_channels", self.channels_combo)
        self._register_tooltip("tooltip_sample_rate", self.sample_rate_combo)
        self._register_tooltip("tooltip_add_files", self.add_files_btn)
        self._register_tooltip("tooltip_remove_selected", self.remove_selected_btn)
        self._register_tooltip("tooltip_clear_list", self.clear_list_btn)
        self._register_tooltip("tooltip_convert", self.convert_btn)
        self._register_tooltip("tooltip_language", self.language_combo)
        self._register_tooltip("tooltip_changelog", self.changelog_btn)

    def _build_converter_tab(self) -> None:
        top_bar = ttk.Frame(self.converter_tab)
        top_bar.pack(fill=tk.X, pady=(0, 10))

        self.output_label = ttk.Label(top_bar)
        self.output_label.pack(side=tk.LEFT)

        style = ttk.Style()
        style.configure("Readonly.TEntry", foreground="gray")
        self.output_entry = ttk.Entry(
            top_bar,
            textvariable=self.output_dir,
            state="readonly",
            style="Readonly.TEntry",
        )
        self.output_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)

        self.choose_output_btn = ttk.Button(top_bar, command=self._pick_output_dir)
        self.choose_output_btn.pack(side=tk.LEFT)

        opts_bar = ttk.Frame(self.converter_tab)
        opts_bar.pack(fill=tk.X, pady=(0, 10))

        self.quality_label = ttk.Label(opts_bar)
        self.quality_label.pack(side=tk.LEFT)
        self.quality_combo = ttk.Combobox(
            opts_bar,
            textvariable=self.quality_display_var,
            state="readonly",
            width=12,
        )
        self.quality_combo.pack(side=tk.LEFT, padx=(8, 16))
        self.quality_combo.bind("<<ComboboxSelected>>", self._on_quality_changed)

        self.channels_label = ttk.Label(opts_bar)
        self.channels_label.pack(side=tk.LEFT)
        self.channels_combo = ttk.Combobox(
            opts_bar,
            textvariable=self.channels_display_var,
            state="readonly",
            width=14,
        )
        self.channels_combo.pack(side=tk.LEFT, padx=(8, 16))
        self.channels_combo.bind("<<ComboboxSelected>>", self._on_channels_changed)

        self.sample_rate_label = ttk.Label(opts_bar)
        self.sample_rate_label.pack(side=tk.LEFT)
        self.sample_rate_combo = ttk.Combobox(
            opts_bar,
            textvariable=self.sample_rate_display_var,
            state="readonly",
            width=14,
        )
        self.sample_rate_combo.pack(side=tk.LEFT, padx=(8, 0))
        self.sample_rate_combo.bind("<<ComboboxSelected>>", self._on_sample_rate_changed)

        self.drop_frame = ttk.LabelFrame(self.converter_tab)
        self.drop_frame.pack(fill=tk.BOTH, expand=True)

        list_wrap = ttk.Frame(self.drop_frame)
        list_wrap.pack(fill=tk.BOTH, expand=True, padx=8, pady=(8, 4))

        self.file_list = FileListPanel(list_wrap)
        self.file_list.pack(fill=tk.BOTH, expand=True)
        self.file_list.dnd_widget().drop_target_register(DND_FILES)
        self.file_list.dnd_widget().dnd_bind("<<Drop>>", self._on_drop)
        self.file_list.dnd_widget().bind("<Delete>", lambda _e: self._remove_selected())
        self.file_list.bind("<Delete>", lambda _e: self._remove_selected())
        self.file_list.bind("<Escape>", lambda _e: self.file_list.clear_selection())

        self.list_summary_label = ttk.Label(self.drop_frame, foreground="gray", font=("", 9))
        self.list_summary_label.pack(anchor=tk.W, padx=8, pady=(0, 8))

        self.bind("<Control-Return>", lambda _e: self._start_conversion())
        self.bind("<Control-KeyPress>", self._on_ctrl_key)

        buttons = ttk.Frame(self.converter_tab)
        buttons.pack(fill=tk.X, pady=10)

        self.add_files_btn      = ttk.Button(buttons, command=self._add_files_dialog)
        self.remove_selected_btn = ttk.Button(buttons, command=self._remove_selected)
        self.clear_list_btn     = ttk.Button(buttons, command=self._clear_list)
        self.convert_btn        = ttk.Button(buttons, command=self._start_conversion)

        self.add_files_btn.pack(side=tk.LEFT)
        self.remove_selected_btn.pack(side=tk.LEFT, padx=8)
        self.clear_list_btn.pack(side=tk.LEFT)
        self.convert_btn.pack(side=tk.RIGHT)

        self.progress_frame = ttk.Frame(self.converter_tab)
        self.progress_frame.pack(fill=tk.X, pady=(0, 4))

        self.progress_label = ttk.Label(self.progress_frame, text="", foreground="gray", font=("", 8))
        self.progress_label.pack(anchor=tk.W)

        self.progress_bar = ttk.Progressbar(self.progress_frame, mode="determinate")
        self.progress_bar.pack(fill=tk.X)

        self.progress_frame.pack_forget()

    def _build_log_tab(self) -> None:
        self.log_text = tk.Text(self.log_tab, state=tk.DISABLED, wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def _build_settings_tab(self) -> None:
        settings_wrap = ttk.LabelFrame(self.settings_tab, padding=12)
        settings_wrap.pack(fill=tk.X, anchor=tk.N)

        language_row = ttk.Frame(settings_wrap)
        language_row.pack(fill=tk.X)

        self.language_label = ttk.Label(language_row)
        self.language_label.pack(side=tk.LEFT)

        self.language_combo = ttk.Combobox(
            language_row,
            textvariable=self.language_var,
            values=list(LANGUAGE_OPTIONS.keys()),
            state="readonly",
            width=10,
        )
        self.language_combo.pack(side=tk.LEFT, padx=(8, 0))
        self.language_combo.bind("<<ComboboxSelected>>", self._on_language_changed)

        self.settings_frame = settings_wrap

    def _build_help_tab(self) -> None:
        self.help_shortcuts_label = ttk.Label(self.help_tab, font=("", 10, "bold"))
        self.help_shortcuts_label.grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 8))

        self._help_row_widgets: list[tuple[ttk.Label, ttk.Label]] = []
        for i in range(6):
            key_lbl  = ttk.Label(self.help_tab, font=("Consolas", 10, "bold"), foreground="#444")
            desc_lbl = ttk.Label(self.help_tab, font=("", 10))
            key_lbl.grid(row=i + 1, column=0, sticky=tk.W, padx=(0, 24), pady=2)
            desc_lbl.grid(row=i + 1, column=1, sticky=tk.W, pady=2)
            self._help_row_widgets.append((key_lbl, desc_lbl))

        self.help_note_label = ttk.Label(self.help_tab, font=("", 9), foreground="gray")
        self.help_note_label.grid(row=8, column=0, columnspan=2, sticky=tk.W, pady=(16, 0))

        self.changelog_btn = ttk.Button(self.help_tab, command=self._show_changelog)
        self.changelog_btn.grid(row=9, column=0, columnspan=2, sticky=tk.W, pady=(12, 0))

    # ── Language ───────────────────────────────────────────────────────────────

    def _t(self, key: str, **kwargs: object) -> str:
        template = TRANSLATIONS.get(self.language, TRANSLATIONS["en"]).get(key, key)
        return template.format(**kwargs) if kwargs else template

    def _on_language_changed(self, _event: tk.Event) -> None:
        code = LANGUAGE_OPTIONS.get(self.language_var.get(), "en")
        if code == self.language:
            return
        self.language = code
        self._apply_language()
        self._log(self._t("language_switched"))
        self._save_settings()

    def _on_output_dir_changed(self, *_) -> None:
        self._save_settings()

    def _on_quality_changed(self, _event: tk.Event | None = None) -> None:
        value = self._value_from_label(self.quality_display_var.get(), QUALITY_CHOICES)
        self.quality_var.set(value)
        self._save_settings()

    def _on_channels_changed(self, _event: tk.Event | None = None) -> None:
        value = self._value_from_label(self.channels_display_var.get(), CHANNEL_CHOICES)
        self.channels_var.set(value)
        self._save_settings()

    def _on_sample_rate_changed(self, _event: tk.Event | None = None) -> None:
        value = self._value_from_label(self.sample_rate_display_var.get(), SAMPLE_RATE_CHOICES)
        self.sample_rate_var.set(value)
        self._save_settings()

    def _label_from_value(self, value: str, choices: list[tuple[str, str]]) -> str:
        for item_value, key in choices:
            if item_value == value:
                return self._t(key)
        return self._t(choices[0][1])

    def _value_from_label(self, label: str, choices: list[tuple[str, str]]) -> str:
        for value, key in choices:
            if self._t(key) == label:
                return value
        return choices[0][0]

    def _choice_labels(self, choices: list[tuple[str, str]]) -> list[str]:
        return [self._t(key) for _, key in choices]

    def _conversion_options(self) -> ConversionOptions:
        quality_level = self.quality_var.get()
        if quality_level not in QUALITY_QA:
            quality_level = "medium"
        return ConversionOptions(
            quality=QUALITY_QA[quality_level],
            channels=self.channels_var.get(),
            sample_rate=self.sample_rate_var.get(),
        )

    def _save_settings(self) -> None:
        self._prefs["language"] = self.language
        self._prefs["output_dir"] = self.output_dir.get()
        self._prefs["quality"] = (
            self.quality_var.get() if self.quality_var.get() in QUALITY_QA else "medium"
        )
        self._prefs["channels"] = self.channels_var.get()
        self._prefs["sample_rate"] = self.sample_rate_var.get()
        settings.save(self._prefs)

    def _register_tooltip(self, key: str, *widgets: tk.Misc) -> None:
        self._tooltips[key] = [ToolTip(widget) for widget in widgets]

    def _update_tooltips(self) -> None:
        for key, tips in self._tooltips.items():
            text = self._t(key)
            for tip in tips:
                tip.set_text(text)

    def _apply_language(self) -> None:
        self.title(self._t("window_title"))
        self.notebook.tab(0, text=self._t("tab_converter"))
        self.notebook.tab(1, text=self._t("tab_log"))
        self.notebook.tab(2, text=self._t("tab_settings"))
        self.notebook.tab(3, text=self._t("tab_help"))
        self.settings_frame.configure(text=self._t("settings_frame_title"))
        self.language_label.configure(text=self._t("language_label"))
        self.output_label.configure(text=self._t("output_dir_label"))
        self.quality_label.configure(text=self._t("quality_label"))
        self.quality_combo.configure(values=self._choice_labels(QUALITY_CHOICES))
        self.quality_display_var.set(self._label_from_value(self.quality_var.get(), QUALITY_CHOICES))
        self.channels_label.configure(text=self._t("channels_label"))
        self.sample_rate_label.configure(text=self._t("sample_rate_label"))
        self.channels_combo.configure(values=self._choice_labels(CHANNEL_CHOICES))
        self.channels_display_var.set(self._label_from_value(self.channels_var.get(), CHANNEL_CHOICES))
        self.sample_rate_combo.configure(values=self._choice_labels(SAMPLE_RATE_CHOICES))
        self.sample_rate_display_var.set(self._label_from_value(self.sample_rate_var.get(), SAMPLE_RATE_CHOICES))
        self.choose_output_btn.configure(text=self._t("choose_button"))
        self.drop_frame.configure(text=self._t("drop_frame_title"))
        self.add_files_btn.configure(text=self._t("add_files_button"))
        self.remove_selected_btn.configure(text=self._t("remove_selected_button"))
        self.clear_list_btn.configure(text=self._t("clear_list_button"))
        self.convert_btn.configure(text=self._t("convert_button"))
        self.file_list.configure_presenters(
            display_name=self._display_name,
            format_duration=self._format_duration_compact,
            pending_label=self._t("list_duration_pending"),
        )
        self._refresh_file_list()
        self.help_shortcuts_label.configure(text=self._t("help_shortcuts_title"))
        for (key_lbl, desc_lbl), (key, desc) in zip(
            self._help_row_widgets, self._t("help_shortcuts")
        ):
            key_lbl.configure(text=key)
            desc_lbl.configure(text=desc)
        self.help_note_label.configure(text=self._t("help_note"))
        self.changelog_btn.configure(text=self._t("changelog_button"))
        self._update_list_summary()
        self._update_tooltips()

    # ── Icon ───────────────────────────────────────────────────────────────────

    def _set_icon(self) -> None:
        meipass = getattr(sys, "_MEIPASS", None)
        base_dirs = []
        if meipass:
            base_dirs.append(Path(meipass) / "assets")
        base_dirs.append(Path(__file__).resolve().parent.parent / "assets")

        for base in base_dirs:
            png = base / "icon.png"
            if png.exists():
                try:
                    from PIL import Image, ImageTk
                    src = Image.open(str(png)).convert("RGBA")
                    self._icon_refs = [
                        ImageTk.PhotoImage(src.resize((s, s), Image.LANCZOS))
                        for s in (256, 48, 32, 16)
                    ]
                    self.iconphoto(True, *self._icon_refs)
                    return
                except Exception:
                    pass

    # ── File list ──────────────────────────────────────────────────────────────

    def _file_count_label(self, count: int) -> str:
        if self.language == "ru":
            n = abs(count) % 100
            n1 = n % 10
            if n1 == 1 and n != 11:
                word = "файл"
            elif n1 in (2, 3, 4) and n not in (12, 13, 14):
                word = "файла"
            else:
                word = "файлов"
            return f"{count} {word}"
        if self.language == "zh":
            return f"{count} 个文件"
        return f"{count} file" if count == 1 else f"{count} files"

    def _format_duration(self, seconds: float) -> str:
        total = max(0, int(round(seconds)))
        hours = total // 3600
        minutes = (total % 3600) // 60
        secs = total % 60

        if self.language == "ru":
            parts: list[str] = []
            if hours:
                parts.append(f"{hours} ч")
            if minutes or hours:
                parts.append(f"{minutes} мин")
            parts.append(f"{secs} сек")
            return " ".join(parts)

        if self.language == "zh":
            parts = []
            if hours:
                parts.append(f"{hours} 小时")
            if minutes or hours:
                parts.append(f"{minutes} 分")
            parts.append(f"{secs} 秒")
            return " ".join(parts)

        if hours:
            return f"{hours} hr {minutes} min {secs} sec"
        if minutes:
            return f"{minutes} min {secs} sec"
        return f"{secs} sec"

    def _format_duration_compact(self, seconds: float) -> str:
        total = max(0, int(round(seconds)))
        hours = total // 3600
        minutes = (total % 3600) // 60
        secs = total % 60
        if hours:
            return f"{hours}:{minutes:02d}:{secs:02d}"
        return f"{minutes}:{secs:02d}"

    def _display_name(self, path: Path) -> str:
        names = [item.name for item in self.files]
        if names.count(path.name) > 1:
            return str(path)
        return path.name

    def _refresh_file_list(self) -> None:
        self.file_list.set_items(
            self.files,
            self._file_durations,
            probing=self._probing_durations and bool(self.ffmpeg_path),
        )

    def _update_list_summary(self) -> None:
        count = len(self.files)
        if count == 0:
            self.list_summary_label.configure(text=self._t("list_summary_empty"))
            return

        parts = [self._file_count_label(count)]
        known = [p for p in self.files if p.resolve() in self._file_durations]
        if len(known) == count:
            total_seconds = sum(self._file_durations[p.resolve()] for p in self.files)
            if total_seconds > 0:
                parts.append(self._format_duration(total_seconds))

        self.list_summary_label.configure(text=", ".join(parts))

    def _probe_durations_async(self, paths: list[Path]) -> None:
        if not self.ffmpeg_path or not paths:
            return

        ffmpeg_path = self.ffmpeg_path
        ffprobe_path = self.ffprobe_path
        self._probing_durations = True
        self._refresh_file_list()

        def worker() -> None:
            updates: dict[Path, float] = {}
            current_files = {p.resolve() for p in self.files}
            for path in paths:
                resolved = path.resolve()
                if resolved not in current_files:
                    continue
                duration = probe_audio_duration(
                    path,
                    ffmpeg_path=ffmpeg_path,
                    ffprobe_path=ffprobe_path,
                )
                if duration is not None and duration > 0:
                    updates[resolved] = duration
            self.after(0, lambda: self._finish_duration_probe(updates))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_duration_probe(self, updates: dict[Path, float]) -> None:
        self._probing_durations = False
        self._apply_duration_updates(updates)

    def _apply_duration_updates(self, updates: dict[Path, float]) -> None:
        self._file_durations.update(updates)
        self._refresh_file_list()
        self._update_list_summary()

    def _pick_output_dir(self) -> None:
        selected = filedialog.askdirectory(initialdir=self.output_dir.get() or str(Path.cwd()))
        if selected:
            self.output_dir.set(selected)

    def _add_files_dialog(self) -> None:
        paths = filedialog.askopenfilenames(
            title=self._t("pick_audio_title"),
            filetypes=[(self._t("audio_files_filter"), "*.*")],
        )
        self._add_files([Path(p) for p in paths])

    def _on_drop(self, event: tk.Event) -> None:
        self._add_files([Path(p) for p in self.tk.splitlist(event.data)])

    def _add_files(self, paths: list[Path]) -> None:
        expanded = expand_input_paths(paths)
        existing = {p.resolve() for p in self.files}
        accepted, skipped = filter_audio_files(expanded, existing)
        for p in accepted:
            self.files.append(p)
        if accepted:
            self._refresh_file_list()
            self._log(self._t("log_added_files", count=len(accepted)))
            self._update_list_summary()
            self._probe_durations_async(accepted)
        if skipped:
            self._log(self._t("log_skipped_items", count=skipped))

    _CTRL_HOTKEYS: dict[int, str] = {
        65: "_select_all",        # A
        79: "_add_files_dialog",  # O
        76: "_clear_list",        # L
    }

    def _on_ctrl_key(self, event: tk.Event) -> str | None:
        action = self._CTRL_HOTKEYS.get(event.keycode)
        if action:
            getattr(self, action)()
            return "break"
        return None

    def _select_all(self, _event: tk.Event = None) -> str:
        self.file_list.select_all()
        return "break"

    def _remove_selected(self) -> None:
        selected = self.file_list.get_selected_paths()
        if not selected:
            return
        to_remove = {path.resolve() for path in selected}
        self.files = [path for path in self.files if path.resolve() not in to_remove]
        for resolved in to_remove:
            self._file_durations.pop(resolved, None)
        self._refresh_file_list()
        self._log(self._t("log_removed_files", count=len(selected)))
        self._update_list_summary()

    def _clear_list(self) -> None:
        if self.files:
            self.files.clear()
            self._file_durations.clear()
            self._refresh_file_list()
            self._log(self._t("log_list_cleared"))
            self._update_list_summary()

    # ── Conversion ─────────────────────────────────────────────────────────────

    def _check_ffmpeg(self) -> None:
        if self.ffmpeg_path:
            self._log(self._t("ffmpeg_found", path=self.ffmpeg_path))
            return
        self._log(self._t("ffmpeg_missing_log"))
        messagebox.showwarning(self._t("ffmpeg_missing_title"), self._t("ffmpeg_missing_message"))

    def _start_conversion(self) -> None:
        if self.is_converting:
            return
        if not self.files:
            messagebox.showinfo(self._t("no_files_title"), self._t("no_files_message"))
            return
        if not self.ffmpeg_path:
            messagebox.showerror(self._t("error_title"), self._t("ffmpeg_not_found_short"))
            return

        out_dir = Path(self.output_dir.get().strip() or Path.cwd() / "converted")
        out_dir.mkdir(parents=True, exist_ok=True)

        self.is_converting = True
        self.progress_bar["value"] = 0
        self.progress_bar["maximum"] = len(self.files)
        self.progress_label.configure(text="")
        self.progress_frame.pack(fill=tk.X, pady=(0, 4))
        self._log(self._t("log_start_conversion", count=len(self.files)))
        self._set_ui_locked(True)
        self._conflict_apply_all = None

        threading.Thread(
            target=run_conversion,
            args=(
                self.ffmpeg_path,
                list(self.files),
                out_dir,
                self._conversion_options(),
                self.log_queue,
                self._t,
                self._resolve_conflict,
            ),
            daemon=True,
        ).start()

    def _resolve_conflict(self, src: Path, target: Path) -> str:
        if self._conflict_apply_all:
            return self._conflict_apply_all

        self._conflict_src = src
        self._conflict_target = target
        self._conflict_event.clear()
        self.after(0, self._show_conflict_dialog)
        self._conflict_event.wait()
        return self._conflict_choice

    def _release_busy(self) -> None:
        try:
            self.tk.call("tk", "busy", "forget", self)
        except Exception:
            pass

    def _restore_busy(self) -> None:
        if self.is_converting:
            try:
                self.tk.call("tk", "busy", "hold", self)
            except Exception:
                pass

    def _show_conflict_dialog(self) -> None:
        target = self._conflict_target
        if target is None:
            self._conflict_choice = "rename"
            self._conflict_event.set()
            return

        self._release_busy()

        dlg = tk.Toplevel(self)
        dlg.title(self._t("conflict_dialog_title"))
        dlg.resizable(False, False)
        dlg.transient(self)
        dlg.grab_set()

        frame = ttk.Frame(dlg, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            frame,
            text=self._t("conflict_dialog_message", name=target.name),
            wraplength=360,
            font=("", 10),
        ).pack(anchor=tk.W, pady=(0, 12))

        apply_all_var = tk.BooleanVar(value=False)

        def choose(policy: str) -> None:
            if apply_all_var.get():
                self._conflict_apply_all = policy
            self._conflict_choice = policy
            dlg.destroy()
            self._restore_busy()
            self._conflict_event.set()

        btn_row = ttk.Frame(frame)
        btn_row.pack(fill=tk.X, pady=(0, 12))
        ttk.Button(
            btn_row,
            text=self._t("conflict_btn_overwrite"),
            command=lambda: choose("overwrite"),
        ).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 4))
        ttk.Button(
            btn_row,
            text=self._t("conflict_btn_skip"),
            command=lambda: choose("skip"),
        ).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=4)
        ttk.Button(
            btn_row,
            text=self._t("conflict_btn_rename"),
            command=lambda: choose("rename"),
        ).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(4, 0))

        ttk.Checkbutton(frame, text=self._t("conflict_apply_all"), variable=apply_all_var).pack(anchor=tk.W)

        dlg.protocol("WM_DELETE_WINDOW", lambda: choose("skip"))
        dlg.bind("<Escape>", lambda _e: choose("skip"))

        dlg.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - dlg.winfo_width()) // 2
        y = self.winfo_y() + (self.winfo_height() - dlg.winfo_height()) // 2
        dlg.geometry(f"+{x}+{y}")

    def _format_done_message(self, ok: int, failed: int, skipped: int = 0) -> str:
        message = self._t("log_done", ok=ok, failed=failed)
        if skipped:
            message += self._t("log_done_skipped", skipped=skipped)
        return message

    def _drain_log_queue(self) -> None:
        while True:
            try:
                message = self.log_queue.get_nowait()
            except queue.Empty:
                break
            if message.startswith("PROGRESS::"):
                _, current, total, name = message.split("::", 3)
                self.progress_bar["value"] = int(current)
                self.progress_label.configure(
                    text=f"{name}  ({current}/{total})"
                )
            elif message.startswith("DONE::"):
                parts = message.split("::")
                ok, failed = int(parts[1]), int(parts[2])
                skipped = int(parts[3]) if len(parts) > 3 else 0
                self._log(self._format_done_message(ok, failed, skipped))
                self.is_converting = False
                self.progress_frame.pack_forget()
                self._set_ui_locked(False)
                self._play_completion_sound()
                self._show_done_dialog(ok, failed, skipped)
            else:
                self._log(message)
        self.after(120, self._drain_log_queue)

    def _play_completion_sound(self) -> None:
        if sys.platform != "win32":
            return
        try:
            import winsound
            winsound.PlaySound("SystemAsterisk", winsound.SND_ALIAS | winsound.SND_ASYNC)
        except Exception:
            pass

    def _show_changelog(self) -> None:
        dlg = tk.Toplevel(self)
        dlg.title(self._t("changelog_title"))
        dlg.resizable(False, False)
        dlg.transient(self)
        dlg.grab_set()

        frame = ttk.Frame(dlg, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)

        for entry in changelog.load():
            ttk.Label(frame, text=f"v{entry['version']}", font=("", 11, "bold")).pack(anchor=tk.W)
            changes = entry.get("changes", {})
            items = changes.get(self.language) or changes.get("en") or []
            for change in items:
                ttk.Label(frame, text=f"  • {change}", font=("", 9)).pack(anchor=tk.W, pady=1)
            ttk.Separator(frame).pack(fill=tk.X, pady=8)

        ttk.Button(frame, text="OK", command=dlg.destroy, width=10).pack(anchor=tk.E)
        dlg.bind("<Return>", lambda _: dlg.destroy())
        dlg.bind("<Escape>", lambda _: dlg.destroy())

        dlg.update_idletasks()
        x = self.winfo_x() + (self.winfo_width()  - dlg.winfo_width())  // 2
        y = self.winfo_y() + (self.winfo_height() - dlg.winfo_height()) // 2
        dlg.geometry(f"+{x}+{y}")

    def _set_ui_locked(self, locked: bool) -> None:
        try:
            if locked:
                self.tk.call("tk", "busy", "hold", self)
            else:
                self.tk.call("tk", "busy", "forget", self)
        except Exception:
            self.convert_btn.configure(state=tk.DISABLED if locked else tk.NORMAL)

    def _show_done_dialog(self, ok: int, failed: int, skipped: int = 0) -> None:
        out_dir = Path(self.output_dir.get().strip())

        dlg = tk.Toplevel(self)
        dlg.title(self._t("done_title"))
        dlg.resizable(False, False)
        dlg.transient(self)
        dlg.grab_set()

        ttk.Label(
            dlg,
            text=self._format_done_message(ok, failed, skipped),
            padding=(24, 20, 24, 12),
            font=("", 10),
        ).pack()

        btn_frame = ttk.Frame(dlg, padding=(16, 0, 16, 16))
        btn_frame.pack(fill=tk.X)

        ttk.Button(
            btn_frame,
            text=self._t("open_folder_button"),
            command=lambda: os.startfile(str(out_dir)),
        ).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 4))

        ttk.Button(
            btn_frame,
            text="OK",
            command=dlg.destroy,
        ).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(4, 0))

        dlg.bind("<Return>", lambda _: dlg.destroy())
        dlg.bind("<Escape>", lambda _: dlg.destroy())

        dlg.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - dlg.winfo_width()) // 2
        y = self.winfo_y() + (self.winfo_height() - dlg.winfo_height()) // 2
        dlg.geometry(f"+{x}+{y}")

    # ── Log ────────────────────────────────────────────────────────────────────

    def _log(self, text: str) -> None:
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, text + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)
