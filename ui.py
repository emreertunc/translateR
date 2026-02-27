"""
UI helper layer with non-TUI fallbacks.

Item #4 (advanced TUI) is intentionally skipped.
"""

from typing import List, Optional


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
        print("Enter text. Finish with a line containing only 'EOF'.")
        lines: List[str] = []
        while True:
            try:
                line = input()
            except EOFError:
                break
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
