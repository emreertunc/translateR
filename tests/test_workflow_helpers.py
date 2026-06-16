import io
import unittest
from unittest.mock import patch

from workflows.helpers import display_locale_table


class WorkflowHelperTests(unittest.TestCase):
    def test_display_locale_table_prints_all_locales(self):
        locales = {f"l-{index}": f"Language {index}" for index in range(1, 24)}
        output = io.StringIO()

        with patch("sys.stdout", output):
            display_locale_table(locales)

        rendered = output.getvalue()
        self.assertIn("l-1", rendered)
        self.assertIn("Language 23", rendered)
        self.assertNotIn("more", rendered)


if __name__ == "__main__":
    unittest.main()
