"""
In-App Purchase localization translation workflow.

Translates IAP display name and description to missing locales.
"""

import time
from typing import Dict, List

from utils import (
    APP_STORE_LOCALES,
    detect_base_language,
    format_progress,
    get_field_limit,
    parallel_map_locales,
    print_error,
    print_info,
    print_success,
    print_warning,
    provider_model_info,
)
from workflows.helpers import choose_target_locales, get_app_locales, pick_provider


def _select_iaps(ui, asc_client, app_id: str) -> List[Dict]:
    """Prompt user to select one or more IAPs."""
    response = asc_client.get_in_app_purchases(app_id)
    items = response.get("data", []) if isinstance(response, dict) else []
    if not items:
        print_error("No in-app purchases found for this app")
        return []

    print("Available IAPs:")
    for idx, item in enumerate(items, 1):
        attrs = item.get("attributes", {})
        name = attrs.get("referenceName") or attrs.get("name") or "Untitled IAP"
        product_id = attrs.get("productId")
        iap_type = attrs.get("inAppPurchaseType") or ""
        label = name
        if product_id:
            label += f" [{product_id}]"
        if iap_type:
            label += f" - {iap_type}"
        print(f"{idx:2d}. {label}")

    raw = input("Enter IAP numbers (comma-separated): ").strip()
    if not raw:
        print_warning("No in-app purchases selected")
        return []

    selected_ids: List[str] = []
    try:
        indexes = [int(value.strip()) for value in raw.split(",") if value.strip()]
        for index in indexes:
            if 1 <= index <= len(items):
                selected_ids.append(items[index - 1].get("id"))
    except Exception:
        selected_ids = []

    if not selected_ids:
        print_warning("No valid in-app purchases selected")
        return []

    selected = [item for item in items if item.get("id") in selected_ids]
    return selected


def run(cli) -> bool:
    ui = cli.ui
    asc = cli.asc_client

    print_info("IAP Translation Mode - Translate in-app purchase name and description")

    app_id = ui.prompt_app_id(asc)
    if app_id is None:
        print_info("Cancelled")
        return True

    app_locales = get_app_locales(asc, app_id)
    selected_iaps = _select_iaps(ui, asc, app_id)
    if not selected_iaps:
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

    total_saved = 0
    for iap_index, iap in enumerate(selected_iaps, 1):
        attrs = iap.get("attributes", {})
        iap_name = attrs.get("referenceName") or attrs.get("name") or "Untitled IAP"
        product_id = attrs.get("productId", "")
        iap_label = f"{iap_name} [{product_id}]" if product_id else iap_name
        print()
        print_info(f"({iap_index}/{len(selected_iaps)}) Processing {iap_label}")

        localizations_response = asc.get_in_app_purchase_localizations(iap.get("id"))
        localizations = localizations_response.get("data", []) if isinstance(localizations_response, dict) else []
        if not localizations:
            print_warning("No existing localization found; unable to detect base language")
            continue

        base_locale = detect_base_language(localizations)
        if not base_locale:
            print_error("Could not detect base language for this IAP; skipping")
            continue

        base_attrs = next(
            (loc.get("attributes", {}) for loc in localizations if loc.get("attributes", {}).get("locale") == base_locale),
            {},
        )
        base_name = (base_attrs.get("name") or "").strip()
        base_description = (base_attrs.get("description") or "").strip()
        if not base_name:
            print_error("Base localization is missing required name; skipping")
            continue

        print_info(f"Base language: {APP_STORE_LOCALES.get(base_locale, base_locale)} [{base_locale}]")

        existing_locale_ids: Dict[str, str] = {
            loc.get("attributes", {}).get("locale"): loc.get("id")
            for loc in localizations
            if loc.get("id")
        }
        available_targets = {
            locale: name
            for locale, name in APP_STORE_LOCALES.items()
            if locale not in existing_locale_ids and locale != base_locale
        }
        if not available_targets:
            print_warning("All supported languages are already localized for this IAP")
            continue

        target_locales = choose_target_locales(
            available_targets,
            base_locale,
            preferred_locales=app_locales,
        )
        if not target_locales and available_targets:
            target_locales = list(available_targets.keys())
            print_info("No locales selected. Using all missing locales.")
        if not target_locales:
            print_warning("No target languages selected; skipping this IAP")
            continue

        name_limit = get_field_limit("iap_name") or 30
        desc_limit = get_field_limit("iap_description") or 45

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
            translated_name = translated_name.strip()
            if not translated_name:
                stronger = (refine_phrase or "").strip()
                extra = " Do not return an empty string. Return only translated text."
                stronger = (stronger + extra).strip() if stronger else extra.strip()
                translated_name = (
                    provider.translate(
                        text=base_name,
                        target_language=language,
                        max_length=name_limit,
                        is_keywords=False,
                        seed=seed,
                        refinement=stronger,
                    )
                    or ""
                ).strip()
            if len(translated_name) > name_limit:
                translated_name = translated_name[:name_limit]

            payload: Dict[str, str] = {"name": translated_name}
            if base_description:
                translated_description = provider.translate(
                    text=base_description,
                    target_language=language,
                    max_length=desc_limit,
                    is_keywords=False,
                    seed=seed,
                    refinement=refine_phrase,
                ) or ""
                translated_description = translated_description.strip()
                if len(translated_description) > desc_limit:
                    translated_description = translated_description[:desc_limit]
                payload["description"] = translated_description

            time.sleep(1)
            return payload

        translated_map, _ = parallel_map_locales(
            target_locales,
            _translate,
            progress_action="Translated",
            pacing_seconds=0.0,
        )

        success_count = 0
        total_targets = len(target_locales)
        completed = 0
        last_len = 0

        try:
            line = format_progress(0, total_targets, "Saving locales...")
            print(line, end="\r")
            last_len = len(line)
        except Exception:
            pass

        for locale in target_locales:
            data = translated_map.get(locale, {})
            translated_name = (data.get("name") or "").strip()
            if not translated_name:
                print_error(f"  ❌ Skipping {APP_STORE_LOCALES.get(locale, locale)}: translated name is empty")
                completed += 1
                continue

            localization_id = existing_locale_ids.get(locale)
            try:
                if localization_id:
                    asc.update_in_app_purchase_localization(
                        localization_id=localization_id,
                        name=translated_name,
                        description=data.get("description"),
                    )
                else:
                    asc.create_in_app_purchase_localization(
                        iap_id=iap.get("id"),
                        locale=locale,
                        name=translated_name,
                        description=data.get("description"),
                    )
                success_count += 1
            except Exception as error:
                if "409" in str(error) and not localization_id:
                    try:
                        refreshed = asc.get_in_app_purchase_localizations(iap.get("id"))
                        refreshed_map = {
                            item.get("attributes", {}).get("locale"): item.get("id")
                            for item in refreshed.get("data", [])
                            if item.get("id")
                        }
                        refreshed_id = refreshed_map.get(locale)
                        if refreshed_id:
                            asc.update_in_app_purchase_localization(
                                localization_id=refreshed_id,
                                name=translated_name,
                                description=data.get("description"),
                            )
                            existing_locale_ids[locale] = refreshed_id
                            success_count += 1
                        else:
                            print_error(f"  ❌ Failed to save {APP_STORE_LOCALES.get(locale, locale)}: {error}")
                    except Exception:
                        print_error(f"  ❌ Failed to save {APP_STORE_LOCALES.get(locale, locale)}: {error}")
                else:
                    print_error(f"  ❌ Failed to save {APP_STORE_LOCALES.get(locale, locale)}: {error}")

            completed += 1
            try:
                line = format_progress(completed, total_targets, f"Saved {APP_STORE_LOCALES.get(locale, locale)}")
                pad = max(0, last_len - len(line))
                print("\r" + line + (" " * pad), end="")
                last_len = len(line)
            except Exception:
                pass

        try:
            print("\r" + (" " * last_len) + "\r", end="")
        except Exception:
            pass

        total_saved += success_count
        print_success(f"Saved {success_count}/{len(target_locales)} locales for {iap_label}")

    print()
    print_success(f"IAP translation finished. Localizations saved: {total_saved}")
    if total_saved > 0 and hasattr(cli, "_maybe_save_app_id"):
        try:
            cli._maybe_save_app_id(app_id)
        except Exception:
            pass
    input("\nPress Enter to continue...")
    return True
