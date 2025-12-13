"""
Subscription localization translation workflow.

Translates subscription name and description to missing locales.
"""

import time
from typing import Dict, List

from utils import (
    APP_STORE_LOCALES,
    get_field_limit,
    detect_base_language,
    print_info,
    print_warning,
    print_error,
    print_success,
    parallel_map_locales,
    provider_model_info,
    format_progress,
)


def _pick_groups(ui, asc, app_id: str) -> List[Dict]:
    resp = asc.get_subscription_groups(app_id)
    groups = resp.get("data", []) if isinstance(resp, dict) else []
    if not groups:
        print_warning("No subscription groups found for this app")
        return []
    choices = []
    id_to_group = {}
    for g in groups:
        attrs = g.get("attributes", {})
        label = attrs.get("referenceName") or g.get("id")
        choices.append({"name": label, "value": g.get("id")})
        id_to_group[g.get("id")] = g
    selected_ids: List[str] = []
    if ui.available():
        selected_ids = ui.checkbox("Select subscription group(s)", choices, add_back=True) or []
    else:
        for idx, c in enumerate(choices, 1):
            print(f"{idx}. {c['name']}")
        raw = input("Enter group numbers (comma-separated): ").strip()
        if raw:
            try:
                nums = [int(x) for x in raw.replace(' ', '').split(',') if x]
                for n in nums:
                    if 1 <= n <= len(choices):
                        selected_ids.append(choices[n - 1]["value"])
            except Exception:
                selected_ids = []
    if not selected_ids:
        print_warning("No subscription groups selected")
        return []
    return [id_to_group[sid] for sid in selected_ids if sid in id_to_group]


def _pick_subscriptions(ui, asc, groups: List[Dict]) -> List[Dict]:
    """Select subscriptions across one or more groups."""
    choices = []
    id_to_item: Dict[str, Dict] = {}
    for group in groups:
        group_id = group.get("id")
        group_name = (group.get("attributes") or {}).get("referenceName") or group_id
        resp = asc.get_subscriptions_for_group(group_id)
        subs = resp.get("data", []) if isinstance(resp, dict) else []
        if not subs:
            continue
        for s in subs:
            attrs = s.get("attributes", {})
            name = attrs.get("name") or s.get("id")
            pid = attrs.get("productId", "")
            label = name + (f"  [{pid}]" if pid else "")
            label = f"{group_name}: {label}"
            choices.append({"name": label, "value": s.get("id")})
            id_to_item[s.get("id")] = s
    selected: List[str] = []
    if ui.available():
        selected = ui.checkbox("Select subscriptions to translate", choices, add_back=True) or []
    else:
        for idx, c in enumerate(choices, 1):
            print(f"{idx}. {c['name']}")
        raw = input("Enter numbers (comma-separated): ").strip()
        if raw:
            try:
                nums = [int(x) for x in raw.replace(' ', '').split(',') if x]
                for n in nums:
                    if 1 <= n <= len(choices):
                        selected.append(choices[n - 1]["value"])
            except Exception:
                selected = []
    if not selected:
        print_warning("No subscriptions selected")
        return []
    return [id_to_item[sid] for sid in selected if sid in id_to_item]


def _mode_selector(ui) -> str:
    if ui.available():
        choice = ui.select("Select subscription translation scope", [
            {"name": "Subscriptions (products)", "value": "sub"},
            {"name": "Subscription Groups (group display)", "value": "group"},
        ], add_back=True)
        return choice or "sub"
    print("1) Subscriptions (products)\n2) Subscription Groups")
    raw = input("Select (1-2): ").strip()
    return "group" if raw == "2" else "sub"


def run(cli) -> bool:
    ui = cli.ui
    asc = cli.asc_client

    print_info("Subscription Translation Mode - Translate subscription name and description")

    scope = _mode_selector(ui)

    app_id = ui.prompt_app_id(asc)
    if app_id is None:
        print_info("Cancelled")
        return True

    groups_selected = _pick_groups(ui, asc, app_id)
    if not groups_selected:
        return True

    subs: List[Dict] = []
    groups: List[Dict] = []
    if scope == "sub":
        subs = _pick_subscriptions(ui, asc, groups_selected)
        if not subs:
            return True
    else:
        groups = groups_selected

    # Prefill locales from app's latest version
    app_locales = set()
    try:
        latest_ver = asc.get_latest_app_store_version(app_id)
        if latest_ver:
            locs = asc.get_app_store_version_localizations(latest_ver).get("data", [])
            app_locales = {l.get("attributes", {}).get("locale") for l in locs if l.get("attributes", {}).get("locale")}
    except Exception:
        pass

    # Provider selection (reuse helper from IAP)
    from workflows.iap_translate import _pick_provider  # reuse selection helper
    provider, provider_key = _pick_provider(cli)
    if not provider:
        return True
    refine_phrase = (getattr(cli, "config", None).get_prompt_refinement() if getattr(cli, "config", None) else "") or ""
    seed = getattr(cli, "session_seed", None)
    pname, pmodel = provider_model_info(provider, provider_key)
    print_info(f"AI provider: {pname} — model: {pmodel or 'n/a'} — seed: {seed}")

    targets = subs if scope == "sub" else groups
    global_targets: List[str] = []
    global_targets_enabled = scope == "sub" and len(subs) > 1

    # Preselect targets once for multi-sub runs
    if global_targets_enabled:
        first_sub = subs[0]
        loc_resp = asc.get_subscription_localizations(first_sub.get("id"))
        locs_first = loc_resp.get("data", []) if isinstance(loc_resp, dict) else []
        base_locale_first = detect_base_language(locs_first)
        existing_first = {l.get("attributes", {}).get("locale") for l in locs_first if l.get("attributes", {}).get("locale")}
        from workflows.iap_translate import _choose_targets
        global_targets = _choose_targets(ui, list(existing_first), base_locale_first or "", preferred_locales=app_locales)

    for idx, sub in enumerate(targets, 1):
        attrs = sub.get("attributes", {})
        if scope == "sub":
            sub_name = attrs.get("name") or "Untitled Subscription"
            product_id = attrs.get("productId", "")
            label = f"{sub_name} [{product_id}]" if product_id else sub_name
        else:
            sub_name = attrs.get("referenceName") or "Subscription Group"
            label = sub_name
        print()
        print_info(f"({idx}/{len(targets)}) Processing {label}")

        loc_resp = asc.get_subscription_localizations(sub.get("id")) if scope == "sub" else asc.get_subscription_group_localizations(sub.get("id"))
        locs = loc_resp.get("data", []) if isinstance(loc_resp, dict) else []
        if not locs:
            print_warning("No existing localizations; skipping")
            continue

        base_locale = detect_base_language(locs)
        if not base_locale:
            print_error("Could not detect base language; skipping")
            continue
        base_attrs = next((l.get("attributes", {}) for l in locs if l.get("attributes", {}).get("locale") == base_locale), {})
        base_name = base_attrs.get("name", "")
        base_desc = base_attrs.get("description", "") if scope == "sub" else base_attrs.get("customAppName", "")
        if not base_name:
            print_error("Base subscription name missing; skipping")
            continue
        print_info(f"Base language: {APP_STORE_LOCALES.get(base_locale, base_locale)} [{base_locale}]")

        existing_locale_ids: Dict[str, str] = {l.get("attributes", {}).get("locale"): l.get("id") for l in locs if l.get("id")}
        existing_locale_attrs: Dict[str, Dict] = {l.get("attributes", {}).get("locale"): (l.get("attributes", {}) or {}) for l in locs if l.get("attributes")}
        from workflows.iap_translate import _choose_targets  # reuse locale selector with defaults
        if global_targets_enabled and global_targets:
            target_locales = [t for t in global_targets if t not in existing_locale_ids]
        else:
            target_locales = _choose_targets(ui, list(existing_locale_ids.keys()), base_locale, preferred_locales=app_locales)
        # Always avoid translating the base locale
        target_locales = [t for t in target_locales if t != base_locale]
        if not target_locales:
            print_warning("No target languages selected; skipping this subscription")
            continue

        name_limit = get_field_limit("subscription_name") if scope == "sub" else get_field_limit("subscription_group_name")
        desc_limit = get_field_limit("subscription_description") if scope == "sub" else get_field_limit("subscription_group_custom_app_name")

        def _task(loc: str):
            language_name = APP_STORE_LOCALES.get(loc, loc)
            translated = {}
            translated["name"] = provider.translate(base_name, language_name, max_length=name_limit, seed=seed, refinement=refine_phrase)
            if base_desc:
                field = "description" if scope == "sub" else "customAppName"
                translated[field] = provider.translate(base_desc, language_name, max_length=desc_limit, seed=seed, refinement=refine_phrase)
            time.sleep(1)
            return translated

        results, errs = parallel_map_locales(target_locales, _task, progress_action="Translated", pacing_seconds=0.0)

        success = 0
        total_targets = len(target_locales)
        completed = 0
        last_progress_len = 0
        try:
            line = format_progress(0, total_targets, "Saving locales...")
            print(line, end="\r")
            last_progress_len = len(line)
        except Exception:
            pass
        def _refresh_locale_ids() -> Dict[str, str]:
            try:
                refreshed = asc.get_subscription_localizations(sub.get("id")) if scope == "sub" else asc.get_subscription_group_localizations(sub.get("id"))
                refreshed_map = {l.get("attributes", {}).get("locale"): l.get("id") for l in refreshed.get("data", []) if l.get("id")}
                refreshed_attrs = {l.get("attributes", {}).get("locale"): (l.get("attributes", {}) or {}) for l in refreshed.get("data", []) if l.get("attributes")}
                existing_locale_ids.clear()
                existing_locale_ids.update(refreshed_map)
                existing_locale_attrs.clear()
                existing_locale_attrs.update(refreshed_attrs)
                return refreshed_map
            except Exception:
                return existing_locale_ids

        def _unique_root_match(loc_map: Dict[str, str], locale_code: str) -> str:
            # Never map region/script locales like en-AU to a different variant like en-US.
            # Only allow root matching when the requested locale has no region/script (e.g., fi vs fi-FI).
            if "-" in (locale_code or ""):
                return ""
            root = locale_code.split("-")[0].lower()
            matches = [lid for code, lid in loc_map.items() if code and code.split("-")[0].lower() == root]
            return matches[0] if len(matches) == 1 else ""

        for loc, data in results.items():
            loc_id = existing_locale_ids.get(loc)
            if not loc_id:
                # Attempt a pre-flight unique root match before creation (e.g., fi vs fi-FI)
                loc_id = _unique_root_match(existing_locale_ids, loc)

            # Skip update if current values already match desired ones
            if loc_id:
                current_attrs = existing_locale_attrs.get(loc, {})
                current_name = current_attrs.get("name")
                current_desc = current_attrs.get("description") if scope == "sub" else current_attrs.get("customAppName")
                desired_name = data.get("name")
                desired_desc = data.get("description") if scope == "sub" else data.get("customAppName")
                if current_name == desired_name and (desired_desc is None or current_desc == desired_desc):
                    success += 1
                    completed += 1
                    try:
                        line = format_progress(completed, total_targets, f"Saved {APP_STORE_LOCALES.get(loc, loc)}")
                        pad = max(0, last_progress_len - len(line))
                        print("\r" + line + (" " * pad), end="")
                        last_progress_len = len(line)
                    except Exception:
                        pass
                    continue
            try:
                if scope == "sub":
                    if loc_id:
                        asc.update_subscription_localization(loc_id, data.get("name"), data.get("description"))
                    else:
                        time.sleep(0.25)
                        asc.create_subscription_localization(sub.get("id"), loc, data.get("name", ""), data.get("description"))
                        _refresh_locale_ids()
                    existing_locale_attrs[loc] = {"name": data.get("name"), "description": data.get("description")}
                else:
                    if loc_id:
                        asc.update_subscription_group_localization(loc_id, data.get("name"), data.get("customAppName"))
                    else:
                        time.sleep(0.25)
                        asc.create_subscription_group_localization(sub.get("id"), loc, data.get("name", ""), data.get("customAppName"))
                        _refresh_locale_ids()
                    existing_locale_attrs[loc] = {"name": data.get("name"), "customAppName": data.get("customAppName")}
                success += 1
                completed += 1
                try:
                    line = format_progress(completed, total_targets, f"Saved {APP_STORE_LOCALES.get(loc, loc)}")
                    pad = max(0, last_progress_len - len(line))
                    print("\r" + line + (" " * pad), end="")
                    last_progress_len = len(line)
                except Exception:
                    pass
            except Exception as e:
                if "409" in str(e):
                    try:
                        refreshed = asc.get_subscription_localizations(sub.get("id")) if scope == "sub" else asc.get_subscription_group_localizations(sub.get("id"))
                        refreshed_map = {l.get("attributes", {}).get("locale"): l.get("id") for l in refreshed.get("data", []) if l.get("id")}
                        refreshed_attrs = {l.get("attributes", {}).get("locale"): (l.get("attributes", {}) or {}) for l in refreshed.get("data", []) if l.get("attributes")}
                        loc_obj = next((l for l in refreshed.get("data", []) if l.get("attributes", {}).get("locale") == loc), None)
                        if not loc_obj:
                            # Try unique language-root match only when unambiguous (avoid en-US/en-GB conflicts)
                            if "-" not in (loc or ""):
                                root = loc.split("-")[0].lower()
                                candidates = [
                                    l for l in refreshed.get("data", [])
                                    if l.get("attributes", {}).get("locale", "").split("-")[0].lower() == root
                                ]
                                loc_obj = candidates[0] if len(candidates) == 1 else None
                        if loc_obj:
                            attrs = loc_obj.get("attributes", {})
                            desired_name = data.get("name")
                            desired_desc = data.get("description") if scope == "sub" else data.get("customAppName")
                            current_desc = attrs.get("description") if scope == "sub" else attrs.get("customAppName")
                            if attrs.get("name") == desired_name and (desired_desc is None or current_desc == desired_desc):
                                success += 1
                                existing_locale_ids[loc] = loc_obj.get("id") or existing_locale_ids.get(loc, "")
                                if loc_obj.get("attributes", {}).get("locale"):
                                    existing_locale_attrs[loc_obj.get("attributes", {}).get("locale")] = attrs
                                continue
                        new_id = refreshed_map.get(loc) or _unique_root_match(refreshed_map, loc)
                        if new_id:
                            if scope == "sub":
                                asc.update_subscription_localization(new_id, data.get("name"), data.get("description"))
                            else:
                                asc.update_subscription_group_localization(new_id, data.get("name"), data.get("customAppName"))
                            success += 1
                            existing_locale_ids[loc] = new_id
                            if refreshed_attrs.get(loc):
                                existing_locale_attrs[loc] = refreshed_attrs.get(loc)
                            completed += 1
                            try:
                                line = format_progress(completed, total_targets, f"Saved {APP_STORE_LOCALES.get(loc, loc)}")
                                pad = max(0, last_progress_len - len(line))
                                print("\r" + line + (" " * pad), end="")
                                last_progress_len = len(line)
                            except Exception:
                                pass
                            continue
                        # If we still don't have an ID, check direct fetch by loc_id when we had one and see if it already matches
                        if loc_id:
                            try:
                                fetched = asc.get_subscription_localization(loc_id) if scope == "sub" else asc.get_subscription_group_localization(loc_id)
                                f_attrs = fetched.get("data", {}).get("attributes", {}) if isinstance(fetched, dict) else {}
                                desired_name = data.get("name")
                                desired_desc = data.get("description") if scope == "sub" else data.get("customAppName")
                                current_desc = f_attrs.get("description") if scope == "sub" else f_attrs.get("customAppName")
                                if f_attrs.get("name") == desired_name and (desired_desc is None or current_desc == desired_desc):
                                    success += 1
                                    existing_locale_attrs[loc] = f_attrs
                                    completed += 1
                                    try:
                                        line = format_progress(completed, total_targets, f"Saved {APP_STORE_LOCALES.get(loc, loc)}")
                                        pad = max(0, last_progress_len - len(line))
                                        print("\r" + line + (" " * pad), end="")
                                        last_progress_len = len(line)
                                    except Exception:
                                        pass
                                    continue
                            except Exception:
                                pass
                    except Exception:
                        pass
                language_name = APP_STORE_LOCALES.get(loc, loc)
                print_error(f"  ❌ Failed to save {language_name}: {e}")

        try:
            print("\r" + (" " * last_progress_len) + "\r", end="")
        except Exception:
            pass
        print_success(f"Saved {success}/{len(target_locales)} locales for {label}")

    input("\nPress Enter to continue...")
    return True
