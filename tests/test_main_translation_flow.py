import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, patch

import requests

from main import PartialLocalizationError, TranslateRCLI
from utils import APP_STORE_LOCALES


def localization(locale, localization_id):
    return {"id": localization_id, "attributes": {"locale": locale}}


class TranslationTargetParsingTests(unittest.TestCase):
    def test_existing_locale_and_legacy_alias_are_selectable(self):
        selected, invalid, aliases = TranslateRCLI._parse_target_locale_input(
            "hi-IN,tr,hi",
            ["hi", "tr"],
            [],
        )

        self.assertEqual(selected, ["hi", "tr"])
        self.assertEqual(invalid, [])
        self.assertEqual(aliases, [("hi-IN", "hi")])

    def test_all_selects_only_new_locale_defaults(self):
        selected, invalid, aliases = TranslateRCLI._parse_target_locale_input(
            "all",
            ["de-DE", "tr", "hi"],
            ["tr", "hi"],
        )

        self.assertEqual(selected, ["tr", "hi"])
        self.assertEqual(invalid, [])
        self.assertEqual(aliases, [])


class TranslationModeSelectionTests(unittest.TestCase):
    @patch("main.time.sleep")
    @patch("main.confirm_locale_write", return_value=True)
    @patch("builtins.input", side_effect=["1", "hi-IN", ""])
    def test_metadata_mode_can_retranslate_an_existing_locale(
        self,
        _input_mock,
        _confirm_mock,
        _sleep_mock,
    ):
        cli = TranslateRCLI.__new__(TranslateRCLI)
        cli.asc_client = Mock()
        cli.asc_client.get_latest_app_store_version.return_value = "version-id"
        existing = [
            {
                "id": "version-en",
                "attributes": {"locale": "en-US", "description": "Description"},
            },
            localization("hi", "version-hi"),
        ]
        cli.asc_client.get_app_store_version_localizations.return_value = {"data": existing}
        cli.asc_client.get_app_primary_locale.return_value = "en-US"
        cli.ai_manager = Mock()
        cli.ai_manager.get_provider.return_value = Mock()
        cli._get_app_id = Mock(return_value="app-id")
        cli._select_ai_provider = Mock(return_value="google")
        cli._prompt_translation_refinement = Mock(return_value="")
        cli._translate_locale_bundle = Mock(return_value=("updated", None))
        cli._maybe_save_app_id = Mock()

        with redirect_stdout(io.StringIO()):
            result = cli.translation_mode()

        self.assertTrue(result)
        self.assertEqual(cli._translate_locale_bundle.call_args.args[1], "hi")
        self.assertTrue(
            cli._translate_locale_bundle.call_args.kwargs["translate_version"]
        )
        self.assertFalse(
            cli._translate_locale_bundle.call_args.kwargs["translate_app_info"]
        )
        self.assertIsNone(cli._translate_locale_bundle.call_args.args[5])

    @patch("main.confirm_locale_write", return_value=True)
    @patch("builtins.input", side_effect=["2", "hi", ""])
    def test_partial_state_survives_a_failed_provider_fallback(
        self,
        _input_mock,
        _confirm_mock,
    ):
        cli = TranslateRCLI.__new__(TranslateRCLI)
        cli.asc_client = Mock()
        cli.asc_client.get_latest_app_store_version.return_value = "version-id"
        existing = [
            {
                "id": "version-en",
                "attributes": {"locale": "en-US", "description": "Description"},
            },
            localization("hi", "version-hi"),
        ]
        cli.asc_client.get_app_store_version_localizations.return_value = {"data": existing}
        cli.asc_client.get_app_primary_locale.return_value = "en-US"
        cli.ai_manager = Mock()
        cli.ai_manager.get_provider.side_effect = [Mock(), Mock()]
        cli._get_app_id = Mock(return_value="app-id")
        cli._select_ai_provider = Mock(return_value="google")
        cli._prompt_translation_refinement = Mock(return_value="")
        cli._prepare_app_info_translation_context = Mock(return_value={
            "localizations": [
                localization("en-US", "app-info-en"),
                localization("hi", "app-info-hi"),
            ]
        })
        cli._translate_locale_bundle = Mock(side_effect=[
            PartialLocalizationError("metadata locked"),
            RuntimeError("fallback provider failed"),
        ])
        cli._prompt_retry_with_another_provider = Mock(side_effect=["openai", None])
        cli._maybe_save_app_id = Mock()

        output = io.StringIO()
        with redirect_stdout(output):
            result = cli.translation_mode()

        self.assertTrue(result)
        self.assertEqual(cli._translate_locale_bundle.call_count, 2)
        self.assertTrue(
            cli._translate_locale_bundle.call_args_list[0].kwargs["translate_app_info"]
        )
        self.assertFalse(
            cli._translate_locale_bundle.call_args_list[1].kwargs["translate_app_info"]
        )
        self.assertIn("Partially saved locales: hi", output.getvalue())
        self.assertNotIn("Failed locales: hi", output.getvalue())

    @patch("main.time.sleep")
    @patch("main.confirm_locale_write", return_value=True)
    @patch("builtins.input", side_effect=["2", "all", ""])
    def test_complete_all_repairs_locale_missing_only_from_app_info(
        self,
        _input_mock,
        _confirm_mock,
        _sleep_mock,
    ):
        cli = TranslateRCLI.__new__(TranslateRCLI)
        cli.asc_client = Mock()
        cli.asc_client.get_latest_app_store_version.return_value = "version-id"
        version_localizations = [
            localization(locale, f"version-{locale}") for locale in APP_STORE_LOCALES
        ]
        version_localizations[list(APP_STORE_LOCALES).index("en-US")]["attributes"][
            "description"
        ] = "Description"
        cli.asc_client.get_app_store_version_localizations.return_value = {
            "data": version_localizations
        }
        cli.asc_client.get_app_primary_locale.return_value = "en-US"
        app_info_context = {
            "app_info_id": "app-info-id",
            "localizations": [
                localization(locale, f"app-info-{locale}")
                for locale in APP_STORE_LOCALES
                if locale != "hi"
            ],
        }
        cli.ai_manager = Mock()
        cli.ai_manager.get_provider.return_value = Mock()
        cli._get_app_id = Mock(return_value="app-id")
        cli._select_ai_provider = Mock(return_value="google")
        cli._prompt_translation_refinement = Mock(return_value="")
        cli._prepare_app_info_translation_context = Mock(return_value=app_info_context)
        cli._translate_locale_bundle = Mock(return_value=("updated", "created"))
        cli._maybe_save_app_id = Mock()

        with redirect_stdout(io.StringIO()):
            result = cli.translation_mode()

        self.assertTrue(result)
        self.assertEqual(cli._translate_locale_bundle.call_args.args[1], "hi")
        self.assertFalse(
            cli._translate_locale_bundle.call_args.kwargs["translate_version"]
        )
        self.assertTrue(
            cli._translate_locale_bundle.call_args.kwargs["translate_app_info"]
        )


class FullSetupSelectionTests(unittest.TestCase):
    @patch("main.time.sleep")
    @patch("builtins.input", side_effect=["1", "y", ""])
    def test_full_setup_repairs_cross_surface_locale_mismatch(
        self,
        _input_mock,
        _sleep_mock,
    ):
        cli = TranslateRCLI.__new__(TranslateRCLI)
        cli.asc_client = Mock()
        cli.asc_client.get_latest_app_store_version.return_value = "version-id"
        version_localizations = [
            localization(locale, f"version-{locale}") for locale in APP_STORE_LOCALES
        ]
        version_localizations[list(APP_STORE_LOCALES).index("en-US")]["attributes"][
            "description"
        ] = "Description"
        cli.asc_client.get_app_store_version_localizations.side_effect = [
            {"data": version_localizations},
            {"data": version_localizations},
        ]
        cli.asc_client.get_app_primary_locale.return_value = "en-US"
        initial_app_info = [
            localization(locale, f"app-info-{locale}")
            for locale in APP_STORE_LOCALES
            if locale != "hi"
        ]
        cli._prepare_app_info_translation_context = Mock(return_value={
            "app_info_id": "app-info-id",
            "localizations": initial_app_info,
        })
        cli.asc_client.get_app_info_localizations.return_value = {
            "data": [
                localization(locale, f"app-info-{locale}")
                for locale in APP_STORE_LOCALES
            ]
        }
        cli.ai_manager = Mock()
        cli.ai_manager.get_provider.return_value = Mock()
        cli._get_app_id = Mock(return_value="app-id")
        cli._select_ai_provider = Mock(return_value="google")
        cli._prompt_translation_refinement = Mock(return_value="")
        cli._translate_locale_bundle = Mock(return_value=("updated", "created"))
        cli._maybe_save_app_id = Mock()

        with redirect_stdout(io.StringIO()):
            result = cli.full_setup_mode()

        self.assertTrue(result)
        self.assertEqual(cli._translate_locale_bundle.call_args.args[1], "hi")
        self.assertFalse(
            cli._translate_locale_bundle.call_args.kwargs["translate_version"]
        )
        self.assertTrue(
            cli._translate_locale_bundle.call_args.kwargs["translate_app_info"]
        )


class LocaleBundleTests(unittest.TestCase):
    def setUp(self):
        self.cli = TranslateRCLI.__new__(TranslateRCLI)
        self.cli.asc_client = Mock()

    @staticmethod
    def app_info_context(localizations=None):
        return {
            "app_info_id": "app-info-id",
            "localizations": localizations or [localization("en-US", "app-info-en")],
            "base_locale": "en-US",
            "base_name": "Pixel Stretch Pro",
            "base_subtitle": "Create Pixel Stretch Edits",
            "base_privacy_policy_url": "https://example.com/privacy",
        }

    def test_bundle_translates_every_field_before_writing_app_info_then_metadata(self):
        events = []
        provider = Mock()

        def translate(text, language, **kwargs):
            events.append(("translate", text))
            return f"{language}: {text}"

        provider.translate.side_effect = translate
        self.cli.asc_client.create_app_info_localization.side_effect = (
            lambda *args, **kwargs: events.append(("app-info-write", kwargs))
            or {"data": localization("tr", "app-info-tr")}
        )
        self.cli.asc_client.create_app_store_version_localization.side_effect = (
            lambda *args, **kwargs: events.append(("metadata-write", kwargs))
            or {"data": localization("tr", "version-tr")}
        )
        base_data = {
            "description": "Description",
            "keywords": "photo,effect",
            "promotionalText": "Promo",
            "whatsNew": "Bug fixes",
            "marketingUrl": "https://example.com/marketing",
            "supportUrl": "https://example.com/support",
        }
        version_localizations = [localization("en-US", "version-en")]

        with redirect_stdout(io.StringIO()):
            actions = self.cli._translate_locale_bundle(
                "version-id",
                "tr",
                provider,
                base_data,
                version_localizations,
                self.app_info_context(),
            )

        self.assertEqual(actions, ("created", "created"))
        first_write = next(index for index, event in enumerate(events) if "write" in event[0])
        self.assertTrue(all(event[0] == "translate" for event in events[:first_write]))
        self.assertLess(
            next(index for index, event in enumerate(events) if event[0] == "app-info-write"),
            next(index for index, event in enumerate(events) if event[0] == "metadata-write"),
        )
        app_info_kwargs = next(event[1] for event in events if event[0] == "app-info-write")
        metadata_kwargs = next(event[1] for event in events if event[0] == "metadata-write")
        self.assertEqual(app_info_kwargs["name"], "Turkish: Pixel Stretch Pro")
        self.assertEqual(metadata_kwargs["locale"], "tr")
        self.assertEqual(metadata_kwargs["description"], "Turkish: Description")

    def test_existing_bundle_uses_updates_instead_of_creates(self):
        provider = Mock()
        provider.translate.return_value = "Translated"
        version_localizations = [
            localization("en-US", "version-en"),
            localization("tr", "version-tr"),
        ]
        app_info_context = self.app_info_context([
            localization("en-US", "app-info-en"),
            localization("tr", "app-info-tr"),
        ])

        with redirect_stdout(io.StringIO()):
            actions = self.cli._translate_locale_bundle(
                "version-id",
                "tr",
                provider,
                {"description": "Description"},
                version_localizations,
                app_info_context,
            )

        self.assertEqual(actions, ("updated", "updated"))
        self.cli.asc_client.update_app_info_localization.assert_called_once()
        self.cli.asc_client.update_app_store_version_localization.assert_called_once()
        self.cli.asc_client.create_app_info_localization.assert_not_called()
        self.cli.asc_client.create_app_store_version_localization.assert_not_called()

    def test_missing_version_preserves_existing_app_info(self):
        provider = Mock()
        provider.translate.return_value = "Translated"
        self.cli.asc_client.create_app_store_version_localization.return_value = {
            "data": localization("tr", "version-tr")
        }

        with redirect_stdout(io.StringIO()):
            actions = self.cli._translate_locale_bundle(
                "version-id",
                "tr",
                provider,
                {"description": "Description"},
                [localization("en-US", "version-en")],
                self.app_info_context([
                    localization("en-US", "app-info-en"),
                    localization("tr", "app-info-tr"),
                ]),
                translate_version=True,
                translate_app_info=False,
            )

        self.assertEqual(actions, ("created", None))
        self.cli.asc_client.update_app_info_localization.assert_not_called()
        self.cli.asc_client.create_app_info_localization.assert_not_called()
        self.cli.asc_client.create_app_store_version_localization.assert_called_once()

    def test_missing_app_info_preserves_existing_version_metadata(self):
        provider = Mock()
        provider.translate.return_value = "Translated"
        self.cli.asc_client.create_app_info_localization.return_value = {
            "data": localization("tr", "app-info-tr")
        }

        with redirect_stdout(io.StringIO()):
            actions = self.cli._translate_locale_bundle(
                "version-id",
                "tr",
                provider,
                {"description": "Description"},
                [
                    localization("en-US", "version-en"),
                    localization("tr", "version-tr"),
                ],
                self.app_info_context(),
                translate_version=False,
                translate_app_info=True,
            )

        self.assertEqual(actions, (None, "created"))
        self.cli.asc_client.update_app_store_version_localization.assert_not_called()
        self.cli.asc_client.create_app_store_version_localization.assert_not_called()
        self.cli.asc_client.create_app_info_localization.assert_called_once()

    def test_provider_failure_happens_before_any_app_store_write(self):
        provider = Mock()
        provider.translate.side_effect = RuntimeError("provider failed")

        with self.assertRaisesRegex(RuntimeError, "provider failed"):
            with redirect_stdout(io.StringIO()):
                self.cli._translate_locale_bundle(
                    "version-id",
                    "tr",
                    provider,
                    {"description": "Description"},
                    [localization("en-US", "version-en")],
                    self.app_info_context(),
                )

        self.cli.asc_client.create_app_info_localization.assert_not_called()
        self.cli.asc_client.update_app_info_localization.assert_not_called()
        self.cli.asc_client.create_app_store_version_localization.assert_not_called()
        self.cli.asc_client.update_app_store_version_localization.assert_not_called()

    def test_metadata_failure_after_app_info_write_is_reported_as_partial(self):
        provider = Mock()
        provider.translate.return_value = "Translated"
        self.cli.asc_client.create_app_info_localization.return_value = {
            "data": localization("tr", "app-info-tr")
        }
        self.cli.asc_client.create_app_store_version_localization.side_effect = RuntimeError(
            "metadata locked"
        )

        with self.assertRaisesRegex(PartialLocalizationError, "metadata locked"):
            with redirect_stdout(io.StringIO()):
                self.cli._translate_locale_bundle(
                    "version-id",
                    "tr",
                    provider,
                    {"description": "Description"},
                    [localization("en-US", "version-en")],
                    self.app_info_context(),
                )

        self.cli.asc_client.create_app_info_localization.assert_called_once()
        self.cli.asc_client.create_app_store_version_localization.assert_called_once()

    def test_app_info_create_conflict_refetches_and_updates(self):
        response = requests.Response()
        response.status_code = 409
        conflict = requests.exceptions.HTTPError("409 Conflict", response=response)
        self.cli.asc_client.create_app_info_localization.side_effect = conflict
        self.cli.asc_client.get_app_info_localizations.return_value = {
            "data": [
                localization("en-US", "app-info-en"),
                localization("tr", "app-info-tr"),
            ]
        }
        context = self.app_info_context()

        action = self.cli._upsert_app_info_localization(
            "tr",
            {"name": "Translated"},
            context,
        )

        self.assertEqual(action, "updated")
        self.cli.asc_client.update_app_info_localization.assert_called_once_with(
            "app-info-tr",
            name="Translated",
        )

    def test_version_create_conflict_refetches_and_updates(self):
        response = requests.Response()
        response.status_code = 409
        conflict = requests.exceptions.HTTPError("409 Conflict", response=response)
        self.cli.asc_client.create_app_store_version_localization.side_effect = conflict
        self.cli.asc_client.get_app_store_version_localizations.return_value = {
            "data": [
                localization("en-US", "version-en"),
                localization("tr", "version-tr"),
            ]
        }
        localizations = [localization("en-US", "version-en")]

        action = self.cli._upsert_version_localization(
            "version-id",
            "tr",
            {"description": "Translated"},
            {},
            localizations,
        )

        self.assertEqual(action, "updated")
        self.cli.asc_client.update_app_store_version_localization.assert_called_once_with(
            localization_id="version-tr",
            description="Translated",
            keywords=None,
            marketing_url=None,
            promotional_text=None,
            support_url=None,
            whats_new=None,
        )


if __name__ == "__main__":
    unittest.main()
