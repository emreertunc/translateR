"""
Game Center localization workflow.

Translates Game Center text localizations for achievements, leaderboards,
activities, and challenges.
"""

import time
from typing import Dict, List, Optional, Tuple

from utils import (
    APP_STORE_LOCALES,
    detect_base_language,
    find_matching_locale_entry,
    get_field_limit,
    parallel_map_locales,
    print_error,
    print_info,
    print_success,
    print_warning,
    provider_model_info,
)
from workflows.helpers import choose_target_locales, get_app_locales, pick_provider


RESOURCE_TITLES = {
    "achievement": "Achievements",
    "leaderboard": "Leaderboards",
    "activity": "Activities",
    "challenge": "Challenges",
}


def _choose_resource_types() -> List[str]:
    print("Select Game Center resources:")
    print("1. Achievements")
    print("2. Leaderboards")
    print("3. Activities")
    print("4. Challenges")
    raw = input("Select resources (comma-separated or 'all'): ").strip().lower()
    if not raw:
        return []
    if raw in ("all", "*"):
        return ["achievement", "leaderboard", "activity", "challenge"]

    selected: List[str] = []
    for token in raw.replace(" ", "").split(","):
        if token == "1":
            selected.append("achievement")
        elif token == "2":
            selected.append("leaderboard")
        elif token == "3":
            selected.append("activity")
        elif token == "4":
            selected.append("challenge")
    return list(dict.fromkeys(selected))


def _label_item(item: Dict, kind: str) -> str:
    attrs = item.get("attributes", {})
    name = attrs.get("referenceName") or attrs.get("vendorIdentifier") or "Untitled"
    vendor_id = attrs.get("vendorIdentifier")
    label = name

    if vendor_id and vendor_id not in name:
        label = f"{name} [{vendor_id}]"

    if kind == "achievement":
        points = attrs.get("points")
        if points is not None:
            label += f" - {points} pts"
    elif kind == "activity":
        play_style = attrs.get("playStyle")
        if play_style:
            label += f" - {play_style}"
    elif kind == "challenge":
        challenge_type = attrs.get("challengeType")
        if challenge_type:
            label += f" - {challenge_type}"

    return label


def _merge_items(detail_items: List[Dict], group_items: List[Dict]) -> List[Dict]:
    merged: Dict[str, Dict] = {}
    for item in detail_items + group_items:
        item_id = item.get("id")
        if item_id:
            merged[item_id] = item
    return list(merged.values())


def _select_items(items: List[Dict], kind: str) -> List[Dict]:
    if not items:
        print_warning(f"No {RESOURCE_TITLES.get(kind, kind)} found")
        return []

    print(f"Available {RESOURCE_TITLES.get(kind, kind)}:")
    for idx, item in enumerate(items, 1):
        print(f"{idx:2d}. {_label_item(item, kind)}")

    raw = input("Enter item numbers (comma-separated or 'all'): ").strip().lower()
    if not raw:
        print_warning(f"No {RESOURCE_TITLES.get(kind, kind)} selected")
        return []

    if raw in ("all", "*"):
        return items

    selected_ids: List[str] = []
    try:
        indexes = [int(value.strip()) for value in raw.split(",") if value.strip()]
        for index in indexes:
            if 1 <= index <= len(items):
                selected_ids.append(items[index - 1].get("id"))
    except Exception:
        selected_ids = []

    if not selected_ids:
        print_warning(f"No valid {RESOURCE_TITLES.get(kind, kind)} selected")
        return []

    return [item for item in items if item.get("id") in selected_ids]


def _parse_version_string(value: str) -> Optional[Tuple[int, ...]]:
    if not value:
        return None
    parts = value.split(".")
    numbers: List[int] = []
    for part in parts:
        if not part.isdigit():
            return None
        numbers.append(int(part))
    return tuple(numbers)


def _pick_latest_version(versions: List[Dict]) -> Optional[Dict]:
    if not versions:
        return None

    numeric_versions: List[Tuple[Tuple[int, ...], Dict]] = []
    fallback_versions: List[Tuple[str, Dict]] = []
    for version in versions:
        attrs = version.get("attributes", {})
        value = attrs.get("version") or ""
        parsed = _parse_version_string(value)
        if parsed is None:
            fallback_versions.append((value, version))
        else:
            numeric_versions.append((parsed, version))

    if numeric_versions:
        numeric_versions.sort(key=lambda item: item[0])
        return numeric_versions[-1][1]

    if fallback_versions:
        fallback_versions.sort(key=lambda item: item[0])
        return fallback_versions[-1][1]

    return None


def _select_base_locale(available_locales: List[str], suggested: Optional[str]) -> Optional[str]:
    if not available_locales:
        return None

    ordered = list(available_locales)
    if suggested and suggested in ordered:
        ordered.remove(suggested)
        ordered = [suggested] + ordered

    print("Available base locales:")
    for idx, locale in enumerate(ordered, 1):
        name = APP_STORE_LOCALES.get(locale, locale)
        suffix = " (recommended)" if suggested and locale == suggested else ""
        print(f"{idx:2d}. {locale} - {name}{suffix}")

    prompt = "Select base locale"
    if suggested and suggested in ordered:
        prompt += f" (Enter = {suggested})"
    prompt += ": "

    raw = input(prompt).strip()
    if not raw and suggested and suggested in ordered:
        return suggested

    try:
        index = int(raw)
        if 1 <= index <= len(ordered):
            return ordered[index - 1]
    except Exception:
        return None

    return None


def _translate_required(
    provider,
    text: str,
    language_name: str,
    seed: Optional[int],
    refine_phrase: str,
    field_name: str,
    max_length: Optional[int] = None,
) -> str:
    translated = provider.translate(
        text=text,
        target_language=language_name,
        max_length=max_length,
        is_keywords=False,
        seed=seed,
        refinement=refine_phrase,
    ) or ""
    translated = translated.strip()
    if translated:
        return translated

    fallback_refine = (refine_phrase or "").strip()
    tail = f" Do not return empty output. Return only translated {field_name}."
    fallback_refine = (fallback_refine + tail).strip() if fallback_refine else tail.strip()

    translated = provider.translate(
        text=text,
        target_language=language_name,
        max_length=max_length,
        is_keywords=False,
        seed=seed,
        refinement=fallback_refine,
    ) or ""
    return translated.strip()


def _load_item_localizations(asc, kind: str, item_id: str) -> Tuple[List[Dict], Optional[str], Optional[str]]:
    if kind == "achievement":
        response = asc.get_game_center_achievement_localizations(item_id)
        return response.get("data", []), None, None

    if kind == "leaderboard":
        response = asc.get_game_center_leaderboard_localizations(item_id)
        return response.get("data", []), None, None

    if kind == "activity":
        versions_response = asc.get_game_center_activity_versions(item_id)
        versions = versions_response.get("data", []) if isinstance(versions_response, dict) else []
        latest = _pick_latest_version(versions)
        if not latest:
            return [], None, None
        version_id = latest.get("id")
        if not version_id:
            return [], None, None
        version_label = latest.get("attributes", {}).get("version")
        response = asc.get_game_center_activity_version_localizations(version_id)
        return response.get("data", []), version_id, version_label

    versions_response = asc.get_game_center_challenge_versions(item_id)
    versions = versions_response.get("data", []) if isinstance(versions_response, dict) else []
    latest = _pick_latest_version(versions)
    if not latest:
        return [], None, None
    version_id = latest.get("id")
    if not version_id:
        return [], None, None
    version_label = latest.get("attributes", {}).get("version")
    response = asc.get_game_center_challenge_version_localizations(version_id)
    return response.get("data", []), version_id, version_label


def _find_existing_locale_id(localizations: List[Dict], target_locale: str) -> str:
    matched = find_matching_locale_entry(localizations, target_locale)
    if matched:
        return matched.get("id") or ""
    return ""


def _refresh_localizations_for_item(asc, kind: str, item_id: str, version_id: Optional[str]) -> List[Dict]:
    if kind == "achievement":
        response = asc.get_game_center_achievement_localizations(item_id)
        return response.get("data", []) if isinstance(response, dict) else []

    if kind == "leaderboard":
        response = asc.get_game_center_leaderboard_localizations(item_id)
        return response.get("data", []) if isinstance(response, dict) else []

    if kind == "activity" and version_id:
        response = asc.get_game_center_activity_version_localizations(version_id)
        return response.get("data", []) if isinstance(response, dict) else []

    if kind == "challenge" and version_id:
        response = asc.get_game_center_challenge_version_localizations(version_id)
        return response.get("data", []) if isinstance(response, dict) else []

    return []


def run(cli) -> bool:
    ui = cli.ui
    asc = cli.asc_client

    print_info("Game Center Translation Mode - Translate achievements, leaderboards, activities, and challenges")

    app_id = ui.prompt_app_id(asc)
    if app_id is None:
        print_info("Cancelled")
        return True

    try:
        detail_response = asc.get_game_center_detail(app_id)
    except Exception as error:
        print_error(f"Failed to load Game Center detail: {error}")
        input("\nPress Enter to continue...")
        return True

    detail = detail_response.get("data") if isinstance(detail_response, dict) else None
    if not detail:
        print_error("Game Center is not configured for this app")
        input("\nPress Enter to continue...")
        return True

    detail_id = detail.get("id")
    if not detail_id:
        print_error("Game Center detail id is missing")
        input("\nPress Enter to continue...")
        return True

    group_id = None
    try:
        group_response = asc.get_game_center_group(detail_id)
        group = group_response.get("data") if isinstance(group_response, dict) else None
        if isinstance(group, dict):
            group_id = group.get("id")
    except Exception:
        group_id = None

    include_group = False
    if group_id:
        choice = input("Include shared Game Center Group items? (Y/n): ").strip().lower()
        include_group = choice in ("", "y", "yes")

    selected_types = _choose_resource_types()
    if not selected_types:
        print_warning("No resource types selected")
        input("\nPress Enter to continue...")
        return True

    selected_items: List[Tuple[str, Dict]] = []

    for kind in selected_types:
        detail_items: List[Dict] = []
        group_items: List[Dict] = []

        try:
            if kind == "achievement":
                detail_items = asc.get_game_center_achievements(detail_id).get("data", [])
                if include_group and group_id:
                    group_items = asc.get_game_center_group_achievements(group_id).get("data", [])
            elif kind == "leaderboard":
                detail_items = asc.get_game_center_leaderboards(detail_id).get("data", [])
                if include_group and group_id:
                    group_items = asc.get_game_center_group_leaderboards(group_id).get("data", [])
            elif kind == "activity":
                detail_items = asc.get_game_center_activities(detail_id).get("data", [])
                if include_group and group_id:
                    group_items = asc.get_game_center_group_activities(group_id).get("data", [])
            elif kind == "challenge":
                detail_items = asc.get_game_center_challenges(detail_id).get("data", [])
                if include_group and group_id:
                    group_items = asc.get_game_center_group_challenges(group_id).get("data", [])
        except Exception as error:
            print_error(f"Failed to list {RESOURCE_TITLES.get(kind, kind)}: {error}")
            continue

        merged = _merge_items(detail_items, group_items)
        picked = _select_items(merged, kind)
        selected_items.extend((kind, item) for item in picked)

    if not selected_items:
        print_warning("No Game Center items selected")
        input("\nPress Enter to continue...")
        return True

    provider, provider_key = pick_provider(cli)
    if not provider:
        input("\nPress Enter to continue...")
        return True

    seed = getattr(cli, "session_seed", None)
    refine_phrase = cli.config.get_prompt_refinement() or ""
    provider_name, provider_model = provider_model_info(provider, provider_key)
    if seed is not None:
        print_info(f"AI provider: {provider_name} (model: {provider_model or 'n/a'}, seed: {seed})")
    else:
        print_info(f"AI provider: {provider_name} (model: {provider_model or 'n/a'})")

    app_locales = get_app_locales(asc, app_id)

    records: List[Dict] = []
    all_localizations: List[Dict] = []
    locale_sets: List[set] = []

    for kind, item in selected_items:
        item_id = item.get("id")
        if not item_id:
            continue

        localizations, version_id, version_label = _load_item_localizations(asc, kind, item_id)
        label = _label_item(item, kind)
        if version_label:
            label = f"{label} v{version_label}"

        if not localizations:
            print_warning(f"No localizations found for {label}; skipping")
            continue

        locales = {
            entry.get("attributes", {}).get("locale")
            for entry in localizations
            if entry.get("attributes", {}).get("locale")
        }
        if not locales:
            print_warning(f"Localization locales missing for {label}; skipping")
            continue

        records.append(
            {
                "kind": kind,
                "item": item,
                "item_id": item_id,
                "label": label,
                "localizations": localizations,
                "version_id": version_id,
            }
        )
        all_localizations.extend(localizations)
        locale_sets.append(locales)

    if not records or not locale_sets:
        print_warning("No selected items are ready for localization")
        input("\nPress Enter to continue...")
        return True

    union_locales = set()
    for locale_set in locale_sets:
        union_locales.update(locale_set)

    intersection = set(locale_sets[0])
    for locale_set in locale_sets[1:]:
        intersection &= locale_set

    suggested_base = detect_base_language(all_localizations)
    base_choices = sorted(intersection) if intersection else sorted(union_locales)
    if not intersection:
        print_warning("No shared locale exists across all selected items. Items without base locale will be skipped.")

    base_locale = _select_base_locale(base_choices, suggested_base)
    if not base_locale:
        print_warning("No base locale selected")
        input("\nPress Enter to continue...")
        return True

    print_info(f"Base locale: {APP_STORE_LOCALES.get(base_locale, base_locale)} [{base_locale}]")

    supported = set(APP_STORE_LOCALES.keys())
    missing_union = set()
    for record in records:
        localizations = record["localizations"]
        existing_locales = {
            entry.get("attributes", {}).get("locale")
            for entry in localizations
            if entry.get("attributes", {}).get("locale")
        }
        missing_union.update({loc for loc in supported if loc != base_locale and loc not in existing_locales})

    available_targets = {loc: APP_STORE_LOCALES.get(loc, loc) for loc in sorted(missing_union)}
    if not available_targets:
        print_warning("All supported locales are already localized for selected items")
        input("\nPress Enter to continue...")
        return True

    target_locales = choose_target_locales(available_targets, base_locale, preferred_locales=app_locales)
    if not target_locales and available_targets:
        target_locales = list(available_targets.keys())
        print_info("No target locale selected. Using all missing locales.")
    target_locales = [locale for locale in target_locales if locale != base_locale]
    if not target_locales:
        print_warning("No target locales selected")
        input("\nPress Enter to continue...")
        return True

    total_saved = 0

    for index, record in enumerate(records, 1):
        kind = record["kind"]
        item_id = record["item_id"]
        label = record["label"]
        localizations = record["localizations"]
        version_id = record.get("version_id")

        print()
        print_info(f"({index}/{len(records)}) Processing {label}")

        base_entry = find_matching_locale_entry(localizations, base_locale)
        if not base_entry:
            print_warning(f"Base locale {base_locale} not found for this item; skipping")
            continue

        base_attrs = base_entry.get("attributes", {})
        missing_locales = [locale for locale in target_locales if not _find_existing_locale_id(localizations, locale)]
        if not missing_locales:
            print_warning("No missing locales for this item")
            continue

        if kind == "achievement":
            base_name = (base_attrs.get("name") or "").strip()
            base_before = (base_attrs.get("beforeEarnedDescription") or "").strip()
            base_after = (base_attrs.get("afterEarnedDescription") or "").strip()
            if not (base_name and base_before and base_after):
                print_error("Base localization is missing required fields (name/before/after)")
                continue

            name_limit = get_field_limit("game_center_achievement_name") or 30
            before_limit = get_field_limit("game_center_achievement_before_description") or 200
            after_limit = get_field_limit("game_center_achievement_after_description") or 200

            def _task(locale: str) -> Dict[str, str]:
                language = APP_STORE_LOCALES.get(locale, locale)
                translated = {
                    "name": _translate_required(
                        provider,
                        base_name,
                        language,
                        seed,
                        refine_phrase,
                        "achievement name",
                        max_length=name_limit,
                    ),
                    "before": _translate_required(
                        provider,
                        base_before,
                        language,
                        seed,
                        refine_phrase,
                        "before-earned description",
                        max_length=before_limit,
                    ),
                    "after": _translate_required(
                        provider,
                        base_after,
                        language,
                        seed,
                        refine_phrase,
                        "after-earned description",
                        max_length=after_limit,
                    ),
                }
                time.sleep(1)
                return translated

            translated_map, errors = parallel_map_locales(missing_locales, _task, progress_action="Translated")

            saved_count = 0
            for locale in missing_locales:
                language = APP_STORE_LOCALES.get(locale, locale)
                data = translated_map.get(locale, {})
                name = (data.get("name") or "").strip()
                before = (data.get("before") or "").strip()
                after = (data.get("after") or "").strip()
                if not (name and before and after):
                    print_error(f"  Skipping {language}: required fields are empty")
                    continue

                saved = False
                try:
                    response = asc.create_game_center_achievement_localization(
                        achievement_id=item_id,
                        locale=locale,
                        name=name,
                        before_earned_description=before,
                        after_earned_description=after,
                    )
                    created_id = response.get("data", {}).get("id") if isinstance(response, dict) else None
                    if created_id:
                        localizations.append({"id": created_id, "attributes": {"locale": locale}})
                    saved = True
                except Exception as error:
                    if "409" in str(error):
                        try:
                            refreshed = _refresh_localizations_for_item(asc, kind, item_id, version_id)
                            existing_id = _find_existing_locale_id(refreshed, locale)
                            if existing_id:
                                asc.update_game_center_achievement_localization(
                                    existing_id,
                                    name=name,
                                    before_earned_description=before,
                                    after_earned_description=after,
                                )
                                localizations[:] = refreshed
                                saved = True
                        except Exception:
                            saved = False
                    if not saved:
                        print_error(f"  Failed to save {language}: {error}")

                if saved:
                    saved_count += 1

            if errors:
                print_warning(f"{len(errors)} locales failed during translation for {label}")
            print_success(f"Saved {saved_count}/{len(missing_locales)} locales for {label}")
            total_saved += saved_count
            continue

        if kind == "leaderboard":
            base_name = (base_attrs.get("name") or "").strip()
            base_description = (base_attrs.get("description") or "").strip()
            base_suffix = (base_attrs.get("formatterSuffix") or "").strip()
            base_suffix_singular = (base_attrs.get("formatterSuffixSingular") or "").strip()
            base_override = base_attrs.get("formatterOverride")
            if not base_name:
                print_error("Base localization is missing required field: name")
                continue

            name_limit = get_field_limit("game_center_leaderboard_name") or 30
            desc_limit = get_field_limit("game_center_leaderboard_description") or 200

            def _task(locale: str) -> Dict[str, str]:
                language = APP_STORE_LOCALES.get(locale, locale)
                translated_name = _translate_required(
                    provider,
                    base_name,
                    language,
                    seed,
                    refine_phrase,
                    "leaderboard name",
                    max_length=name_limit,
                )
                translated_description = (
                    provider.translate(
                        text=base_description,
                        target_language=language,
                        max_length=desc_limit,
                        is_keywords=False,
                        seed=seed,
                        refinement=refine_phrase,
                    ).strip()
                    if base_description
                    else ""
                )
                translated_suffix = (
                    provider.translate(
                        text=base_suffix,
                        target_language=language,
                        is_keywords=False,
                        seed=seed,
                        refinement=refine_phrase,
                    ).strip()
                    if base_suffix
                    else ""
                )
                translated_suffix_singular = (
                    provider.translate(
                        text=base_suffix_singular,
                        target_language=language,
                        is_keywords=False,
                        seed=seed,
                        refinement=refine_phrase,
                    ).strip()
                    if base_suffix_singular
                    else ""
                )
                time.sleep(1)
                return {
                    "name": translated_name,
                    "description": translated_description,
                    "formatterSuffix": translated_suffix,
                    "formatterSuffixSingular": translated_suffix_singular,
                }

            translated_map, errors = parallel_map_locales(missing_locales, _task, progress_action="Translated")

            saved_count = 0
            for locale in missing_locales:
                language = APP_STORE_LOCALES.get(locale, locale)
                data = translated_map.get(locale, {})
                name = (data.get("name") or "").strip()
                description = (data.get("description") or "").strip() or None
                formatter_suffix = (data.get("formatterSuffix") or "").strip() or None
                formatter_suffix_singular = (data.get("formatterSuffixSingular") or "").strip() or None
                if not name:
                    print_error(f"  Skipping {language}: required field 'name' is empty")
                    continue

                saved = False
                try:
                    response = asc.create_game_center_leaderboard_localization(
                        leaderboard_id=item_id,
                        locale=locale,
                        name=name,
                        description=description,
                        formatter_suffix=formatter_suffix,
                        formatter_suffix_singular=formatter_suffix_singular,
                        formatter_override=base_override,
                    )
                    created_id = response.get("data", {}).get("id") if isinstance(response, dict) else None
                    if created_id:
                        localizations.append({"id": created_id, "attributes": {"locale": locale}})
                    saved = True
                except Exception as error:
                    if "409" in str(error):
                        try:
                            refreshed = _refresh_localizations_for_item(asc, kind, item_id, version_id)
                            existing_id = _find_existing_locale_id(refreshed, locale)
                            if existing_id:
                                asc.update_game_center_leaderboard_localization(
                                    existing_id,
                                    name=name,
                                    description=description,
                                    formatter_suffix=formatter_suffix,
                                    formatter_suffix_singular=formatter_suffix_singular,
                                    formatter_override=base_override,
                                )
                                localizations[:] = refreshed
                                saved = True
                        except Exception:
                            saved = False
                    if not saved:
                        print_error(f"  Failed to save {language}: {error}")

                if saved:
                    saved_count += 1

            if errors:
                print_warning(f"{len(errors)} locales failed during translation for {label}")
            print_success(f"Saved {saved_count}/{len(missing_locales)} locales for {label}")
            total_saved += saved_count
            continue

        if kind in ("activity", "challenge"):
            if not version_id:
                print_error("Version id is missing for this item")
                continue

            base_name = (base_attrs.get("name") or "").strip()
            base_description = (base_attrs.get("description") or "").strip()
            if not base_name:
                print_error("Base localization is missing required field: name")
                continue

            if kind == "activity":
                name_limit = get_field_limit("game_center_activity_name") or 30
                desc_limit = get_field_limit("game_center_activity_description") or 200
            else:
                name_limit = get_field_limit("game_center_challenge_name") or 30
                desc_limit = get_field_limit("game_center_challenge_description") or 200

            def _task(locale: str) -> Dict[str, str]:
                language = APP_STORE_LOCALES.get(locale, locale)
                translated_name = _translate_required(
                    provider,
                    base_name,
                    language,
                    seed,
                    refine_phrase,
                    f"{kind} name",
                    max_length=name_limit,
                )
                translated_description = (
                    provider.translate(
                        text=base_description,
                        target_language=language,
                        max_length=desc_limit,
                        is_keywords=False,
                        seed=seed,
                        refinement=refine_phrase,
                    ).strip()
                    if base_description
                    else ""
                )
                time.sleep(1)
                return {"name": translated_name, "description": translated_description}

            translated_map, errors = parallel_map_locales(missing_locales, _task, progress_action="Translated")

            saved_count = 0
            for locale in missing_locales:
                language = APP_STORE_LOCALES.get(locale, locale)
                data = translated_map.get(locale, {})
                name = (data.get("name") or "").strip()
                description = (data.get("description") or "").strip() or None
                if not name:
                    print_error(f"  Skipping {language}: required field 'name' is empty")
                    continue

                saved = False
                try:
                    if kind == "activity":
                        response = asc.create_game_center_activity_localization(
                            version_id=version_id,
                            locale=locale,
                            name=name,
                            description=description,
                        )
                    else:
                        response = asc.create_game_center_challenge_localization(
                            version_id=version_id,
                            locale=locale,
                            name=name,
                            description=description,
                        )
                    created_id = response.get("data", {}).get("id") if isinstance(response, dict) else None
                    if created_id:
                        localizations.append({"id": created_id, "attributes": {"locale": locale}})
                    saved = True
                except Exception as error:
                    if "409" in str(error):
                        try:
                            refreshed = _refresh_localizations_for_item(asc, kind, item_id, version_id)
                            existing_id = _find_existing_locale_id(refreshed, locale)
                            if existing_id:
                                if kind == "activity":
                                    asc.update_game_center_activity_localization(
                                        existing_id,
                                        name=name,
                                        description=description,
                                    )
                                else:
                                    asc.update_game_center_challenge_localization(
                                        existing_id,
                                        name=name,
                                        description=description,
                                    )
                                localizations[:] = refreshed
                                saved = True
                        except Exception:
                            saved = False
                    if not saved:
                        print_error(f"  Failed to save {language}: {error}")

                if saved:
                    saved_count += 1

            if errors:
                print_warning(f"{len(errors)} locales failed during translation for {label}")
            print_success(f"Saved {saved_count}/{len(missing_locales)} locales for {label}")
            total_saved += saved_count

    print()
    print_success(f"Game Center translation completed. Localizations saved: {total_saved}")
    if total_saved > 0 and hasattr(cli, "_maybe_save_app_id"):
        try:
            cli._maybe_save_app_id(app_id)
        except Exception:
            pass

    input("\nPress Enter to continue...")
    return True
