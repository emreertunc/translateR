"""
In-App Events localization translation workflow.
"""

import time
from typing import Dict, List, Optional, Tuple

from utils import (
    APP_STORE_LOCALES,
    detect_base_language,
    get_field_limit,
    parallel_map_locales,
    print_error,
    print_info,
    print_success,
    print_warning,
    provider_model_info,
)
from workflows.helpers import choose_target_locales, get_app_locales, pick_provider


def _select_events(asc_client, app_id: str) -> List[Dict]:
    response = asc_client.get_app_events(app_id)
    events = response.get("data", []) if isinstance(response, dict) else []
    if not events:
        print_warning("No in-app events found for this app")
        return []

    print("Available in-app events:")
    for idx, event in enumerate(events, 1):
        attrs = event.get("attributes", {}) or {}
        ref_name = attrs.get("referenceName") or "Untitled Event"
        badge = attrs.get("badge") or ""
        state = attrs.get("eventState") or ""
        label = ref_name
        if badge:
            label += f" - {badge}"
        if state:
            label += f" ({state})"
        print(f"{idx:2d}. {label}")

    raw = input("Enter event numbers (comma-separated): ").strip()
    if not raw:
        print_warning("No in-app events selected")
        return []

    selected_ids: List[str] = []
    try:
        indexes = [int(value.strip()) for value in raw.split(",") if value.strip()]
        for index in indexes:
            if 1 <= index <= len(events):
                selected_ids.append(events[index - 1].get("id"))
    except Exception:
        selected_ids = []

    if not selected_ids:
        print_warning("No valid in-app events selected")
        return []

    return [event for event in events if event.get("id") in selected_ids]


def _locale_id_map(localizations: List[Dict]) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for localization in localizations:
        locale = localization.get("attributes", {}).get("locale")
        loc_id = localization.get("id")
        if locale and loc_id:
            mapping[locale] = loc_id
    return mapping


def _find_existing_locale_id(locale_ids: Dict[str, str], locale: str) -> str:
    """Find exact or safe root locale match."""
    loc_id = locale_ids.get(locale)
    if loc_id:
        return loc_id

    if "-" in locale:
        return ""

    root = locale.split("-")[0].lower()
    matches = [
        value
        for code, value in locale_ids.items()
        if code and code.split("-")[0].lower() == root
    ]
    return matches[0] if len(matches) == 1 else ""


def _prompt_missing_source(ui, base_name: str, base_short: str, base_long: str) -> Tuple[str, str, str]:
    if not base_name:
        base_name = input("Base event name is empty. Enter source event name: ").strip()
    if not base_short:
        base_short = input("Base short description is empty. Enter source short description: ").strip()
    if not base_long:
        edited = ui.prompt_multiline("Base long description is empty. Enter source long description (END with 'EOF'):")
        base_long = (edited or "").strip()
    return base_name, base_short, base_long


def run(cli) -> bool:
    ui = cli.ui
    asc = cli.asc_client

    print_info("In-App Events Translation Mode - Translate event name and descriptions")

    app_id = ui.prompt_app_id(asc)
    if app_id is None:
        print_info("Cancelled")
        return True

    app_locales = get_app_locales(asc, app_id)
    selected_events = _select_events(asc, app_id)
    if not selected_events:
        return True

    provider, provider_key = pick_provider(cli)
    if not provider:
        return True

    seed = getattr(cli, "session_seed", None)
    refine_phrase = cli.config.get_prompt_refinement() or ""
    provider_name, provider_model = provider_model_info(provider, provider_key)
    if seed is not None:
        print_info(f"AI provider: {provider_name} (model: {provider_model or 'n/a'}, seed: {seed})")
    else:
        print_info(f"AI provider: {provider_name} (model: {provider_model or 'n/a'})")

    name_limit = get_field_limit("app_event_name") or 30
    short_limit = get_field_limit("app_event_short_description") or 50
    long_limit = get_field_limit("app_event_long_description") or 120

    total_saved = 0
    for event_index, event in enumerate(selected_events, 1):
        attrs = event.get("attributes", {}) or {}
        event_id = event.get("id") or ""
        ref_name = attrs.get("referenceName") or "Untitled Event"
        state = attrs.get("eventState") or ""
        badge = attrs.get("badge") or ""
        label = ref_name + (f" - {badge}" if badge else "") + (f" ({state})" if state else "")

        print()
        print_info(f"({event_index}/{len(selected_events)}) Processing {label}")
        if not event_id:
            print_error("Missing event id; skipping")
            continue

        localizations_response = asc.get_app_event_localizations(event_id)
        localizations = localizations_response.get("data", []) if isinstance(localizations_response, dict) else []
        if not localizations:
            print_warning("No existing localizations found; skipping")
            continue

        primary_locale = attrs.get("primaryLocale")
        locale_ids = _locale_id_map(localizations)

        base_locale: Optional[str] = None
        if primary_locale and primary_locale in locale_ids:
            base_locale = primary_locale
        else:
            base_locale = detect_base_language(localizations)
        if not base_locale:
            print_error("Could not detect base locale; skipping")
            continue

        base_attrs = next(
            (loc.get("attributes", {}) for loc in localizations if loc.get("attributes", {}).get("locale") == base_locale),
            {},
        )
        base_name = (base_attrs.get("name") or "").strip()
        base_short = (base_attrs.get("shortDescription") or "").strip()
        base_long = (base_attrs.get("longDescription") or "").strip()
        base_name, base_short, base_long = _prompt_missing_source(ui, base_name, base_short, base_long)

        if not base_name or not base_short or not base_long:
            print_error("Source fields (name/short/long) are required; skipping this event")
            continue

        print_info(f"Base language: {APP_STORE_LOCALES.get(base_locale, base_locale)} [{base_locale}]")

        available_targets = {
            locale: name
            for locale, name in APP_STORE_LOCALES.items()
            if locale not in locale_ids and locale != base_locale
        }
        target_locales = choose_target_locales(
            available_targets,
            base_locale,
            preferred_locales=app_locales,
        )
        if not target_locales and available_targets:
            target_locales = list(available_targets.keys())
            print_info("No locales selected. Using all missing locales.")
        target_locales = [locale for locale in target_locales if locale != base_locale]
        if not target_locales:
            print_warning("No target locales selected; skipping")
            continue

        def _translate(locale: str) -> Dict[str, str]:
            language = APP_STORE_LOCALES.get(locale, locale)
            translated_name = provider.translate(
                text=base_name,
                target_language=language,
                max_length=name_limit,
                is_keywords=False,
                seed=seed,
                refinement=refine_phrase,
            ) or ""
            translated_short = provider.translate(
                text=base_short,
                target_language=language,
                max_length=short_limit,
                is_keywords=False,
                seed=seed,
                refinement=refine_phrase,
            ) or ""
            translated_long = provider.translate(
                text=base_long,
                target_language=language,
                max_length=long_limit,
                is_keywords=False,
                seed=seed,
                refinement=refine_phrase,
            ) or ""

            translated_name = translated_name.strip()[:name_limit]
            translated_short = translated_short.strip()[:short_limit]
            translated_long = translated_long.strip()[:long_limit]
            if len(translated_long) < 2:
                translated_long = (translated_short or translated_name)[:long_limit]
            if len(translated_long) < 2:
                translated_long = ""

            time.sleep(1)
            return {
                "name": translated_name,
                "shortDescription": translated_short,
                "longDescription": translated_long,
            }

        translated_map, _ = parallel_map_locales(
            target_locales,
            _translate,
            progress_action="Translated",
            pacing_seconds=0.0,
        )

        saved = 0
        for locale in target_locales:
            data = translated_map.get(locale, {})
            if (
                not data.get("name")
                or not data.get("shortDescription")
                or len(data.get("longDescription", "")) < 2
            ):
                print_error(f"  ❌ Skipping {APP_STORE_LOCALES.get(locale, locale)}: translated fields are incomplete")
                continue

            localization_id = _find_existing_locale_id(locale_ids, locale)
            try:
                if localization_id:
                    asc.update_app_event_localization(
                        localization_id=localization_id,
                        name=data.get("name"),
                        short_description=data.get("shortDescription"),
                        long_description=data.get("longDescription"),
                    )
                else:
                    asc.create_app_event_localization(
                        app_event_id=event_id,
                        locale=locale,
                        name=data.get("name"),
                        short_description=data.get("shortDescription"),
                        long_description=data.get("longDescription"),
                    )
                saved += 1
            except Exception as error:
                if "409" in str(error):
                    try:
                        refreshed = asc.get_app_event_localizations(event_id)
                        refreshed_ids = _locale_id_map(refreshed.get("data", []))
                        refreshed_id = _find_existing_locale_id(refreshed_ids, locale)
                        if refreshed_id:
                            asc.update_app_event_localization(
                                localization_id=refreshed_id,
                                name=data.get("name"),
                                short_description=data.get("shortDescription"),
                                long_description=data.get("longDescription"),
                            )
                            locale_ids[locale] = refreshed_id
                            saved += 1
                        else:
                            print_error(f"  ❌ Failed to save {APP_STORE_LOCALES.get(locale, locale)}: {error}")
                    except Exception:
                        print_error(f"  ❌ Failed to save {APP_STORE_LOCALES.get(locale, locale)}: {error}")
                else:
                    print_error(f"  ❌ Failed to save {APP_STORE_LOCALES.get(locale, locale)}: {error}")

        total_saved += saved
        print_success(f"Saved {saved}/{len(target_locales)} locales for {label}")

    print()
    print_success(f"In-app events translation finished. Localizations saved: {total_saved}")
    if total_saved > 0 and hasattr(cli, "_maybe_save_app_id"):
        try:
            cli._maybe_save_app_id(app_id)
        except Exception:
            pass
    input("\nPress Enter to continue...")
    return True
