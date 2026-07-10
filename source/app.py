import os
import queue
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from tkinterdnd2 import DND_FILES, TkinterDnD

from .constants import __version__, LANGUAGE_OPTIONS, TRANSLATIONS
from . import changelog
from .converter import filter_audio_files, resolve_ffmpeg_path, run_conversion
from . import settings


class OggConverterApp(TkinterDnD.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.geometry("760x520")
        self.minsize(700, 440)

        self.files: list[Path] = []
        self.log_queue: "queue.Queue[str]" = queue.Queue()
        self.is_converting = False
        self.ffmpeg_path = resolve_ffmpeg_path()
        self._prefs = settings.load()

        self.language = self._prefs.get("language", "en")
        lang_name = next((k for k, v in LANGUAGE_OPTIONS.items() if v == self.language), "English")
        self.language_var = tk.StringVar(value=lang_name)

        default_out = str(Path.cwd() / "converted")
        self.output_dir = tk.StringVar(value=self._prefs.get("output_dir") or default_out)
        self.output_dir.trace_add("write", self._on_output_dir_changed)

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

        ver_lbl = ttk.Label(root, text=f"v{__version__}", foreground="gray", font=("", 8), cursor="hand2")
        ver_lbl.pack(anchor=tk.SE, pady=(2, 0))
        ver_lbl.bind("<Button-1>", lambda _e: self._show_changelog())

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

    def _build_converter_tab(self) -> None:
        top_bar = ttk.Frame(self.converter_tab)
        top_bar.pack(fill=tk.X, pady=(0, 10))

        self.output_label = ttk.Label(top_bar)
        self.output_label.pack(side=tk.LEFT)

        style = ttk.Style()
        style.configure("Readonly.TEntry", foreground="gray")
        ttk.Entry(
            top_bar,
            textvariable=self.output_dir,
            state="readonly",
            style="Readonly.TEntry",
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)

        self.choose_output_btn = ttk.Button(top_bar, command=self._pick_output_dir)
        self.choose_output_btn.pack(side=tk.LEFT)

        self.drop_frame = ttk.LabelFrame(self.converter_tab)
        self.drop_frame.pack(fill=tk.BOTH, expand=True)

        self.listbox = tk.Listbox(self.drop_frame, selectmode=tk.EXTENDED, activestyle="none")
        self.listbox.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.listbox.drop_target_register(DND_FILES)
        self.listbox.dnd_bind("<<Drop>>", self._on_drop)
        self.listbox.bind("<Delete>", lambda _e: self._remove_selected())
        self.listbox.bind("<Escape>", lambda _e: self.listbox.selection_clear(0, tk.END))

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

    def _save_settings(self) -> None:
        self._prefs["language"] = self.language
        self._prefs["output_dir"] = self.output_dir.get()
        settings.save(self._prefs)

    def _apply_language(self) -> None:
        self.title(self._t("window_title"))
        self.notebook.tab(0, text=self._t("tab_converter"))
        self.notebook.tab(1, text=self._t("tab_log"))
        self.notebook.tab(2, text=self._t("tab_settings"))
        self.notebook.tab(3, text=self._t("tab_help"))
        self.settings_frame.configure(text=self._t("settings_frame_title"))
        self.language_label.configure(text=self._t("language_label"))
        self.output_label.configure(text=self._t("output_dir_label"))
        self.choose_output_btn.configure(text=self._t("choose_button"))
        self.drop_frame.configure(text=self._t("drop_frame_title"))
        self.add_files_btn.configure(text=self._t("add_files_button"))
        self.remove_selected_btn.configure(text=self._t("remove_selected_button"))
        self.clear_list_btn.configure(text=self._t("clear_list_button"))
        self.convert_btn.configure(text=self._t("convert_button"))
        self.help_shortcuts_label.configure(text=self._t("help_shortcuts_title"))
        for (key_lbl, desc_lbl), (key, desc) in zip(
            self._help_row_widgets, self._t("help_shortcuts")
        ):
            key_lbl.configure(text=key)
            desc_lbl.configure(text=desc)
        self.help_note_label.configure(text=self._t("help_note"))
        self.changelog_btn.configure(text=self._t("changelog_button"))

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
        existing = {p.resolve() for p in self.files}
        accepted, skipped = filter_audio_files(paths, existing)
        for p in accepted:
            self.files.append(p)
            self.listbox.insert(tk.END, str(p))
        if accepted:
            self._log(self._t("log_added_files", count=len(accepted)))
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
        self.listbox.selection_set(0, tk.END)
        return "break"

    def _remove_selected(self) -> None:
        indexes = list(self.listbox.curselection())
        for i in reversed(indexes):
            del self.files[i]
            self.listbox.delete(i)
        if indexes:
            self._log(self._t("log_removed_files", count=len(indexes)))

    def _clear_list(self) -> None:
        if self.files:
            self.files.clear()
            self.listbox.delete(0, tk.END)
            self._log(self._t("log_list_cleared"))

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

        threading.Thread(
            target=run_conversion,
            args=(self.ffmpeg_path, list(self.files), out_dir, self.log_queue, self._t),
            daemon=True,
        ).start()

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
                _, ok, failed = message.split("::")
                ok, failed = int(ok), int(failed)
                self._log(self._t("log_done", ok=ok, failed=failed))
                self.is_converting = False
                self.progress_frame.pack_forget()
                self._set_ui_locked(False)
                self._show_done_dialog(ok, failed)
            else:
                self._log(message)
        self.after(120, self._drain_log_queue)

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

    def _show_done_dialog(self, ok: int, failed: int) -> None:
        out_dir = Path(self.output_dir.get().strip())

        dlg = tk.Toplevel(self)
        dlg.title(self._t("done_title"))
        dlg.resizable(False, False)
        dlg.transient(self)
        dlg.grab_set()

        ttk.Label(
            dlg,
            text=self._t("log_done", ok=ok, failed=failed),
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
