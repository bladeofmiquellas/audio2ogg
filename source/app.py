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
    PRESET_CHOICES,
    PRESETS,
    QUALITY_CHOICES,
    QUALITY_QA,
    SAMPLE_RATE_CHOICES,
    THEME_CHOICES,
    TRANSLATIONS,
)
from . import changelog
from .converter import (
    ConversionOptions,
    expand_input_paths,
    filter_audio_files,
    probe_audio_duration,
    estimate_conversion_sizes,
    resolve_ffmpeg_path,
    resolve_ffprobe_path,
    resolve_ffplay_path,
    format_byte_size,
    run_conversion,
)
from .file_list import FileListPanel
from .player import AudioPlayer
from . import settings
from .theme import AppTheme, apply_root_theme, apply_ttk_theme, get_theme
from .tooltip import ToolTip, set_tooltip_theme


class OggConverterApp(TkinterDnD.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.geometry("760x520")
        self.minsize(700, 480)

        self.files: list[Path] = []
        self.log_queue: "queue.Queue[str]" = queue.Queue()
        self.is_converting = False
        self.ffmpeg_path = resolve_ffmpeg_path()
        self.ffprobe_path = resolve_ffprobe_path(self.ffmpeg_path)
        self.ffplay_path = resolve_ffplay_path(self.ffmpeg_path)
        self._player = AudioPlayer(self.ffmpeg_path, self.ffplay_path)
        self._playback_poll_id: str | None = None
        self._file_durations: dict[Path, float] = {}
        self._probing_durations = False
        self._prefs = settings.load()
        self._style = ttk.Style()
        self._theme: AppTheme = get_theme("light")

        self.language = self._prefs.get("language", "en")
        lang_name = next((k for k, v in LANGUAGE_OPTIONS.items() if v == self.language), "English")
        self.language_var = tk.StringVar(value=lang_name)

        default_out = str(Path.cwd() / "converted")
        self.output_dir = tk.StringVar(value=self._prefs.get("output_dir") or default_out)
        self.output_dir.trace_add("write", self._on_output_dir_changed)

        preset = self._prefs.get("preset", "custom")
        if preset not in PRESETS:
            preset = "custom"
        self.preset_var = tk.StringVar(value=preset)
        self.quality_var = tk.StringVar(value=self._prefs.get("quality", "medium"))
        self.channels_var = tk.StringVar(value=self._prefs.get("channels", "original"))
        self.sample_rate_var = tk.StringVar(value=self._prefs.get("sample_rate", "48000"))
        if preset in PRESETS:
            for key, value in PRESETS[preset].items():
                if key == "quality":
                    self.quality_var.set(value)
                elif key == "channels":
                    self.channels_var.set(value)
                elif key == "sample_rate":
                    self.sample_rate_var.set(value)
        self.theme_var = tk.StringVar(value=self._prefs.get("theme", "light"))
        self.preset_display_var = tk.StringVar()
        self.quality_display_var = tk.StringVar()
        self.channels_display_var = tk.StringVar()
        self.sample_rate_display_var = tk.StringVar()
        self.theme_display_var = tk.StringVar()
        self._applying_preset = False

        self._conflict_apply_all: str | None = None
        self._conflict_choice = "rename"
        self._conflict_event = threading.Event()
        self._conflict_src: Path | None = None
        self._conflict_target: Path | None = None
        self._cancel_event = threading.Event()

        self._tooltips: dict[str, list[ToolTip]] = {}
        self._ui_icon_refs: list[tk.PhotoImage] = []

        self._build_ui()
        self._apply_theme()
        self._apply_language()
        self._set_icon()
        self._check_ffmpeg()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(120, self._drain_log_queue)

    # ── UI construction ────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=12)
        root.pack(fill=tk.BOTH, expand=True)

        footer = ttk.Frame(root)
        footer.pack(side=tk.BOTTOM, fill=tk.X, pady=(6, 0))
        self.version_label = ttk.Label(footer, text=f"v{__version__}", font=("", 8), cursor="hand2")
        self.version_label.pack(side=tk.RIGHT)
        self.version_label.bind("<Button-1>", lambda _e: self._show_changelog())

        self.notebook = ttk.Notebook(root)
        self.notebook.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

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
        self._register_tooltip("tooltip_open_output_dir", self.open_output_btn)
        self._register_tooltip("tooltip_preset", self.preset_combo)
        self._register_tooltip("tooltip_quality", self.quality_combo)
        self._register_tooltip("tooltip_channels", self.channels_combo)
        self._register_tooltip("tooltip_sample_rate", self.sample_rate_combo)
        self._register_tooltip("tooltip_add_files", self.add_files_btn)
        self._register_tooltip("tooltip_remove_selected", self.remove_selected_btn)
        self._register_tooltip("tooltip_clear_list", self.clear_list_btn)
        self._register_tooltip("tooltip_play", self.play_btn)
        self._register_tooltip("tooltip_convert", self.convert_btn)
        self._register_tooltip("tooltip_cancel", self.cancel_btn)
        self._register_tooltip("tooltip_language", self.language_combo)
        self._register_tooltip("tooltip_theme", self.theme_combo)
        self._register_tooltip("tooltip_changelog", self.changelog_btn)

    def _build_converter_tab(self) -> None:
        self._style.configure("Icon.TButton", padding=(4, 2))

        self.progress_frame = ttk.Frame(self.converter_tab)
        self.progress_label = ttk.Label(self.progress_frame, text="", font=("", 9))
        self.progress_label.pack(anchor=tk.W, pady=(0, 4))
        self.progress_bar = ttk.Progressbar(self.progress_frame, mode="determinate")
        self.progress_bar.pack(fill=tk.X, ipady=1)

        self.buttons_frame = ttk.Frame(self.converter_tab)
        self.add_files_btn = ttk.Button(self.buttons_frame, command=self._add_files_dialog)
        self.remove_selected_btn = ttk.Button(self.buttons_frame, command=self._remove_selected)
        self.clear_list_btn = ttk.Button(self.buttons_frame, command=self._clear_list)
        self._play_icon = self._create_play_icon()
        self._stop_icon = self._create_stop_icon()
        play_btn_kwargs: dict = {
            "command": self._toggle_playback,
            "style": "Icon.TButton",
            "width": 2,
        }
        if self._play_icon is not None:
            play_btn_kwargs["image"] = self._play_icon
        else:
            play_btn_kwargs["text"] = ">"
        self.play_btn = ttk.Button(self.buttons_frame, **play_btn_kwargs)
        self.convert_btn = ttk.Button(self.buttons_frame, command=self._start_conversion)
        self.cancel_btn = ttk.Button(self.buttons_frame, command=self._cancel_conversion)

        self.add_files_btn.pack(side=tk.LEFT)
        self.remove_selected_btn.pack(side=tk.LEFT, padx=8)
        self.clear_list_btn.pack(side=tk.LEFT)
        self.play_btn.pack(side=tk.LEFT, padx=(8, 0))
        self.convert_btn.pack(side=tk.RIGHT)
        self.buttons_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(8, 0))

        top_bar = ttk.Frame(self.converter_tab)
        top_bar.pack(side=tk.TOP, fill=tk.X, pady=(0, 10))

        self.output_label = ttk.Label(top_bar)
        self.output_label.pack(side=tk.LEFT)

        self.output_entry = ttk.Entry(
            top_bar,
            textvariable=self.output_dir,
            state="readonly",
            style="Readonly.TEntry",
        )
        self.output_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)

        self.choose_output_btn = ttk.Button(top_bar, command=self._pick_output_dir)
        self.choose_output_btn.pack(side=tk.LEFT)
        folder_icon = self._load_folder_icon()
        open_btn_kwargs: dict = {
            "command": self._open_output_dir,
            "style": "Icon.TButton",
        }
        if folder_icon is not None:
            open_btn_kwargs["image"] = folder_icon
            open_btn_kwargs["width"] = 2
        else:
            open_btn_kwargs["text"] = "..."
        self.open_output_btn = ttk.Button(top_bar, **open_btn_kwargs)
        self.open_output_btn.pack(side=tk.LEFT, padx=(6, 0))

        opts_bar = ttk.Frame(self.converter_tab)
        opts_bar.pack(side=tk.TOP, fill=tk.X, pady=(0, 10))

        self.preset_label = ttk.Label(opts_bar)
        self.preset_label.pack(side=tk.LEFT)
        self.preset_combo = ttk.Combobox(
            opts_bar,
            textvariable=self.preset_display_var,
            state="readonly",
            width=12,
        )
        self.preset_combo.pack(side=tk.LEFT, padx=(8, 16))
        self.preset_combo.bind("<<ComboboxSelected>>", self._on_preset_changed)

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
        self.drop_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        list_wrap = ttk.Frame(self.drop_frame)

        self.file_list = FileListPanel(list_wrap)
        self.file_list.pack(fill=tk.BOTH, expand=True)
        self.file_list.dnd_widget().drop_target_register(DND_FILES)
        self.file_list.dnd_widget().dnd_bind("<<Drop>>", self._on_drop)
        self.file_list.set_activate_handler(self._toggle_playback)
        self.file_list.set_selection_handler(self._update_play_controls)

        self.summary_frame = ttk.Frame(self.drop_frame, height=44)
        self.summary_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=(4, 8))
        self.summary_frame.pack_propagate(False)
        self.summary_frame.bind("<Configure>", self._on_summary_frame_configure)

        self.list_summary_label = ttk.Label(
            self.summary_frame,
            font=("", 9),
            anchor=tk.NW,
            justify=tk.LEFT,
        )
        self.list_summary_label.pack(fill=tk.BOTH, expand=True, anchor=tk.W)

        list_wrap.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=8, pady=(8, 4))

        self._bind_converter_space_override(
            self.choose_output_btn,
            self.open_output_btn,
            self.add_files_btn,
            self.remove_selected_btn,
            self.clear_list_btn,
            self.play_btn,
            self.convert_btn,
            self.cancel_btn,
        )

        self.bind("<Control-Return>", lambda _e: self._start_conversion())
        self.bind("<Control-KeyPress>", self._on_ctrl_key)
        self.bind_all("<Delete>", self._on_delete_key)
        self.bind_all("<Escape>", self._on_escape_key)
        self.bind_all("<KeyPress-space>", self._on_space_key)

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

        theme_row = ttk.Frame(settings_wrap)
        theme_row.pack(fill=tk.X, pady=(12, 0))

        self.theme_label = ttk.Label(theme_row)
        self.theme_label.pack(side=tk.LEFT)

        self.theme_combo = ttk.Combobox(
            theme_row,
            textvariable=self.theme_display_var,
            state="readonly",
            width=12,
        )
        self.theme_combo.pack(side=tk.LEFT, padx=(8, 0))
        self.theme_combo.bind("<<ComboboxSelected>>", self._on_theme_changed)

        self.settings_frame = settings_wrap

    def _build_help_tab(self) -> None:
        help_wrap = ttk.Frame(self.help_tab)
        help_wrap.pack(fill=tk.BOTH, expand=True, anchor=tk.NW)
        help_wrap.bind("<Configure>", self._on_help_tab_configure)

        self.help_shortcuts_label = ttk.Label(help_wrap, font=("", 10, "bold"))
        self.help_shortcuts_label.pack(anchor=tk.W, pady=(0, 8))

        self._help_row_widgets: list[tuple[ttk.Label, ttk.Label]] = []
        for _ in range(8):
            row = ttk.Frame(help_wrap)
            row.pack(fill=tk.X, anchor=tk.W, pady=2)
            key_lbl = ttk.Label(row, font=("Consolas", 10, "bold"), width=14, anchor=tk.W)
            key_lbl.pack(side=tk.LEFT, anchor=tk.W)
            desc_lbl = ttk.Label(row, font=("", 10), anchor=tk.W, justify=tk.LEFT)
            desc_lbl.pack(side=tk.LEFT, anchor=tk.W, fill=tk.X, expand=True, padx=(8, 0))
            self._help_row_widgets.append((key_lbl, desc_lbl))

        self.help_note_label = ttk.Label(help_wrap, font=("", 9), justify=tk.LEFT)
        self.help_note_label.pack(anchor=tk.W, pady=(16, 0))

        self.changelog_btn = ttk.Button(help_wrap, command=self._show_changelog)
        self.changelog_btn.pack(anchor=tk.W, pady=(12, 0))

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

    def _on_theme_changed(self, _event: tk.Event | None = None) -> None:
        value = self._value_from_label(self.theme_display_var.get(), THEME_CHOICES)
        if value == self.theme_var.get():
            return
        self.theme_var.set(value)
        self._apply_theme()
        self._log(self._t("theme_switched", theme=self._label_from_value(value, THEME_CHOICES)))
        self._save_settings()

    def _on_output_dir_changed(self, *_) -> None:
        self._save_settings()

    def _on_preset_changed(self, _event: tk.Event | None = None) -> None:
        value = self._value_from_label(self.preset_display_var.get(), PRESET_CHOICES)
        self.preset_var.set(value)
        if value in PRESETS:
            self._apply_preset(value)
        self._release_combobox_focus(self.preset_combo)
        self._save_settings()
        self._update_list_summary()

    def _apply_preset(self, preset_id: str) -> None:
        preset = PRESETS.get(preset_id)
        if preset is None:
            return
        self._applying_preset = True
        try:
            self.quality_var.set(preset["quality"])
            self.channels_var.set(preset["channels"])
            self.sample_rate_var.set(preset["sample_rate"])
            self.quality_display_var.set(
                self._label_from_value(preset["quality"], QUALITY_CHOICES)
            )
            self.channels_display_var.set(
                self._label_from_value(preset["channels"], CHANNEL_CHOICES)
            )
            self.sample_rate_display_var.set(
                self._label_from_value(preset["sample_rate"], SAMPLE_RATE_CHOICES)
            )
        finally:
            self._applying_preset = False

    def _switch_to_custom_preset(self) -> None:
        if self.preset_var.get() == "custom":
            return
        self.preset_var.set("custom")
        self.preset_display_var.set(self._label_from_value("custom", PRESET_CHOICES))

    def _on_quality_changed(self, _event: tk.Event | None = None) -> None:
        value = self._value_from_label(self.quality_display_var.get(), QUALITY_CHOICES)
        self.quality_var.set(value)
        if not self._applying_preset:
            self._switch_to_custom_preset()
        self._release_combobox_focus(self.quality_combo)
        self._save_settings()
        self._update_list_summary()

    def _on_channels_changed(self, _event: tk.Event | None = None) -> None:
        value = self._value_from_label(self.channels_display_var.get(), CHANNEL_CHOICES)
        self.channels_var.set(value)
        if not self._applying_preset:
            self._switch_to_custom_preset()
        self._release_combobox_focus(self.channels_combo)
        self._save_settings()
        self._update_list_summary()

    def _on_sample_rate_changed(self, _event: tk.Event | None = None) -> None:
        value = self._value_from_label(self.sample_rate_display_var.get(), SAMPLE_RATE_CHOICES)
        self.sample_rate_var.set(value)
        if not self._applying_preset:
            self._switch_to_custom_preset()
        self._release_combobox_focus(self.sample_rate_combo)
        self._save_settings()
        self._update_list_summary()

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
        preset = self.preset_var.get()
        self._prefs["preset"] = preset if preset in PRESETS or preset == "custom" else "custom"
        self._prefs["quality"] = (
            self.quality_var.get() if self.quality_var.get() in QUALITY_QA else "medium"
        )
        self._prefs["channels"] = self.channels_var.get()
        self._prefs["sample_rate"] = self.sample_rate_var.get()
        self._prefs["theme"] = self.theme_var.get() if self.theme_var.get() in {"light", "dark"} else "light"
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
        self.theme_label.configure(text=self._t("theme_label"))
        self.theme_combo.configure(values=self._choice_labels(THEME_CHOICES))
        self.theme_display_var.set(self._label_from_value(self.theme_var.get(), THEME_CHOICES))
        self.output_label.configure(text=self._t("output_dir_label"))
        self.preset_label.configure(text=self._t("preset_label"))
        self.preset_combo.configure(values=self._choice_labels(PRESET_CHOICES))
        self.preset_display_var.set(self._label_from_value(self.preset_var.get(), PRESET_CHOICES))
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
        self._update_play_controls()
        self.convert_btn.configure(text=self._t("convert_button"))
        self.cancel_btn.configure(text=self._t("cancel_button"))
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

    def _apply_theme(self) -> None:
        theme_name = self.theme_var.get()
        self._theme = get_theme(theme_name)
        apply_ttk_theme(self._style, self._theme)
        self._style.configure("Horizontal.TProgressbar", thickness=14)
        apply_root_theme(self, self._theme)

        set_tooltip_theme(
            bg=self._theme.tip_bg,
            fg=self._theme.tip_fg,
            border=self._theme.tip_border,
        )

        self.file_list.apply_theme(
            bg_even=self._theme.list_bg_even,
            bg_odd=self._theme.list_bg_odd,
            bg_selected=self._theme.list_bg_selected,
            bg_playing=self._theme.list_bg_playing,
            fg_name=self._theme.list_fg_name,
            fg_duration=self._theme.list_fg_duration,
            fg_pending=self._theme.list_fg_pending,
            sep_color=self._theme.list_sep,
        )

        self.log_text.configure(
            background=self._theme.log_bg,
            foreground=self._theme.log_fg,
            insertbackground=self._theme.log_fg,
            selectbackground=self._theme.select_bg,
            selectforeground=self._theme.fg,
            highlightthickness=0,
            borderwidth=0,
        )

        for label in (
            self.version_label,
            self.progress_label,
            self.list_summary_label,
            self.help_note_label,
        ):
            label.configure(foreground=self._theme.muted)

        for key_lbl, _desc_lbl in self._help_row_widgets:
            key_lbl.configure(foreground=self._theme.help_key_fg)

    # ── Icon ───────────────────────────────────────────────────────────────────

    def _asset_dirs(self) -> list[Path]:
        meipass = getattr(sys, "_MEIPASS", None)
        dirs: list[Path] = []
        if meipass:
            dirs.append(Path(meipass) / "assets")
        dirs.append(Path(__file__).resolve().parent.parent / "assets")
        return dirs

    def _load_folder_icon(self) -> tk.PhotoImage | None:
        for base in self._asset_dirs():
            png = base / "folder.png"
            if not png.exists():
                continue
            try:
                from PIL import Image, ImageTk
                src = Image.open(str(png)).convert("RGBA")
                ref = ImageTk.PhotoImage(src.resize((18, 18), Image.LANCZOS))
                self._ui_icon_refs.append(ref)
                return ref
            except Exception:
                continue
        return self._create_folder_icon()

    def _create_folder_icon(self) -> tk.PhotoImage | None:
        try:
            from PIL import Image, ImageDraw, ImageTk
        except Exception:
            return None

        size = 18
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        tab_color = "#F5C451"
        body_color = "#F0B429"
        border = "#C8942A"
        draw.rounded_rectangle([2, 6, 9, 9], radius=1, fill=tab_color, outline=border, width=1)
        draw.rounded_rectangle([2, 8, 15, 15], radius=2, fill=body_color, outline=border, width=1)
        try:
            ref = ImageTk.PhotoImage(img)
        except Exception:
            return None
        self._ui_icon_refs.append(ref)
        return ref

    def _create_play_icon(self) -> tk.PhotoImage | None:
        try:
            from PIL import Image, ImageDraw, ImageTk
        except Exception:
            return None

        size = 18
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.polygon([(6, 4), (6, 14), (15, 9)], fill="#22c55e")
        try:
            ref = ImageTk.PhotoImage(img)
        except Exception:
            return None
        self._ui_icon_refs.append(ref)
        return ref

    def _create_stop_icon(self) -> tk.PhotoImage | None:
        try:
            from PIL import Image, ImageDraw, ImageTk
        except Exception:
            return None

        size = 18
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rectangle([5, 5, 13, 13], fill="#ef4444")
        try:
            ref = ImageTk.PhotoImage(img)
        except Exception:
            return None
        self._ui_icon_refs.append(ref)
        return ref

    def _set_icon(self) -> None:
        for base in self._asset_dirs():
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

    def _on_summary_frame_configure(self, event: tk.Event) -> None:
        wrap = max(event.width - 4, 120)
        try:
            self.list_summary_label.configure(wraplength=wrap)
        except tk.TclError:
            pass

    def _on_help_tab_configure(self, event: tk.Event) -> None:
        wrap = max(event.width - 140, 160)
        try:
            self.help_note_label.configure(wraplength=wrap)
            for _key_lbl, desc_lbl in self._help_row_widgets:
                desc_lbl.configure(wraplength=wrap)
        except tk.TclError:
            pass

    def _update_list_summary(self) -> None:
        count = len(self.files)
        if count == 0:
            self.list_summary_label.configure(text=self._t("list_summary_empty"))
            return

        info_parts = [self._file_count_label(count)]
        known = [p for p in self.files if p.resolve() in self._file_durations]
        if len(known) == count:
            total_seconds = sum(self._file_durations[p.resolve()] for p in self.files)
            if total_seconds > 0:
                info_parts.append(self._format_duration(total_seconds))

        lines = [", ".join(info_parts)]

        input_bytes, output_bytes = estimate_conversion_sizes(
            self.files,
            self._file_durations,
            self._conversion_options(),
        )
        if input_bytes > 0 and output_bytes > 0:
            lines.append(
                self._t(
                    "list_summary_size_estimate",
                    before=format_byte_size(input_bytes),
                    after=format_byte_size(output_bytes),
                )
            )

        self.list_summary_label.configure(text="\n".join(lines))

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

    def _output_dir_path(self) -> Path:
        return Path(self.output_dir.get().strip() or Path.cwd() / "converted")

    def _pick_output_dir(self) -> None:
        selected = filedialog.askdirectory(initialdir=self.output_dir.get() or str(Path.cwd()))
        if selected:
            self.output_dir.set(selected)

    def _open_output_dir(self) -> None:
        out_dir = self._output_dir_path()
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            os.startfile(str(out_dir))
        except OSError:
            messagebox.showerror(
                self._t("error_title"),
                self._t("open_folder_failed", path=str(out_dir)),
            )

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

    def _on_converter_tab_active(self) -> bool:
        try:
            return self.notebook.index(self.notebook.select()) == 0
        except tk.TclError:
            return False

    def _bind_converter_space_override(self, *buttons: ttk.Button) -> None:
        def _on_button_space(_event: tk.Event) -> str | None:
            if self.grab_current() is not None or self.is_converting or not self._on_converter_tab_active():
                return None
            self._toggle_playback()
            return "break"

        for button in buttons:
            button.bind("<KeyPress-space>", _on_button_space)

    def _release_combobox_focus(self, combo: ttk.Combobox) -> None:
        def _clear() -> None:
            try:
                combo.selection_clear()
            except tk.TclError:
                pass
            if self.focus_get() == combo:
                self.focus_set()

        self.after_idle(_clear)

    def _on_delete_key(self, event: tk.Event) -> str | None:
        if self.grab_current() is not None or self.is_converting or not self._on_converter_tab_active():
            return None
        focus = self.focus_get()
        if isinstance(focus, tk.Text) and str(focus.cget("state")) == "normal":
            return None
        if not self.file_list.get_selected_paths():
            return None
        self._remove_selected()
        return "break"

    def _on_escape_key(self, event: tk.Event) -> str | None:
        if self.grab_current() is not None or self.is_converting or not self._on_converter_tab_active():
            return None
        if self._player.is_playing():
            self._stop_playback(log=True)
            return "break"
        if not self.file_list.get_selected_paths():
            return None
        self.file_list.clear_selection()
        return "break"

    def _on_space_key(self, event: tk.Event) -> str | None:
        if self.grab_current() is not None or self.is_converting or not self._on_converter_tab_active():
            return None
        focus = self.focus_get()
        if isinstance(focus, tk.Text) and str(focus.cget("state")) == "normal":
            return None
        widget_class = focus.winfo_class() if focus is not None else ""
        if widget_class in {"TEntry", "TCombobox"}:
            return None
        self._toggle_playback()
        return "break"

    def _select_all(self, _event: tk.Event = None) -> str:
        self.file_list.select_all()
        return "break"

    def _remove_selected(self) -> None:
        selected = self.file_list.get_selected_paths()
        if not selected:
            return
        if self._player.is_playing() and any(
            self._player.is_playing(path) for path in selected
        ):
            self._stop_playback(log=False)
        to_remove = {path.resolve() for path in selected}
        self.files = [path for path in self.files if path.resolve() not in to_remove]
        for resolved in to_remove:
            self._file_durations.pop(resolved, None)
        self._refresh_file_list()
        self._log(self._t("log_removed_files", count=len(selected)))
        self._update_list_summary()

    def _clear_list(self) -> None:
        if self.files:
            self._stop_playback(log=False)
            self.files.clear()
            self._file_durations.clear()
            self._refresh_file_list()
            self._log(self._t("log_list_cleared"))
            self._update_list_summary()

    # ── Conversion ─────────────────────────────────────────────────────────────

    def _check_ffmpeg(self) -> None:
        if self.ffmpeg_path:
            self._log(self._t("ffmpeg_found", path=self.ffmpeg_path))
        else:
            self._log(self._t("ffmpeg_missing_log"))
            messagebox.showwarning(self._t("ffmpeg_missing_title"), self._t("ffmpeg_missing_message"))
        if not self.ffplay_path:
            if self._player.can_play:
                self._log(self._t("ffplay_fallback_log"))
            else:
                self._log(self._t("ffplay_missing_log"))
        self._update_play_controls()

    def _playback_target(self, path: Path | None = None) -> Path | None:
        if path is not None:
            return path
        selected = self.file_list.get_selected_paths()
        if not selected:
            return None
        return selected[0]

    def _stop_playback(self, *, log: bool) -> None:
        if self._playback_poll_id is not None:
            self.after_cancel(self._playback_poll_id)
            self._playback_poll_id = None
        was_playing = self._player.is_playing()
        self._player.stop()
        self.file_list.set_playing_path(None)
        self._update_play_controls()
        if log and was_playing:
            self._log(self._t("log_playback_stopped"))

    def _toggle_playback(self, path: Path | None = None) -> None:
        if self.is_converting:
            return
        target = self._playback_target(path)
        if self._player.is_playing():
            current = self._player.current_path
            if target is None or (
                current is not None and target.resolve() == current.resolve()
            ):
                self._stop_playback(log=True)
                return
            self._stop_playback(log=False)
        if not self._player.can_play:
            messagebox.showerror(self._t("error_title"), self._t("playback_unavailable_short"))
            return
        if target is None:
            messagebox.showinfo(self._t("play_no_selection_title"), self._t("play_no_selection_message"))
            return
        if not self._player.play(target):
            messagebox.showerror(self._t("error_title"), self._t("log_play_error", name=target.name))
            return
        self.file_list.set_playing_path(target)
        self._log(self._t("log_playing", name=target.name))
        self._update_play_controls()
        self._schedule_playback_poll()

    def _schedule_playback_poll(self) -> None:
        if self._playback_poll_id is not None:
            self.after_cancel(self._playback_poll_id)
        self._playback_poll_id = self.after(200, self._poll_playback)

    def _poll_playback(self) -> None:
        self._playback_poll_id = None
        if self._player.is_playing():
            self._schedule_playback_poll()
            return
        self.file_list.set_playing_path(None)
        self._update_play_controls()

    def _update_play_controls(self) -> None:
        playing = self._player.is_playing()
        can_start = self._player.can_play and bool(self.file_list.get_selected_paths())

        if playing:
            state = tk.NORMAL
            tooltip_key = "tooltip_stop"
            icon = self._stop_icon
            fallback_text = self._t("stop_button")
        elif can_start:
            state = tk.NORMAL
            tooltip_key = "tooltip_play"
            icon = self._play_icon
            fallback_text = self._t("play_button")
        else:
            state = tk.DISABLED
            tooltip_key = "tooltip_play"
            icon = self._play_icon
            fallback_text = self._t("play_button")

        try:
            if icon is not None:
                self.play_btn.configure(image=icon, text="", state=state)
            else:
                self.play_btn.configure(text=fallback_text, state=state)
        except tk.TclError:
            pass

        for tip in self._tooltips.get("tooltip_play", []):
            tip.set_text(self._t(tooltip_key))

    def _on_close(self) -> None:
        self._stop_playback(log=False)
        self.destroy()

    def _start_conversion(self) -> None:
        if self.is_converting:
            return
        if not self.files:
            messagebox.showinfo(self._t("no_files_title"), self._t("no_files_message"))
            return
        if not self.ffmpeg_path:
            messagebox.showerror(self._t("error_title"), self._t("ffmpeg_not_found_short"))
            return

        out_dir = self._output_dir_path()
        out_dir.mkdir(parents=True, exist_ok=True)

        self._stop_playback(log=False)
        self.is_converting = True
        self._cancel_event.clear()
        self.progress_bar["value"] = 0
        self.progress_bar["maximum"] = len(self.files)
        self.progress_label.configure(text="")
        self.progress_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(4, 8), before=self.buttons_frame)
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
                self._cancel_event,
            ),
            daemon=True,
        ).start()

    def _cancel_conversion(self) -> None:
        if not self.is_converting:
            return
        self._cancel_event.set()
        self._conflict_choice = "skip"
        self._conflict_event.set()
        self.cancel_btn.configure(state=tk.DISABLED)
        self._log(self._t("log_cancelling"))

    def _resolve_conflict(self, src: Path, target: Path) -> str:
        if self._cancel_event.is_set():
            return "skip"
        if self._conflict_apply_all:
            return self._conflict_apply_all

        self._conflict_src = src
        self._conflict_target = target
        self._conflict_event.clear()
        self.after(0, self._show_conflict_dialog)
        self._conflict_event.wait()
        return self._conflict_choice

    def _release_busy(self) -> None:
        if self.is_converting:
            self._set_ui_locked(False, swap_convert=False)

    def _restore_busy(self) -> None:
        if self.is_converting:
            self._set_ui_locked(True, swap_convert=False)

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

    def _format_size_summary(self, input_bytes: int, output_bytes: int) -> str | None:
        if input_bytes <= 0 or output_bytes <= 0:
            return None
        before = format_byte_size(input_bytes)
        after = format_byte_size(output_bytes)
        if output_bytes < input_bytes:
            percent = round((1 - output_bytes / input_bytes) * 100)
            change = self._t("done_size_saved", percent=percent)
        elif output_bytes > input_bytes:
            percent = round((output_bytes / input_bytes - 1) * 100)
            change = self._t("done_size_grew", percent=percent)
        else:
            change = self._t("done_size_same")
        return self._t("done_size_summary", before=before, after=after, change=change)

    def _parse_conversion_result(self, parts: list[str]) -> tuple[int, int, int, int, int]:
        ok = int(parts[1])
        failed = int(parts[2])
        skipped = int(parts[3]) if len(parts) > 3 else 0
        input_bytes = int(parts[4]) if len(parts) > 4 else 0
        output_bytes = int(parts[5]) if len(parts) > 5 else 0
        return ok, failed, skipped, input_bytes, output_bytes

    def _format_cancelled_message(self, ok: int, failed: int, skipped: int = 0) -> str:
        message = self._t("log_cancelled", ok=ok, failed=failed)
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
                current_i = int(current)
                total_i = int(total)
                self.progress_bar["maximum"] = max(total_i, 1)
                self.progress_bar["value"] = current_i
                self.progress_label.configure(
                    text=f"{name}  ({current_i}/{total_i})"
                )
            elif message.startswith("DONE::"):
                parts = message.split("::")
                ok, failed, skipped, input_bytes, output_bytes = self._parse_conversion_result(parts)
                self._log(self._format_done_message(ok, failed, skipped))
                size_summary = self._format_size_summary(input_bytes, output_bytes)
                if size_summary:
                    self._log(size_summary)
                self._finish_conversion(
                    play_sound=True,
                    show_dialog=True,
                    ok=ok,
                    failed=failed,
                    skipped=skipped,
                    input_bytes=input_bytes,
                    output_bytes=output_bytes,
                )
            elif message.startswith("CANCELLED::"):
                parts = message.split("::")
                ok, failed, skipped, input_bytes, output_bytes = self._parse_conversion_result(parts)
                self._log(self._format_cancelled_message(ok, failed, skipped))
                self._finish_conversion(play_sound=False, show_dialog=False)
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

    def _finish_conversion(
        self,
        *,
        play_sound: bool,
        show_dialog: bool,
        ok: int = 0,
        failed: int = 0,
        skipped: int = 0,
        input_bytes: int = 0,
        output_bytes: int = 0,
    ) -> None:
        self.is_converting = False
        self.progress_frame.pack_forget()
        self._set_ui_locked(False)
        if play_sound:
            self._play_completion_sound()
        if show_dialog:
            self._show_done_dialog(ok, failed, skipped, input_bytes, output_bytes)

    def _set_ui_locked(self, locked: bool, *, swap_convert: bool = True) -> None:
        state = tk.DISABLED if locked else tk.NORMAL
        for widget in (
            self.add_files_btn,
            self.remove_selected_btn,
            self.clear_list_btn,
            self.play_btn,
            self.choose_output_btn,
            self.quality_combo,
            self.channels_combo,
            self.sample_rate_combo,
        ):
            try:
                widget.configure(state=state)
            except tk.TclError:
                pass
        if swap_convert:
            if locked:
                self.convert_btn.pack_forget()
                self.cancel_btn.pack(side=tk.RIGHT)
                try:
                    self.cancel_btn.configure(state=tk.NORMAL)
                except tk.TclError:
                    pass
            else:
                self.cancel_btn.pack_forget()
                self.convert_btn.pack(side=tk.RIGHT)
                try:
                    self.convert_btn.configure(state=tk.NORMAL)
                except tk.TclError:
                    pass
        if not locked:
            for combo in (self.quality_combo, self.channels_combo, self.sample_rate_combo):
                try:
                    combo.configure(state="readonly")
                except tk.TclError:
                    pass
        self._update_play_controls()

    def _show_done_dialog(
        self,
        ok: int,
        failed: int,
        skipped: int = 0,
        input_bytes: int = 0,
        output_bytes: int = 0,
    ) -> None:
        out_dir = self._output_dir_path()

        dlg = tk.Toplevel(self)
        dlg.title(self._t("done_title"))
        dlg.resizable(False, False)
        dlg.transient(self)
        dlg.grab_set()

        summary = ttk.Frame(dlg, padding=(24, 20, 24, 12))
        summary.pack()

        ttk.Label(
            summary,
            text=self._format_done_message(ok, failed, skipped),
            font=("", 10),
        ).pack(anchor=tk.W)

        size_summary = self._format_size_summary(input_bytes, output_bytes)
        if size_summary:
            ttk.Label(
                summary,
                text=size_summary,
                font=("", 9),
                foreground=self._theme.muted,
            ).pack(anchor=tk.W, pady=(8, 0))

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
