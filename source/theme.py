from dataclasses import dataclass

import tkinter as tk
from tkinter import ttk


@dataclass(frozen=True)
class AppTheme:
    name: str
    window_bg: str
    fg: str
    muted: str
    accent: str
    surface: str
    surface_alt: str
    border: str
    input_bg: str
    input_fg: str
    button_bg: str
    select_bg: str
    list_bg_even: str
    list_bg_odd: str
    list_bg_selected: str
    list_bg_playing: str
    list_fg_name: str
    list_fg_duration: str
    list_fg_pending: str
    list_sep: str
    log_bg: str
    log_fg: str
    tip_bg: str
    tip_fg: str
    tip_border: str
    help_key_fg: str
    progress_trough: str
    progress_bar: str


LIGHT_THEME = AppTheme(
    name="light",
    window_bg="#f0f0f0",
    fg="#1f2937",
    muted="gray",
    accent="#0078d4",
    surface="#ffffff",
    surface_alt="#f6f7f9",
    border="#e8ebf0",
    input_bg="#ffffff",
    input_fg="gray",
    button_bg="#f0f0f0",
    select_bg="#e8f1ff",
    list_bg_even="#ffffff",
    list_bg_odd="#f6f7f9",
    list_bg_selected="#e8f1ff",
    list_bg_playing="#dff5e8",
    list_fg_name="#1f2937",
    list_fg_duration="#6b7280",
    list_fg_pending="#9ca3af",
    list_sep="#e8ebf0",
    log_bg="#ffffff",
    log_fg="#1f2937",
    tip_bg="#ffffff",
    tip_fg="#333333",
    tip_border="#d4d4d4",
    help_key_fg="#444444",
    progress_trough="#e5e7eb",
    progress_bar="#0078d4",
)

DARK_THEME = AppTheme(
    name="dark",
    window_bg="#1e1e1e",
    fg="#e8e8e8",
    muted="#9ca3af",
    accent="#4a90d9",
    surface="#2d2d2d",
    surface_alt="#262626",
    border="#3e3e42",
    input_bg="#3c3c3c",
    input_fg="#d4d4d4",
    button_bg="#3c3c3c",
    select_bg="#264f78",
    list_bg_even="#2d2d2d",
    list_bg_odd="#262626",
    list_bg_selected="#264f78",
    list_bg_playing="#1e3a2f",
    list_fg_name="#e8e8e8",
    list_fg_duration="#9ca3af",
    list_fg_pending="#6b7280",
    list_sep="#3e3e42",
    log_bg="#1e1e1e",
    log_fg="#d4d4d4",
    tip_bg="#2d2d2d",
    tip_fg="#e8e8e8",
    tip_border="#3e3e42",
    help_key_fg="#b0b0b0",
    progress_trough="#3c3c3c",
    progress_bar="#4a90d9",
)

THEMES: dict[str, AppTheme] = {
    "light": LIGHT_THEME,
    "dark": DARK_THEME,
}


def get_theme(name: str) -> AppTheme:
    return THEMES.get(name, LIGHT_THEME)


def apply_ttk_theme(style: ttk.Style, theme: AppTheme) -> None:
    if theme.name == "dark":
        style.theme_use("clam")
    elif "vista" in style.theme_names():
        style.theme_use("vista")
    elif "xpnative" in style.theme_names():
        style.theme_use("xpnative")
    else:
        style.theme_use("clam")

    style.configure(".", background=theme.window_bg, foreground=theme.fg)
    style.configure("TFrame", background=theme.window_bg)
    style.configure("TLabel", background=theme.window_bg, foreground=theme.fg)
    style.configure("TLabelframe", background=theme.window_bg, foreground=theme.fg)
    style.configure("TLabelframe.Label", background=theme.window_bg, foreground=theme.fg)
    style.configure(
        "TButton",
        background=theme.button_bg,
        foreground=theme.fg,
        bordercolor=theme.border,
        lightcolor=theme.button_bg,
        darkcolor=theme.button_bg,
    )
    style.map(
        "TButton",
        background=[("active", theme.surface), ("disabled", theme.surface_alt)],
        foreground=[("disabled", theme.muted)],
    )
    style.configure(
        "TEntry",
        fieldbackground=theme.input_bg,
        foreground=theme.input_fg,
        insertcolor=theme.fg,
        bordercolor=theme.border,
        lightcolor=theme.border,
        darkcolor=theme.border,
    )
    style.configure(
        "Readonly.TEntry",
        fieldbackground=theme.input_bg,
        foreground=theme.input_fg,
        bordercolor=theme.border,
        lightcolor=theme.border,
        darkcolor=theme.border,
    )
    style.configure(
        "TCombobox",
        fieldbackground=theme.input_bg,
        background=theme.button_bg,
        foreground=theme.fg,
        arrowcolor=theme.fg,
        bordercolor=theme.border,
        lightcolor=theme.border,
        darkcolor=theme.border,
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", theme.input_bg)],
        foreground=[("readonly", theme.fg)],
    )
    style.configure("TNotebook", background=theme.window_bg, bordercolor=theme.border)
    style.configure("TNotebook.Tab", background=theme.surface_alt, foreground=theme.fg, padding=(12, 6))
    style.map(
        "TNotebook.Tab",
        background=[("selected", theme.surface)],
        foreground=[("selected", theme.fg)],
    )
    style.configure(
        "Horizontal.TProgressbar",
        troughcolor=theme.progress_trough,
        background=theme.progress_bar,
        bordercolor=theme.border,
        lightcolor=theme.progress_bar,
        darkcolor=theme.progress_bar,
    )
    style.configure(
        "Vertical.TScrollbar",
        background=theme.surface_alt,
        troughcolor=theme.window_bg,
        bordercolor=theme.border,
        arrowcolor=theme.fg,
    )
    style.configure("Icon.TButton", padding=(4, 2))


def apply_root_theme(root: tk.Misc, theme: AppTheme) -> None:
    root.configure(background=theme.window_bg)
