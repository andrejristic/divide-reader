"""Single entry point of the packaged program: no arguments opens the GUI, a command runs the CLI."""
import sys


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] not in ("--gui",):
        from divide_reader.cli import main as cli
        cli()
    else:
        from divide_reader.gui.app import main as gui
        gui()


if __name__ == "__main__":
    main()
