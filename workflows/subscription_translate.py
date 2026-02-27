"""
Subscription localization translation workflow.

Translates subscription and subscription group localizations.
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


def _mode_selector() -> str:
    print("Translation scope:")
    print("1. Subscriptions (products)")
    print("2. Subscription Groups")
    raw = input("Select scope (1-2): ").strip()
    return "group" if raw == "2" else "sub"


def _pick_groups(asc_client, app_id: str) -> List[Dict]:
    response = asc_client.get_subscription_groups(app_id)
    groups = response.get("data", []) if isinstance(response, dict) else []
    if not groups:
        print_warning("No subscription groups found for this app")
        return []

    print("Available subscription groups:")
    for idx, group in enumerate(groups, 1):
        attrs = group.get("attributes", {})
        label = attrs.get("referenceName") or group.get("id")
        print(f"{idx:2d}. {label}")

    raw = input("Enter group numbers (comma-separated): ").strip()
    if not raw:
        print_warning("No subscription groups selected")
        return []

    selected_ids: List[str] = []
    try:
        indexes = [int(value.strip()) for value in raw.split(",") if value.strip()]
        for index in indexes:
            if 1 <= index <= len(groups):
                selected_ids.append(groups[index - 1].get("id"))
    except Exception:
        selected_ids = []

    if not selected_ids:
        print_warning("No valid subscription groups selected")
        return []

    return [group for group in groups if group.get("id") in selected_ids]


def _pick_subscriptions(asc_client, groups: List[Dict]) -> List[Dict]:
    choices: List[Dict] = []
    id_to_subscription: Dict[str, Dict] = {}

    for group in groups:
        group_id = group.get("id")
        group_name = (group.get("attributes") or {}).get("referenceName") or group_id
        response = asc_client.get_subscriptions_for_group(group_id)
        subscriptions = response.get("data", []) if isinstance(response, dict) else []

        for subscription in subscriptions:
            attrs = subscription.get("attributes", {})
            name = attrs.get("name") or subscription.get("id")
            product_id = attrs.get("productId", "")
            label = f"{group_name}: {name}" + (f" [{product_id}]" if product_id else "")
            choices.append({"name": label, "id": subscription.get("id")})
            id_to_subscription[subscription.get("id")] = subscription

    if not choices:
        print_warning("No subscriptions found in selected groups")
        return []

    print("Available subscriptions:")
    for idx, choice in enumerate(choices, 1):
        print(f"{idx:2d}. {choice['name']}")

    raw = input("Enter subscription numbers (comma-separated): ").strip()
    if not raw:
        print_warning("No subscriptions selected")
        return []

    selected_ids: List[str] = []
    try:
        indexes = [int(value.strip()) for value in raw.split(",") if value.strip()]
        for index in indexes:
            if 1 <= index <= len(choices):
                selected_ids.append(choices[index - 1]["id"])
    except Exception:
        selected_ids = []

    if not selected_ids:
        print_warning("No valid subscriptions selected")
        return []

    return [id_to_subscription[item_id] for item_id in selected_ids if item_id in id_to_subscription]


def run(cli) -> bool:
    ui = cli.ui
    asc = cli.asc_client

    print_info("Subscription Translation Mode - Translate subscription metadata")
    scope = _mode_selector()

    app_id = ui.prompt_app_id(asc)
    if app_id is None:
        print_info("Cancelled")
        return True

    groups = _pick_groups(asc, app_id)
    if not groups:
        return True

    if scope == "sub":
        targets = _pick_subscriptions(asc, groups)
    else:
        targets = groups

    if not targets:
        return True

    app_locales = get_app_locales(asc, app_id)
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

    for target_index, target in enumerate(targets, 1):
        attrs = target.get("attributes", {})
        if scope == "sub":
            base_label_name = attrs.get("name") or "Untitled Subscription"
            product_id = attrs.get("productId", "")
            label = f"{base_label_name} [{product_id}]" if product_id else base_label_name
            localizations_response = asc.get_subscription_localizations(target.get("id"))
        else:
            base_label_name = attrs.get("referenceName") or "Subscription Group"
            label = base_label_name
            localizations_response = asc.get_subscription_group_localizations(target.get("id"))

        print()
        print_info(f"({target_index}/{len(targets)}) Processing {label}")

        localizations = localizations_response.get("data", []) if isinstance(localizations_response, dict) else []
        if not localizations:
            print_warning("No existing localizations; skipping")
            continue

        base_locale = detect_base_language(localizations)
        if not base_locale:
            print_error("Could not detect base language; skipping")
            continue

        base_attrs = next(
            (loc.get("attributes", {}) for loc in localizations if loc.get("attributes", {}).get("locale") == base_locale),
            {},
        )
        base_name = (base_attrs.get("name") or "").strip()
        if scope == "sub":
            base_description = (base_attrs.get("description") or "").strip()
            desc_key = "description"
        else:
            base_description = (base_attrs.get("customAppName") or "").strip()
            desc_key = "customAppName"

        if not base_name:
            print_error("Base name is missing; skipping")
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
            print_warning("No target languages selected; skipping")
            continue

        name_limit = get_field_limit("subscription_name" if scope == "sub" else "subscription_group_name")
        desc_limit = get_field_limit(
            "subscription_description" if scope == "sub" else "subscription_group_custom_app_name"
        )

        def _translate(locale: str) -> Dict[str, str]:
            language = APP_STORE_LOCALES.get(locale, locale)
            payload: Dict[str, str] = {}
            translated_name = provider.translate(
                text=base_name,
                target_language=language,
                max_length=name_limit,
                is_keywords=False,
                seed=seed,
                refinement=refine_phrase,
            ) or ""
            translated_name = translated_name.strip()
            if name_limit and len(translated_name) > name_limit:
                translated_name = translated_name[:name_limit]
            payload["name"] = translated_name

            if base_description:
                translated_desc = provider.translate(
                    text=base_description,
                    target_language=language,
                    max_length=desc_limit,
                    is_keywords=False,
                    seed=seed,
                    refinement=refine_phrase,
                ) or ""
                translated_desc = translated_desc.strip()
                if desc_limit and len(translated_desc) > desc_limit:
                    translated_desc = translated_desc[:desc_limit]
                payload[desc_key] = translated_desc

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
                if scope == "sub":
                    if localization_id:
                        asc.update_subscription_localization(
                            localization_id=localization_id,
                            name=translated_name,
                            description=data.get("description"),
                        )
                    else:
                        asc.create_subscription_localization(
                            subscription_id=target.get("id"),
                            locale=locale,
                            name=translated_name,
                            description=data.get("description"),
                        )
                else:
                    if localization_id:
                        asc.update_subscription_group_localization(
                            localization_id=localization_id,
                            name=translated_name,
                            custom_app_name=data.get("customAppName"),
                        )
                    else:
                        asc.create_subscription_group_localization(
                            group_id=target.get("id"),
                            locale=locale,
                            name=translated_name,
                            custom_app_name=data.get("customAppName"),
                        )
                success_count += 1
            except Exception as error:
                if "409" in str(error):
                    try:
                        if scope == "sub":
                            refreshed = asc.get_subscription_localizations(target.get("id"))
                        else:
                            refreshed = asc.get_subscription_group_localizations(target.get("id"))

                        refreshed_map = {
                            item.get("attributes", {}).get("locale"): item.get("id")
                            for item in refreshed.get("data", [])
                            if item.get("id")
                        }
                        refreshed_id = refreshed_map.get(locale)
                        if refreshed_id:
                            if scope == "sub":
                                asc.update_subscription_localization(
                                    localization_id=refreshed_id,
                                    name=translated_name,
                                    description=data.get("description"),
                                )
                            else:
                                asc.update_subscription_group_localization(
                                    localization_id=refreshed_id,
                                    name=translated_name,
                                    custom_app_name=data.get("customAppName"),
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
        print_success(f"Saved {success_count}/{len(target_locales)} locales for {label}")

    if hasattr(cli, "_maybe_save_app_id"):
        try:
            cli._maybe_save_app_id(app_id)
        except Exception:
            pass
    input("\nPress Enter to continue...")
    return True
