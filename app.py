import queue
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from tkinterdnd2 import DND_FILES, TkinterDnD


AUDIO_EXTENSIONS = {
    ".aac",
    ".aiff",
    ".alac",
    ".amr",
    ".ape",
    ".au",
    ".flac",
    ".m4a",
    ".m4b",
    ".mid",
    ".midi",
    ".mp2",
    ".mp3",
    ".ogg",
    ".opus",
    ".ra",
    ".wav",
    ".wma",
}

LANGUAGE_OPTIONS = {
    "English": "en",
    "Russian": "ru",
    "中文": "zh",
}

TRANSLATIONS = {
    "en": {
        "window_title": "audio2ogg",
        "tab_converter": "Converter",
        "tab_log": "Log",
        "tab_settings": "Settings",
        "settings_frame_title": "Application settings",
        "language_label": "Language:",
        "output_dir_label": "Output folder:",
        "choose_button": "Choose...",
        "drop_frame_title": "Drag and drop audio files here",
        "add_files_button": "Add files",
        "remove_selected_button": "Remove selected",
        "clear_list_button": "Clear list",
        "convert_button": "Convert to OGG",
        "log_frame_title": "Log",
        "ffmpeg_found": "ffmpeg found: {path}",
        "ffmpeg_missing_log": "ffmpeg not found (neither bundled nor in PATH).",
        "ffmpeg_missing_title": "ffmpeg not found",
        "ffmpeg_missing_message": (
            "Could not find ffmpeg executable.\n\n"
            "For portable builds ffmpeg must be embedded in the app.\n"
            "For development runs install ffmpeg and add it to PATH."
        ),
        "pick_audio_title": "Select audio files",
        "audio_files_filter": "Audio files",
        "log_added_files": "Added files: {count}",
        "log_skipped_items": "Skipped items: {count}",
        "log_removed_files": "Removed files: {count}",
        "log_list_cleared": "List cleared.",
        "no_files_title": "No files",
        "no_files_message": "Add files before conversion.",
        "error_title": "Error",
        "ffmpeg_not_found_short": "ffmpeg not found (neither bundled nor in PATH).",
        "log_start_conversion": "Starting conversion. Files: {count}",
        "log_converting": "Converting: {src} -> {dst}",
        "log_ok": "OK: {name}",
        "log_error_unknown": "Unknown ffmpeg error.",
        "log_error": "ERROR: {name} | {err}",
        "log_done": "Done. Successful: {ok}, failed: {failed}",
        "language_switched": "Language switched to English.",
        "tab_help": "Help",
        "help_shortcuts_title": "Keyboard shortcuts",
        "help_shortcuts": [
            ("Ctrl+O",     "Add files"),
            ("Ctrl+A",     "Select all in list"),
            ("Delete",     "Remove selected"),
            ("Escape",     "Deselect all"),
            ("Ctrl+Enter", "Start conversion"),
            ("Ctrl+L",     "Clear list"),
        ],
        "help_note": "Shortcuts work regardless of keyboard layout.",
    },
    "ru": {
        "window_title": "audio2ogg",
        "tab_converter": "Конвертер",
        "tab_log": "Лог",
        "tab_settings": "Настройки",
        "settings_frame_title": "Настройки приложения",
        "language_label": "Язык:",
        "output_dir_label": "Папка экспорта:",
        "choose_button": "Выбрать...",
        "drop_frame_title": "Перетащите аудиофайлы сюда",
        "add_files_button": "Добавить файлы",
        "remove_selected_button": "Удалить выбранные",
        "clear_list_button": "Очистить список",
        "convert_button": "Конвертировать в OGG",
        "log_frame_title": "Лог",
        "ffmpeg_found": "ffmpeg найден: {path}",
        "ffmpeg_missing_log": "ffmpeg не найден (ни встроенный, ни в PATH).",
        "ffmpeg_missing_title": "ffmpeg не найден",
        "ffmpeg_missing_message": (
            "Не найден исполняемый файл ffmpeg.\n\n"
            "Для portable-версии ffmpeg должен быть встроен в сборку.\n"
            "Для dev-запуска установите ffmpeg и добавьте его в PATH."
        ),
        "pick_audio_title": "Выберите аудиофайлы",
        "audio_files_filter": "Аудиофайлы",
        "log_added_files": "Добавлено файлов: {count}",
        "log_skipped_items": "Пропущено элементов: {count}",
        "log_removed_files": "Удалено файлов: {count}",
        "log_list_cleared": "Список очищен.",
        "no_files_title": "Нет файлов",
        "no_files_message": "Сначала добавьте файлы для конвертации.",
        "error_title": "Ошибка",
        "ffmpeg_not_found_short": "ffmpeg не найден (ни встроенный, ни в PATH).",
        "log_start_conversion": "Запуск конвертации. Файлов: {count}",
        "log_converting": "Конвертация: {src} -> {dst}",
        "log_ok": "OK: {name}",
        "log_error_unknown": "Неизвестная ошибка ffmpeg.",
        "log_error": "ERROR: {name} | {err}",
        "log_done": "Готово. Успешно: {ok}, с ошибками: {failed}",
        "language_switched": "Язык переключен на русский.",
        "tab_help": "Справка",
        "help_shortcuts_title": "Горячие клавиши",
        "help_shortcuts": [
            ("Ctrl+O",     "Добавить файлы"),
            ("Ctrl+A",     "Выделить все в списке"),
            ("Delete",     "Удалить выделенные"),
            ("Escape",     "Снять выделение"),
            ("Ctrl+Enter", "Запустить конвертацию"),
            ("Ctrl+L",     "Очистить список"),
        ],
        "help_note": "Горячие клавиши работают на любой раскладке.",
    },
    "zh": {
        "window_title": "audio2ogg",
        "tab_converter": "转换器",
        "tab_log": "日志",
        "tab_settings": "设置",
        "settings_frame_title": "应用设置",
        "language_label": "语言：",
        "output_dir_label": "输出文件夹：",
        "choose_button": "选择...",
        "drop_frame_title": "将音频文件拖放到此处",
        "add_files_button": "添加文件",
        "remove_selected_button": "删除所选",
        "clear_list_button": "清空列表",
        "convert_button": "转换为 OGG",
        "log_frame_title": "日志",
        "ffmpeg_found": "已找到 ffmpeg：{path}",
        "ffmpeg_missing_log": "未找到 ffmpeg（既无内置版本，也不在 PATH 中）。",
        "ffmpeg_missing_title": "未找到 ffmpeg",
        "ffmpeg_missing_message": (
            "找不到 ffmpeg 可执行文件。\n\n"
            "便携版应用需要将 ffmpeg 内置于程序中。\n"
            "开发模式下请安装 ffmpeg 并将其添加到 PATH。"
        ),
        "pick_audio_title": "选择音频文件",
        "audio_files_filter": "音频文件",
        "log_added_files": "已添加文件：{count}",
        "log_skipped_items": "已跳过项目：{count}",
        "log_removed_files": "已删除文件：{count}",
        "log_list_cleared": "列表已清空。",
        "no_files_title": "无文件",
        "no_files_message": "请先添加要转换的文件。",
        "error_title": "错误",
        "ffmpeg_not_found_short": "未找到 ffmpeg（既无内置版本，也不在 PATH 中）。",
        "log_start_conversion": "开始转换，文件数：{count}",
        "log_converting": "正在转换：{src} -> {dst}",
        "log_ok": "成功：{name}",
        "log_error_unknown": "未知的 ffmpeg 错误。",
        "log_error": "错误：{name} | {err}",
        "log_done": "完成。成功：{ok}，失败：{failed}",
        "language_switched": "语言已切换为中文。",
        "tab_help": "帮助",
        "help_shortcuts_title": "快捷键",
        "help_shortcuts": [
            ("Ctrl+O",     "添加文件"),
            ("Ctrl+A",     "全选列表"),
            ("Delete",     "删除所选"),
            ("Escape",     "取消选择"),
            ("Ctrl+Enter", "开始转换"),
            ("Ctrl+L",     "清空列表"),
        ],
        "help_note": "快捷键在任何键盘布局下均可使用。",
    },
}


class OggConverterApp(TkinterDnD.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.geometry("760x520")
        self.minsize(700, 440)

        self.files: list[Path] = []
        self.log_queue: "queue.Queue[str]" = queue.Queue()
        self.is_converting = False
        self.ffmpeg_path = self._resolve_ffmpeg_path()
        self.language = "en"
        self.language_var = tk.StringVar(value="English")

        self.output_dir = tk.StringVar(value=str(Path.cwd() / "converted"))

        self._build_ui()
        self._apply_language()
        self._set_icon()
        self._check_ffmpeg()
        self.after(120, self._drain_log_queue)

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=12)
        root.pack(fill=tk.BOTH, expand=True)

        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        self.converter_tab = ttk.Frame(self.notebook, padding=8)
        self.log_tab = ttk.Frame(self.notebook, padding=8)
        self.settings_tab = ttk.Frame(self.notebook, padding=8)
        self.help_tab = ttk.Frame(self.notebook, padding=16)
        self.notebook.add(self.converter_tab)
        self.notebook.add(self.log_tab)
        self.notebook.add(self.settings_tab)
        self.notebook.add(self.help_tab)

        top_bar = ttk.Frame(self.converter_tab)
        top_bar.pack(fill=tk.X, pady=(0, 10))

        self.output_label = ttk.Label(top_bar)
        self.output_label.pack(side=tk.LEFT)

        style = ttk.Style()
        style.configure("Readonly.TEntry", foreground="gray")
        output_entry = ttk.Entry(
            top_bar,
            textvariable=self.output_dir,
            state="readonly",
            style="Readonly.TEntry",
        )
        output_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)

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

        self.add_files_btn = ttk.Button(buttons, command=self._add_files_dialog)
        self.add_files_btn.pack(side=tk.LEFT)
        self.remove_selected_btn = ttk.Button(buttons, command=self._remove_selected)
        self.remove_selected_btn.pack(side=tk.LEFT, padx=8)
        self.clear_list_btn = ttk.Button(buttons, command=self._clear_list)
        self.clear_list_btn.pack(side=tk.LEFT)

        self.convert_btn = ttk.Button(
            buttons,
            command=self._start_conversion,
        )
        self.convert_btn.pack(side=tk.RIGHT)

        self.log_text = tk.Text(self.log_tab, state=tk.DISABLED, wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True)

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

        self.help_shortcuts_label = ttk.Label(
            self.help_tab, font=("", 10, "bold")
        )
        self.help_shortcuts_label.grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 8))

        self._help_row_widgets: list[tuple[ttk.Label, ttk.Label]] = []
        for i in range(6):
            key_lbl = ttk.Label(self.help_tab, font=("Consolas", 10, "bold"), foreground="#444")
            desc_lbl = ttk.Label(self.help_tab, font=("", 10))
            key_lbl.grid(row=i + 1, column=0, sticky=tk.W, padx=(0, 24), pady=2)
            desc_lbl.grid(row=i + 1, column=1, sticky=tk.W, pady=2)
            self._help_row_widgets.append((key_lbl, desc_lbl))

        self.help_note_label = ttk.Label(
            self.help_tab, font=("", 9), foreground="gray"
        )
        self.help_note_label.grid(row=8, column=0, columnspan=2, sticky=tk.W, pady=(16, 0))

    def _check_ffmpeg(self) -> None:
        if self.ffmpeg_path:
            self._log(self._t("ffmpeg_found", path=self.ffmpeg_path))
            return

        self._log(self._t("ffmpeg_missing_log"))
        messagebox.showwarning(
            self._t("ffmpeg_missing_title"),
            self._t("ffmpeg_missing_message"),
        )

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
        dropped_items = self.tk.splitlist(event.data)
        paths = [Path(p) for p in dropped_items]
        self._add_files(paths)

    def _add_files(self, paths: list[Path]) -> None:
        added = 0
        skipped = 0
        existing = {p.resolve() for p in self.files}

        for p in paths:
            if not p.exists() or not p.is_file():
                skipped += 1
                continue
            if p.suffix.lower() not in AUDIO_EXTENSIONS:
                skipped += 1
                continue

            resolved = p.resolve()
            if resolved in existing:
                skipped += 1
                continue

            self.files.append(p)
            existing.add(resolved)
            self.listbox.insert(tk.END, str(p))
            added += 1

        if added:
            self._log(self._t("log_added_files", count=added))
        if skipped:
            self._log(self._t("log_skipped_items", count=skipped))

    _CTRL_HOTKEYS: dict[int, str] = {
        65: "_select_all",       # A
        79: "_add_files_dialog", # O
        76: "_clear_list",       # L
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
        count = len(self.files)
        self.files.clear()
        self.listbox.delete(0, tk.END)
        if count:
            self._log(self._t("log_list_cleared"))

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
        self.convert_btn.configure(state=tk.DISABLED)
        self.notebook.select(1)
        self._log(self._t("log_start_conversion", count=len(self.files)))

        worker = threading.Thread(target=self._convert_worker, args=(list(self.files), out_dir), daemon=True)
        worker.start()

    def _convert_worker(self, files: list[Path], out_dir: Path) -> None:
        ok = 0
        failed = 0

        for src in files:
            dst = self._build_output_path(src, out_dir)
            cmd = [
                str(self.ffmpeg_path),
                "-hide_banner",
                "-y",
                "-i",
                str(src),
                "-vn",
                "-c:a",
                "libvorbis",
                "-q:a",
                "5",
                str(dst),
            ]

            self.log_queue.put(self._t("log_converting", src=src.name, dst=dst.name))
            proc = subprocess.run(cmd, capture_output=True, text=True)
            if proc.returncode == 0:
                ok += 1
                self.log_queue.put(self._t("log_ok", name=dst.name))
            else:
                failed += 1
                err = (proc.stderr or proc.stdout or "").strip()
                short_err = err[-240:] if err else self._t("log_error_unknown")
                self.log_queue.put(self._t("log_error", name=src.name, err=short_err))

        self.log_queue.put(f"DONE::{ok}::{failed}")

    def _build_output_path(self, src: Path, out_dir: Path) -> Path:
        candidate = out_dir / f"{src.stem}.ogg"
        idx = 1
        while candidate.exists():
            candidate = out_dir / f"{src.stem}_{idx}.ogg"
            idx += 1
        return candidate

    def _drain_log_queue(self) -> None:
        while True:
            try:
                message = self.log_queue.get_nowait()
            except queue.Empty:
                break

            if message.startswith("DONE::"):
                _, ok, failed = message.split("::")
                self._log(self._t("log_done", ok=ok, failed=failed))
                self.is_converting = False
                self.convert_btn.configure(state=tk.NORMAL)
                continue

            self._log(message)

        self.after(120, self._drain_log_queue)

    def _log(self, text: str) -> None:
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, text + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _on_language_changed(self, _event: tk.Event) -> None:
        selected = self.language_var.get()
        code = LANGUAGE_OPTIONS.get(selected, "en")
        if code == self.language:
            return
        self.language = code
        self._apply_language()
        self._log(self._t("language_switched"))

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

    def _t(self, key: str, **kwargs: object) -> str:
        template = TRANSLATIONS.get(self.language, TRANSLATIONS["en"]).get(key, key)
        if kwargs:
            return template.format(**kwargs)
        return template

    def _set_icon(self) -> None:
        meipass = getattr(sys, "_MEIPASS", None)
        candidates = []
        if meipass:
            candidates.append(Path(meipass) / "assets" / "icon.ico")
        candidates.append(Path(__file__).resolve().parent / "assets" / "icon.ico")
        for path in candidates:
            if path.exists():
                try:
                    self.iconbitmap(str(path))
                except Exception:
                    pass
                return

    def _resolve_ffmpeg_path(self) -> Path | None:
        # PyInstaller onefile распаковывает ресурсы во временную папку sys._MEIPASS.
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            bundled = Path(meipass) / "ffmpeg" / "ffmpeg.exe"
            if bundled.exists():
                return bundled

        local_bundled = Path(__file__).resolve().parent / "vendor" / "ffmpeg.exe"
        if local_bundled.exists():
            return local_bundled

        ffmpeg_from_path = shutil.which("ffmpeg")
        if ffmpeg_from_path:
            return Path(ffmpeg_from_path)

        return None


def main() -> None:
    app = OggConverterApp()
    app.mainloop()


if __name__ == "__main__":
    main()
