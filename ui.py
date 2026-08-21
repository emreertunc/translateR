"""
UI helper layer with non-TUI fallbacks.

Item #4 (advanced TUI) is intentionally skipped.
"""

import builtins
from contextlib import contextmanager
from typing import Callable, Iterator, List, Optional

try:
    import readline as _readline
except ImportError:  # pragma: no cover - unavailable on some platforms
    pass
else:
    # Load-bearing: readline bypasses POSIX MAX_CANON for long pasted lines.
    # Do not retain API keys or other prompt values in process history.
    _readline.set_auto_history(False)


class MainMenuRequested(BaseException):
    """Raised when the user requests returning to the main menu."""


class QuitRequested(BaseException):
    """Raised when the user requests exiting the application."""


MENU_COMMANDS = {"m", "menu", "main menu", "ana menu", "ana menü"}
QUIT_COMMANDS = {"q", "quit", "exit"}
NAVIGATION_FOOTER = "[m] main menu  [q] quit"


def _normalize_command(value: str) -> str:
    return " ".join(value.strip().lower().split())


class NavigationInput:
    """Input wrapper that recognizes global navigation commands."""

    def __init__(self, raw_input: Callable[[str], str]):
        self.raw_input = raw_input

    def __call__(self, prompt: str = "") -> str:
        if prompt:
            print(NAVIGATION_FOOTER)
            print()
        value = self.raw_input(prompt)
        command = _normalize_command(value)
        if command in MENU_COMMANDS:
            raise MainMenuRequested()
        if command in QUIT_COMMANDS:
            raise QuitRequested()
        return value


@contextmanager
def global_navigation_input() -> Iterator[None]:
    original_input = builtins.input
    builtins.input = NavigationInput(original_input)
    try:
        yield
    finally:
        builtins.input = original_input


class UI:
    """Simple UI adapter used by workflows."""

    def available(self) -> bool:
        """TUI is intentionally disabled in this implementation."""
        return False

    def select(self, _message: str, _choices: List[dict], add_back: bool = False) -> Optional[str]:
        return None

    def checkbox(self, _message: str, _choices: List[dict], add_back: bool = False) -> Optional[List[str]]:
        return None

    def confirm(self, _message: str, _default: bool = True) -> Optional[bool]:
        return None

    def text(self, _message: str) -> Optional[str]:
        return None

    def editor(self, _message: str, _default: str = "") -> Optional[str]:
        return None

    def prompt_multiline(self, prompt: str, initial: str = "") -> Optional[str]:
        print(prompt)
        if initial:
            print("(Initial text shown below; edit and re-enter if needed)")
            print("-" * 40)
            print(initial)
            print("-" * 40)
        print(
            "Enter text. Finish with a line containing only 'EOF'. "
            "Use ':menu' for the main menu or ':q' to quit."
        )
        lines: List[str] = []
        reader = builtins.input
        if isinstance(reader, NavigationInput):
            reader = reader.raw_input
        while True:
            try:
                line = reader()
            except EOFError:
                break
            command = _normalize_command(line)
            if command in (":m", ":menu"):
                raise MainMenuRequested()
            if command in (":q", ":quit"):
                raise QuitRequested()
            if line.strip() == "EOF":
                break
            lines.append(line)
        text = "\n".join(lines).strip()
        return text if text else None

    def prompt_app_id(self, asc_client) -> Optional[str]:
        """Show app list and allow selecting by number or direct App ID input."""
        try:
            response = asc_client.get_apps()
            apps = response.get("data", [])
        except Exception:
            apps = []

        if apps:
            print()
            print("Available Apps:")
            for i, app in enumerate(apps, 1):
                attrs = app.get("attributes", {})
                app_name = attrs.get("name", "Unknown")
                print(f"{i}. {app_name}")
            print()
            raw = input("Select app (number) or enter App ID: ").strip()
            if raw.isdigit():
                idx = int(raw)
                if 1 <= idx <= len(apps):
                    return apps[idx - 1].get("id")
                return None
            return raw or None

        app_id = input("Enter your App ID: ").strip()
        return app_id or None
