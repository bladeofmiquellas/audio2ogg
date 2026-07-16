from .app import OggConverterApp
from .platform_win import enable_dpi_awareness


def main() -> None:
    enable_dpi_awareness()
    app = OggConverterApp()
    app.mainloop()


if __name__ == "__main__":
    main()
