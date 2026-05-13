import builtins
import io
import unittest
from unittest.mock import patch

from ui import (
    MainMenuRequested,
    NavigationInput,
    QuitRequested,
    global_navigation_input,
)


class NavigationInputTests(unittest.TestCase):
    def test_normal_input_returns_value_and_prints_shortcuts_above_prompt(self):
        prompts = []
        output = io.StringIO()
        nav = NavigationInput(lambda prompt: prompts.append(prompt) or "hello")

        with patch("sys.stdout", output):
            result = nav("Select an option (1-14): ")

        self.assertEqual(result, "hello")
        self.assertEqual(prompts, ["Select an option (1-14): "])
        self.assertEqual(output.getvalue(), "[m] main menu  [q] quit\n\n")

    def test_empty_prompt_stays_empty(self):
        prompts = []
        nav = NavigationInput(lambda prompt: prompts.append(prompt) or "hello")

        result = nav("")

        self.assertEqual(result, "hello")
        self.assertEqual(prompts, [""])

    def test_shortcuts_print_once_per_prompt(self):
        prompts = []
        output = io.StringIO()
        nav = NavigationInput(lambda prompt: prompts.append(prompt) or "hello")

        with patch("sys.stdout", output):
            result = nav("Choice: ")

        self.assertEqual(result, "hello")
        self.assertEqual(prompts, ["Choice: "])
        self.assertEqual(output.getvalue(), "[m] main menu  [q] quit\n\n")

    def test_menu_aliases(self):
        for alias in ("m", "menu", "main menu", "ana menu", "ana menü"):
            with self.subTest(alias=alias):
                nav = NavigationInput(lambda prompt: alias)
                with patch("sys.stdout", io.StringIO()):
                    with self.assertRaises(MainMenuRequested):
                        nav("Select: ")

    def test_quit_aliases(self):
        for alias in ("q", "quit", "exit"):
            with self.subTest(alias=alias):
                nav = NavigationInput(lambda prompt: alias)
                with patch("sys.stdout", io.StringIO()):
                    with self.assertRaises(QuitRequested):
                        nav("Select: ")

    def test_whitespace_and_case_are_normalized(self):
        nav = NavigationInput(lambda prompt: "  MAIN MENU  ")
        with patch("sys.stdout", io.StringIO()):
            with self.assertRaises(MainMenuRequested):
                nav("Select: ")

        nav = NavigationInput(lambda prompt: "\tQ\n")
        with patch("sys.stdout", io.StringIO()):
            with self.assertRaises(QuitRequested):
                nav("Select: ")

    def test_global_navigation_context_restores_input(self):
        original_input = builtins.input

        with patch.object(builtins, "input", lambda prompt="": "ok"):
            patched_input = builtins.input
            with global_navigation_input():
                self.assertIsInstance(builtins.input, NavigationInput)
                with patch("sys.stdout", io.StringIO()):
                    self.assertEqual(builtins.input("Select: "), "ok")
            self.assertIs(builtins.input, patched_input)

        self.assertIs(builtins.input, original_input)


if __name__ == "__main__":
    unittest.main()
