"""
Game Center localization workflow.

Translates Game Center localizations (achievements, leaderboards, activities, challenges).
"""

import time
import os
from urllib.parse import urlparse

import requests
from typing import Dict, List, Optional, Tuple

from utils import (
    APP_STORE_LOCALES,
    detect_base_language,
    print_info,
    print_warning,
    print_error,
    print_success,
    parallel_map_locales,
    provider_model_info,
    format_progress,
)


def _pick_provider(cli):
    manager = cli.ai_manager
    ui = cli.ui
    provs = manager.list_providers()
    if not provs:
        print_error("No AI providers configured. Run setup first.")
        return None, None

    selected_provider = None
    if len(provs) == 1:
        selected_provider = provs[0]
        print_info(f"Using AI provider: {selected_provider}")
    else:
        default_provider = getattr(cli, "config", None).get_default_ai_provider() if getattr(cli, "config", None) else None
        if default_provider and default_provider in provs:
            use_default = ui.confirm(f"Use default AI provider: {default_provider}?", True)
            if use_default is None:
                raw = input(f"Use default provider '{default_provider}'? (Y/n): ").strip().lower()
                use_default = raw in ("", "y", "yes")
            if use_default:
                selected_provider = default_provider
        if not selected_provider:
            if ui.available():
                selected_provider = ui.select(
                    "Select AI provider",
                    [{"name": p + ("  (default)" if p == default_provider else ""), "value": p} for p in provs],
                    add_back=True,
                )
            if not selected_provider:
                for i, p in enumerate(provs, 1):
                    star = " *" if p == default_provider else ""
                    print(f"{i}. {p}{star}")
                raw = input("Select provider (number) (Enter = default): ").strip()
                if not raw and default_provider and default_provider in provs:
                    selected_provider = default_provider
                else:
                    try:
                        idx = int(raw)
                        selected_provider = provs[idx - 1]
                    except Exception:
                        print_error("Invalid selection")
                        return None, None
    provider = manager.get_provider(selected_provider)
    return provider, selected_provider


def _choose_resource_types(ui) -> List[str]:
    choices = [
        {"name": "🏆 Achievements", "value": "achievement"},
        {"name": "📊 Leaderboards", "value": "leaderboard"},
        {"name": "🎮 Activities", "value": "activity"},
        {"name": "🎯 Challenges", "value": "challenge"},
    ]
    if ui.available():
        selected = ui.checkbox("Select Game Center resources", choices, add_back=True) or []
        return selected

    print("1) Achievements\n2) Leaderboards\n3) Activities\n4) Challenges")
    raw = input("Select resources (comma-separated, e.g., 1,2,3): ").strip()
    if not raw:
        return []
    selected = []
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
        label = f"{name}  [{vendor_id}]"
    if kind == "achievement":
        points = attrs.get("points")
        if points is not None:
            label += f" — {points} pts"
    if kind == "challenge":
        challenge_type = attrs.get("challengeType")
        if challenge_type:
            label += f" — {challenge_type}"
    if kind == "activity":
        play_style = attrs.get("playStyle")
        if play_style:
            label += f" — {play_style}"
    return label


def _merge_items(detail_items: List[Dict], group_items: List[Dict]) -> List[Dict]:
    merged: Dict[str, Dict] = {}
    for item in detail_items + group_items:
        item_id = item.get("id")
        if item_id:
            merged[item_id] = item
    return list(merged.values())


def _parse_version_string(value: str):
    if not value:
        return None
    parts = value.split(".")
    nums = []
    for part in parts:
        if not part.isdigit():
            return None
        nums.append(int(part))
    return tuple(nums)


def _pick_latest_version(versions: List[Dict]) -> Optional[Dict]:
    if not versions:
        return None
    numeric = []
    fallback = []
    for v in versions:
        attrs = v.get("attributes", {})
        ver = attrs.get("version") or ""
        parsed = _parse_version_string(ver)
        if parsed is not None:
            numeric.append((parsed, v))
        else:
            fallback.append((ver, v))
    if numeric:
        numeric.sort()
        return numeric[-1][1]
    if fallback:
        fallback.sort()
        return fallback[-1][1]
    return None


def _image_url_from_asset(asset: Dict) -> Optional[str]:
    template = (asset or {}).get("templateUrl")
    if not template:
        return None
    width = (asset or {}).get("width")
    height = (asset or {}).get("height")
    url = template
    if width is not None:
        url = url.replace("{w}", str(width))
    if height is not None:
        url = url.replace("{h}", str(height))
    return url


def _filename_from_url(url: str) -> str:
    try:
        path = urlparse(url).path
        name = os.path.basename(path)
        if name and "." in name:
            return name
    except Exception:
        pass
    return "game_center_image.png"


def _upload_operations(upload_ops: List[Dict], data: bytes, content_type: Optional[str] = None) -> None:
    if not upload_ops:
        raise Exception("No upload operations returned")
    total_len = len(data)
    for op in upload_ops:
        method = op.get("method") or "PUT"
        url = op.get("url")
        if not url:
            raise Exception("Upload operation missing URL")
        offset = op.get("offset") or 0
        length = op.get("length") or len(data)
        headers = {}
        for h in op.get("requestHeaders") or []:
            name = h.get("name")
            value = h.get("value")
            if name and value is not None:
                headers[name] = value
        if content_type:
            has_ct = any(k.lower() == "content-type" for k in headers)
            if not has_ct:
                headers["Content-Type"] = content_type
        if offset > total_len:
            raise Exception(f"Upload operation offset {offset} exceeds data length {total_len}")
        end = min(total_len, offset + length)
        chunk = data[offset:end]
        resp = requests.request(method, url, data=chunk, headers=headers)
        resp.raise_for_status()


def _fetch_image_resource(asc, kind: str, localization_id: str) -> Optional[Dict]:
    try:
        if kind == "achievement":
            resp = asc.get_game_center_achievement_localization_image(localization_id)
        elif kind == "leaderboard":
            resp = asc.get_game_center_leaderboard_localization_image(localization_id)
        elif kind == "activity":
            resp = asc.get_game_center_activity_localization_image(localization_id)
        else:
            resp = asc.get_game_center_challenge_localization_image(localization_id)
        data = resp.get("data") if isinstance(resp, dict) else None
        if data:
            return data
    except Exception:
        pass

    # Fallback to relationship linkage + image by id
    try:
        if kind == "achievement":
            link = asc.get_game_center_achievement_localization_image_linkage(localization_id)
            img_id = (link.get("data") or {}).get("id")
            if img_id:
                resp = asc.get_game_center_achievement_image(img_id)
                return (resp or {}).get("data")
        elif kind == "leaderboard":
            link = asc.get_game_center_leaderboard_localization_image_linkage(localization_id)
            img_id = (link.get("data") or {}).get("id")
            if img_id:
                resp = asc.get_game_center_leaderboard_image(img_id)
                return (resp or {}).get("data")
        elif kind == "activity":
            link = asc.get_game_center_activity_localization_image_linkage(localization_id)
            img_id = (link.get("data") or {}).get("id")
            if img_id:
                resp = asc.get_game_center_activity_image(img_id)
                return (resp or {}).get("data")
        else:
            link = asc.get_game_center_challenge_localization_image_linkage(localization_id)
            img_id = (link.get("data") or {}).get("id")
            if img_id:
                resp = asc.get_game_center_challenge_image(img_id)
                return (resp or {}).get("data")
    except Exception:
        return None
    return None


def _create_image_resource(asc, kind: str, localization_id: str, version_id: Optional[str], file_name: str, file_size: int) -> Dict:
    if kind == "achievement":
        return asc.create_game_center_achievement_image(localization_id, file_name, file_size)
    if kind == "leaderboard":
        return asc.create_game_center_leaderboard_image(localization_id, file_name, file_size)
    if kind == "activity":
        if not version_id:
            raise Exception("Missing activity version id for image upload")
        return asc.create_game_center_activity_image(localization_id, version_id, file_name, file_size)
    if not version_id:
        raise Exception("Missing challenge version id for image upload")
    return asc.create_game_center_challenge_image(localization_id, version_id, file_name, file_size)


def _ext_from_content_type(content_type: Optional[str]) -> Optional[str]:
    if not content_type:
        return None
    ct = content_type.split(";")[0].strip().lower()
    if ct == "image/png":
        return "png"
    if ct == "image/jpeg":
        return "jpg"
    if ct == "image/jpg":
        return "jpg"
    if ct == "image/webp":
        return "webp"
    if ct == "image/gif":
        return "gif"
    return None


def _download_origin_image(origin_image: Dict) -> Tuple[Optional[bytes], Optional[str], Optional[str], str, Optional[str]]:
    asset = origin_image.get("attributes", {}).get("imageAsset") or {}
    template = (asset or {}).get("templateUrl")
    url = _image_url_from_asset(asset)
    if not url and not template:
        return None, None, None, "no_asset_url", None

    urls_to_try = []
    if url:
        urls_to_try.append(url)
    if template:
        file_name = origin_image.get("attributes", {}).get("fileName") or ""
        fmt = "png"
        if "." in file_name:
            ext = file_name.rsplit(".", 1)[-1].strip().lower()
            if ext:
                fmt = ext
        size_candidates = []
        asset_w = (asset or {}).get("width")
        asset_h = (asset or {}).get("height")
        if asset_w and asset_h:
            size_candidates.append((int(asset_w), int(asset_h)))
        size_candidates += [(1024, 1024), (512, 512), (256, 256)]
        for w, h in size_candidates:
            candidate = (
                template.replace("{w}", str(w))
                .replace("{h}", str(h))
                .replace("{f}", fmt)
            )
            if candidate not in urls_to_try:
                urls_to_try.append(candidate)
        if "{" in template:
            try:
                import re
                fallback = re.sub(r"\{[^}]+\}", "512", template)
                if fallback not in urls_to_try:
                    urls_to_try.append(fallback)
            except Exception:
                pass

    last_err = None
    for candidate in urls_to_try:
        try:
            resp = requests.get(candidate, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            data = resp.content
            content_type = resp.headers.get("Content-Type")
            file_name = origin_image.get("attributes", {}).get("fileName") or _filename_from_url(candidate)
            ext = _ext_from_content_type(content_type)
            if ext and "." in file_name:
                base = file_name.rsplit(".", 1)[0]
                file_name = f"{base}.{ext}"
            elif ext and "." not in file_name:
                file_name = f"{file_name}.{ext}"
            return data, file_name, content_type, "ok", None
        except Exception as e:
            last_err = f"{candidate} -> {e}"
            continue
    return None, None, None, "download_failed", last_err


def _copy_localization_image(
    asc,
    kind: str,
    origin_payload: Optional[Tuple[bytes, str, Optional[str]]],
    target_localization_id: Optional[str],
    version_id: Optional[str],
) -> Tuple[str, Optional[str], Optional[str]]:
    if not target_localization_id:
        return "no_target_id", None, None
    if not origin_payload:
        return "no_origin_payload", None, None
    # Skip if target already has an image
    target_img = _fetch_image_resource(asc, kind, target_localization_id)
    if target_img:
        return "target_has_image", None, None

    data, file_name, content_type = origin_payload
    file_size = len(data)
    created = _create_image_resource(asc, kind, target_localization_id, version_id, file_name, file_size)
    image_id = (created.get("data") or {}).get("id")
    upload_ops = created.get("data", {}).get("attributes", {}).get("uploadOperations") or []
    if not upload_ops:
        return "no_upload_ops", None, image_id
    try:
        _upload_operations(upload_ops, data, content_type=content_type)
    except Exception as e:
        return "upload_failed", str(e), image_id

    # Commit the upload by PATCHing the image resource
    if image_id:
        try:
            if kind == "achievement":
                asc.update_game_center_achievement_image(image_id, uploaded=True)
            elif kind == "leaderboard":
                asc.update_game_center_leaderboard_image(image_id, uploaded=True)
            elif kind == "activity":
                asc.update_game_center_activity_image(image_id, uploaded=True)
            else:  # challenge
                asc.update_game_center_challenge_image(image_id, uploaded=True)
        except Exception as e:
            return "commit_failed", f"Upload succeeded but commit failed: {e}", image_id

    return "upload_complete", None, image_id




def _select_items(ui, items: List[Dict], kind: str) -> List[Dict]:
    if not items:
        print_warning(f"No {kind}s found")
        return []

    choices = [
        {"name": _label_item(item, kind), "value": item.get("id")}
        for item in items
        if item.get("id")
    ]

    selected_ids: List[str] = []
    if ui.available():
        selected_ids = ui.checkbox(
            f"Select {kind}s to localize (Space to toggle, Enter to confirm)",
            choices,
            add_back=True,
        ) or []
    else:
        print(f"Available {kind}s:")
        for idx, choice in enumerate(choices, 1):
            print(f"{idx:2d}. {choice['name']}")
        raw = input("Enter numbers (comma-separated) or 'all': ").strip()
        if raw.lower() in ("all", "*"):
            selected_ids = [c["value"] for c in choices]
        elif raw:
            try:
                nums = [int(x) for x in raw.replace(" ", "").split(",") if x]
                for n in nums:
                    if 1 <= n <= len(choices):
                        selected_ids.append(choices[n - 1]["value"])
            except Exception:
                selected_ids = []

    if not selected_ids:
        print_warning(f"No {kind}s selected")
        return []

    selected = [item for item in items if item.get("id") in selected_ids]
    if not selected:
        missing = ", ".join(selected_ids)
        print_warning(f"Selected {kind}s not found in response: {missing}")
    return selected


def _select_base_locale(ui, available_locales: List[str], recommended: Optional[str]) -> Optional[str]:
    if not available_locales:
        return None

    recommended = recommended if recommended in available_locales else None
    ordered = list(available_locales)
    if recommended and recommended in ordered:
        ordered.remove(recommended)
        ordered = [recommended] + ordered

    if ui.available():
        choices = []
        for loc in ordered:
            name = APP_STORE_LOCALES.get(loc, loc)
            label = f"{loc} - {name}"
            if recommended and loc == recommended:
                label += " (recommended)"
            choices.append({"name": label, "value": loc})
        return ui.select("Select base locale", choices, add_back=True)

    print("Available base locales:")
    for idx, loc in enumerate(ordered, 1):
        name = APP_STORE_LOCALES.get(loc, loc)
        rec = " (recommended)" if recommended and loc == recommended else ""
        print(f"{idx:2d}. {loc} - {name}{rec}")
    prompt = f"Select base locale (Enter = {recommended}): " if recommended else "Select base locale (number): "
    raw = input(prompt).strip()
    if not raw and recommended:
        return recommended
    try:
        idx = int(raw)
        if 1 <= idx <= len(ordered):
            return ordered[idx - 1]
    except Exception:
        pass
    return None


def _choose_targets(ui, available_targets: List[str], base_locale: str, preferred_locales=None) -> List[str]:
    preferred_locales = set(preferred_locales or [])
    if not available_targets:
        print_warning("All supported languages are already localized for the selected items")
        return []

    default_checked = {loc for loc in available_targets if loc in preferred_locales}

    if ui.available():
        choices = [
            {"name": "🌐 Select all available locales", "value": "__all__"},
            {"name": "📝 Manual entry (comma-separated locales)", "value": "__manual__"},
        ]
        choices += [
            {"name": f"{loc} - {APP_STORE_LOCALES.get(loc, loc)}", "value": loc, "enabled": loc in default_checked}
            for loc in available_targets
        ]
        selected = ui.checkbox("Select target locales", choices, add_back=True) or []
        if "__all__" in selected:
            return [loc for loc in available_targets if loc != base_locale]
        if "__manual__" in selected or not selected:
            selected = []
        if selected:
            return [s for s in selected if s in available_targets]
        raw = input("Enter target locales (comma-separated): ").strip()
        if not raw:
            return []
        return [s.strip() for s in raw.split(',') if s.strip() in available_targets]

    print("Available target locales:")
    items = list(available_targets)
    col_width = 28
    for i in range(0, len(items), 2):
        left = items[i]
        right = items[i + 1] if i + 1 < len(items) else None
        left_txt = f"{left:8} - {APP_STORE_LOCALES.get(left, left)}".ljust(col_width)
        right_txt = f"{right:8} - {APP_STORE_LOCALES.get(right, right)}" if right else ""
        print(f"{left_txt} {right_txt}")
    default_list = sorted(default_checked)
    raw = input("Enter target locales (comma-separated, 'all' for every locale, Enter = app locales): ").strip()
    if not raw:
        return default_list if default_list else []
    if raw.lower() in ("all", "*"):
        return [loc for loc in available_targets if loc != base_locale]
    selected = [s.strip() for s in raw.split(',') if s.strip() in available_targets]
    return selected or default_list


def _translate_required(provider, text: str, language_name: str, refine_phrase: str, seed: Optional[int], field_label: str) -> str:
    translated = provider.translate(text, language_name, seed=seed, refinement=refine_phrase) or ""
    if translated.strip():
        return translated.strip()
    stronger = (refine_phrase or "").strip()
    extra = f" Do not return an empty string. Return ONLY the translated text for the {field_label}."
    stronger = (stronger + extra).strip() if stronger else extra.strip()
    translated = provider.translate(text, language_name, seed=seed, refinement=stronger) or ""
    return translated.strip()


def run(cli) -> bool:
    ui = cli.ui
    asc = cli.asc_client

    print_info("Game Center Localizations - Achievements, Leaderboards, Activities, Challenges")

    def _confirm_continue_after_image_failure(message: str) -> bool:
        if ui.available():
            return bool(ui.confirm(message, False))
        raw = input(f"{message} (y/N): ").strip().lower()
        return raw in ("y", "yes")

    app_id = ui.prompt_app_id(asc)
    if app_id is None:
        print_info("Cancelled")
        return True

    detail_resp = asc.get_game_center_detail(app_id)
    detail = detail_resp.get("data") if isinstance(detail_resp, dict) else None
    if not detail:
        print_error("Game Center detail not found for this app")
        return True
    detail_id = detail.get("id")
    if not detail_id:
        print_error("Game Center detail ID missing")
        return True

    group_id = None
    try:
        group_resp = asc.get_game_center_group(detail_id)
        group = group_resp.get("data") if isinstance(group_resp, dict) else None
        group_id = group.get("id") if isinstance(group, dict) else None
    except Exception:
        group_id = None

    include_group = False
    if group_id:
        if ui.available():
            include_group = bool(ui.confirm("Include Game Center Group shared items?", True))
        else:
            raw = input("Include Game Center Group shared items? (Y/n): ").strip().lower()
            include_group = raw in ("", "y", "yes")
        if include_group:
            print_info("Including Game Center Group shared items")

    selected_types = _choose_resource_types(ui)
    if not selected_types:
        print_warning("No resources selected")
        return True

    selected_items: List[Tuple[str, Dict]] = []
    if "achievement" in selected_types:
        achievements = asc.get_game_center_achievements(detail_id).get("data", [])
        group_achievements = []
        if include_group and group_id:
            group_achievements = asc.get_game_center_group_achievements(group_id).get("data", [])
        achievements = _merge_items(achievements, group_achievements)
        picked = _select_items(ui, achievements, "achievement")
        selected_items += [("achievement", item) for item in picked]
    if "leaderboard" in selected_types:
        leaderboards = asc.get_game_center_leaderboards(detail_id).get("data", [])
        group_leaderboards = []
        if include_group and group_id:
            group_leaderboards = asc.get_game_center_group_leaderboards(group_id).get("data", [])
        leaderboards = _merge_items(leaderboards, group_leaderboards)
        picked = _select_items(ui, leaderboards, "leaderboard")
        selected_items += [("leaderboard", item) for item in picked]
    if "activity" in selected_types:
        activities = asc.get_game_center_activities(detail_id).get("data", [])
        group_activities = []
        if include_group and group_id:
            group_activities = asc.get_game_center_group_activities(group_id).get("data", [])
        activities = _merge_items(activities, group_activities)
        picked = _select_items(ui, activities, "activity")
        selected_items += [("activity", item) for item in picked]
    if "challenge" in selected_types:
        challenges = asc.get_game_center_challenges(detail_id).get("data", [])
        group_challenges = []
        if include_group and group_id:
            group_challenges = asc.get_game_center_group_challenges(group_id).get("data", [])
        challenges = _merge_items(challenges, group_challenges)
        picked = _select_items(ui, challenges, "challenge")
        selected_items += [("challenge", item) for item in picked]

    if not selected_items:
        return True

    provider, provider_key = _pick_provider(cli)
    if not provider:
        return True
    refine_phrase = (getattr(cli, "config", None).get_prompt_refinement() if getattr(cli, "config", None) else "") or ""
    seed = getattr(cli, "session_seed", None)
    pname, pmodel = provider_model_info(provider, provider_key)
    print_info(f"AI provider: {pname} — model: {pmodel or 'n/a'} — seed: {seed}")

    # Collect app locales to pre-fill targets
    app_locales = set()
    try:
        latest_ver = asc.get_latest_app_store_version(app_id)
        if latest_ver:
            locs = asc.get_app_store_version_localizations(latest_ver).get("data", [])
            app_locales = {l.get("attributes", {}).get("locale") for l in locs if l.get("attributes", {}).get("locale")}
    except Exception:
        app_locales = set()

    # Load localizations for base locale selection
    item_records = []
    all_localizations = []
    locale_sets = []
    for kind, item in selected_items:
        item_id = item.get("id")
        if not item_id:
            continue
        version_id = None
        version_label = None
        if kind == "achievement":
            loc_resp = asc.get_game_center_achievement_localizations(item_id)
        elif kind == "leaderboard":
            loc_resp = asc.get_game_center_leaderboard_localizations(item_id)
        elif kind == "activity":
            versions_resp = asc.get_game_center_activity_versions(item_id)
            versions = versions_resp.get("data", []) if isinstance(versions_resp, dict) else []
            latest = _pick_latest_version(versions)
            if not latest:
                print_warning(f"No versions found for {_label_item(item, kind)}; skipping")
                continue
            version_id = latest.get("id")
            version_label = latest.get("attributes", {}).get("version")
            if not version_id:
                print_warning(f"Latest version missing id for {_label_item(item, kind)}; skipping")
                continue
            loc_resp = asc.get_game_center_activity_version_localizations(version_id)
        else:
            versions_resp = asc.get_game_center_challenge_versions(item_id)
            versions = versions_resp.get("data", []) if isinstance(versions_resp, dict) else []
            latest = _pick_latest_version(versions)
            if not latest:
                print_warning(f"No versions found for {_label_item(item, kind)}; skipping")
                continue
            version_id = latest.get("id")
            version_label = latest.get("attributes", {}).get("version")
            if not version_id:
                print_warning(f"Latest version missing id for {_label_item(item, kind)}; skipping")
                continue
            loc_resp = asc.get_game_center_challenge_version_localizations(version_id)
        localizations = loc_resp.get("data", []) if isinstance(loc_resp, dict) else []
        if not localizations:
            label = _label_item(item, kind)
            if version_label:
                label = f"{label} v{version_label}"
            print_warning(f"No existing localizations found for {label}; skipping")
            continue
        item_records.append({
            "kind": kind,
            "item": item,
            "localizations": localizations,
            "version_id": version_id,
            "version_label": version_label,
        })
        all_localizations.extend(localizations)
        locales = {l.get("attributes", {}).get("locale") for l in localizations if l.get("attributes", {}).get("locale")}
        if locales:
            locale_sets.append(locales)

    if not item_records or not locale_sets:
        print_warning("No items with localizations available for base locale selection")
        return True

    union_locales = set()
    for s in locale_sets:
        union_locales.update(s)
    intersection_locales = set(locale_sets[0])
    for s in locale_sets[1:]:
        intersection_locales &= s

    suggested_base = detect_base_language(all_localizations)
    base_choices = sorted(intersection_locales) if intersection_locales else sorted(union_locales)
    if not intersection_locales:
        print_warning("No single locale exists across all selected items; items missing the base locale will be skipped")
    base_locale = _select_base_locale(ui, base_choices, suggested_base)
    if not base_locale:
        print_warning("No base locale selected")
        return True
    print_info(f"Base locale: {base_locale} ({APP_STORE_LOCALES.get(base_locale, 'Unknown')})")

    supported_locales = set(APP_STORE_LOCALES.keys())
    missing_union = set()
    for record in item_records:
        existing = {l.get("attributes", {}).get("locale") for l in record["localizations"] if l.get("attributes", {}).get("locale")}
        missing = {loc for loc in supported_locales if loc != base_locale and loc not in existing}
        missing_union.update(missing)

    target_locales = _choose_targets(ui, sorted(missing_union), base_locale, preferred_locales=app_locales)
    if not target_locales:
        print_warning("No target locales selected")
        return True

    total_translated = 0
    for idx, record in enumerate(item_records, 1):
        kind = record["kind"]
        item = record["item"]
        localizations = record["localizations"]
        version_id = record.get("version_id")
        version_label = record.get("version_label")
        item_id = item.get("id")
        label = _label_item(item, kind)
        if version_label:
            label = f"{label} v{version_label}"

        print()
        print_info(f"({idx}/{len(item_records)}) Processing {label}")

        base_attrs = next(
            (l.get("attributes", {}) for l in localizations if l.get("attributes", {}).get("locale") == base_locale),
            None,
        )
        base_loc = next(
            (l for l in localizations if l.get("attributes", {}).get("locale") == base_locale),
            None,
        )
        base_loc_id = base_loc.get("id") if isinstance(base_loc, dict) else None
        if not base_attrs:
            print_warning(f"Base locale {base_locale} not found for {label}; skipping")
            continue
        base_image = None
        origin_payload = None
        if base_loc_id:
            base_image = _fetch_image_resource(asc, kind, base_loc_id)
        if not base_image:
            print_warning(f"No base image found for {label}; image copy will be skipped")
        else:
            data, file_name, content_type, status, err = _download_origin_image(base_image)
            if status == "ok" and data and file_name:
                origin_payload = (data, file_name, content_type)
            elif status == "download_failed":
                detail = f" ({err})" if err else ""
                proceed = _confirm_continue_after_image_failure(
                    f"Image download failed for base locale {base_locale}{detail}. Continue?"
                )
                if not proceed:
                    print_warning("Aborted by user.")
                    return True
                print_warning(f"Image download failed for base locale {base_locale}; image copy will be skipped")
            else:
                print_warning(f"Image copy skipped for {label}: {status}")

        existing_locale_ids: Dict[str, str] = {
            l.get("attributes", {}).get("locale"): l.get("id")
            for l in localizations
            if l.get("id") and l.get("attributes", {}).get("locale")
        }
        missing_locales = [loc for loc in target_locales if loc not in existing_locale_ids]
        if not missing_locales:
            print_warning("No missing locales for this item")
            continue

        if kind == "achievement":
            base_name = (base_attrs.get("name") or "").strip()
            base_before = (base_attrs.get("beforeEarnedDescription") or "").strip()
            base_after = (base_attrs.get("afterEarnedDescription") or "").strip()
            if not (base_name and base_before and base_after):
                print_error("Base localization missing required fields (name/before/after); skipping")
                continue

            def _task(loc: str):
                language_name = APP_STORE_LOCALES.get(loc, loc)
                translated = {
                    "name": _translate_required(provider, base_name, language_name, refine_phrase, seed, "name"),
                    "before": _translate_required(provider, base_before, language_name, refine_phrase, seed, "before-earned description"),
                    "after": _translate_required(provider, base_after, language_name, refine_phrase, seed, "after-earned description"),
                }
                time.sleep(1)
                return translated

            results, errs = parallel_map_locales(missing_locales, _task, progress_action="Translated", pacing_seconds=0.0)

            success_count = 0
            total_targets = len(missing_locales)
            completed = 0
            last_progress_len = 0
            try:
                line = format_progress(0, total_targets, "Saving locales...")
                print(line, end="\r")
                last_progress_len = len(line)
            except Exception:
                pass

            for loc, data in results.items():
                name = (data.get("name") or "").strip()
                before = (data.get("before") or "").strip()
                after = (data.get("after") or "").strip()
                if not (name and before and after):
                    language_name = APP_STORE_LOCALES.get(loc, loc)
                    print_error(f"  ❌ Skipping {language_name}: required fields are empty")
                    completed += 1
                    try:
                        line = format_progress(completed, total_targets, f"Skipped {APP_STORE_LOCALES.get(loc, loc)}")
                        pad = max(0, last_progress_len - len(line))
                        print("\r" + line + (" " * pad), end="")
                        last_progress_len = len(line)
                    except Exception:
                        pass
                    continue

                language_name = APP_STORE_LOCALES.get(loc, loc)
                target_loc_id = existing_locale_ids.get(loc)
                saved = False
                try:
                    created = asc.create_game_center_achievement_localization(
                        achievement_id=item_id,
                        locale=loc,
                        name=name,
                        before_earned_description=before,
                        after_earned_description=after,
                    )
                    target_loc_id = created.get("data", {}).get("id") or target_loc_id
                    saved = True
                except Exception as e:
                    if "409" in str(e):
                        try:
                            refreshed = asc.get_game_center_achievement_localizations(item_id)
                            refreshed_map = {l.get("attributes", {}).get("locale"): l.get("id") for l in refreshed.get("data", [])}
                            loc_id = refreshed_map.get(loc)
                            if loc_id:
                                target_loc_id = loc_id
                                asc.update_game_center_achievement_localization(
                                    loc_id,
                                    name=name,
                                    before_earned_description=before,
                                    after_earned_description=after,
                                )
                                saved = True
                            else:
                                raise
                        except Exception:
                            print_error(f"  ❌ Failed to save {language_name}: {e}")
                    else:
                        print_error(f"  ❌ Failed to save {language_name}: {e}")

                if saved:
                    success_count += 1
                    result, err, image_id = _copy_localization_image(asc, kind, origin_payload, target_loc_id, version_id)
                    if result == "commit_failed":
                        print_error(f"  ❌ Image commit failed for {language_name}: {err}")
                    if result not in ("upload_complete", "target_has_image", "commit_failed"):
                        detail = f" ({err})" if err else ""
                        print_warning(f"  ⚠️  Image copy skipped for {language_name}: {result}{detail}")
                completed += 1
                try:
                    status = "Saved" if saved else "Failed"
                    line = format_progress(completed, total_targets, f"{status} {language_name}")
                    pad = max(0, last_progress_len - len(line))
                    print("\r" + line + (" " * pad), end="")
                    last_progress_len = len(line)
                except Exception:
                    pass

            if errs:
                print()
                print_warning(f"{len(errs)} locales failed for {label}")
            try:
                print("\r" + (" " * last_progress_len) + "\r", end="")
            except Exception:
                pass
            total_translated += success_count
            print_success(f"Saved {success_count}/{len(missing_locales)} locales for {label}")

        elif kind == "leaderboard":
            base_name = (base_attrs.get("name") or "").strip()
            base_desc = (base_attrs.get("description") or "").strip()
            base_suffix = (base_attrs.get("formatterSuffix") or "").strip()
            base_suffix_singular = (base_attrs.get("formatterSuffixSingular") or "").strip()
            base_override = base_attrs.get("formatterOverride")
            if not base_name:
                print_error("Base localization missing required name; skipping")
                continue

            def _task(loc: str):
                language_name = APP_STORE_LOCALES.get(loc, loc)
                translated = {
                    "name": _translate_required(provider, base_name, language_name, refine_phrase, seed, "name"),
                    "description": provider.translate(base_desc, language_name, seed=seed, refinement=refine_phrase).strip() if base_desc else "",
                    "formatterSuffix": provider.translate(base_suffix, language_name, seed=seed, refinement=refine_phrase).strip() if base_suffix else "",
                    "formatterSuffixSingular": provider.translate(base_suffix_singular, language_name, seed=seed, refinement=refine_phrase).strip() if base_suffix_singular else "",
                }
                time.sleep(1)
                return translated

            results, errs = parallel_map_locales(missing_locales, _task, progress_action="Translated", pacing_seconds=0.0)

            success_count = 0
            total_targets = len(missing_locales)
            completed = 0
            last_progress_len = 0
            try:
                line = format_progress(0, total_targets, "Saving locales...")
                print(line, end="\r")
                last_progress_len = len(line)
            except Exception:
                pass

            for loc, data in results.items():
                name = (data.get("name") or "").strip()
                description = (data.get("description") or "").strip() or None
                formatter_suffix = (data.get("formatterSuffix") or "").strip() or None
                formatter_suffix_singular = (data.get("formatterSuffixSingular") or "").strip() or None
                if not name:
                    language_name = APP_STORE_LOCALES.get(loc, loc)
                    print_error(f"  ❌ Skipping {language_name}: name is empty (required)")
                    completed += 1
                    try:
                        line = format_progress(completed, total_targets, f"Skipped {APP_STORE_LOCALES.get(loc, loc)}")
                        pad = max(0, last_progress_len - len(line))
                        print("\r" + line + (" " * pad), end="")
                        last_progress_len = len(line)
                    except Exception:
                        pass
                    continue

                language_name = APP_STORE_LOCALES.get(loc, loc)
                target_loc_id = existing_locale_ids.get(loc)
                saved = False
                try:
                    created = asc.create_game_center_leaderboard_localization(
                        leaderboard_id=item_id,
                        locale=loc,
                        name=name,
                        description=description,
                        formatter_suffix=formatter_suffix,
                        formatter_suffix_singular=formatter_suffix_singular,
                        formatter_override=base_override,
                    )
                    target_loc_id = created.get("data", {}).get("id") or target_loc_id
                    saved = True
                except Exception as e:
                    if "409" in str(e):
                        try:
                            refreshed = asc.get_game_center_leaderboard_localizations(item_id)
                            refreshed_map = {l.get("attributes", {}).get("locale"): l.get("id") for l in refreshed.get("data", [])}
                            loc_id = refreshed_map.get(loc)
                            if loc_id:
                                target_loc_id = loc_id
                                asc.update_game_center_leaderboard_localization(
                                    loc_id,
                                    name=name,
                                    description=description,
                                    formatter_suffix=formatter_suffix,
                                    formatter_suffix_singular=formatter_suffix_singular,
                                    formatter_override=base_override,
                                )
                                saved = True
                            else:
                                raise
                        except Exception:
                            print_error(f"  ❌ Failed to save {language_name}: {e}")
                    else:
                        print_error(f"  ❌ Failed to save {language_name}: {e}")

                if saved:
                    success_count += 1
                    result, err, image_id = _copy_localization_image(asc, kind, origin_payload, target_loc_id, version_id)
                    if result == "commit_failed":
                        print_error(f"  ❌ Image commit failed for {language_name}: {err}")
                    if result not in ("upload_complete", "target_has_image", "commit_failed"):
                        detail = f" ({err})" if err else ""
                        print_warning(f"  ⚠️  Image copy skipped for {language_name}: {result}{detail}")
                completed += 1
                try:
                    status = "Saved" if saved else "Failed"
                    line = format_progress(completed, total_targets, f"{status} {language_name}")
                    pad = max(0, last_progress_len - len(line))
                    print("\r" + line + (" " * pad), end="")
                    last_progress_len = len(line)
                except Exception:
                    pass

            if errs:
                print()
                print_warning(f"{len(errs)} locales failed for {label}")
            try:
                print("\r" + (" " * last_progress_len) + "\r", end="")
            except Exception:
                pass
            total_translated += success_count
            print_success(f"Saved {success_count}/{len(missing_locales)} locales for {label}")
        else:
            base_name = (base_attrs.get("name") or "").strip()
            base_desc = (base_attrs.get("description") or "").strip()
            if not base_name:
                print_error("Base localization missing required name; skipping")
                continue
            if not version_id:
                print_error("Missing version id for localized item; skipping")
                continue

            def _task(loc: str):
                language_name = APP_STORE_LOCALES.get(loc, loc)
                translated = {
                    "name": _translate_required(provider, base_name, language_name, refine_phrase, seed, "name"),
                    "description": provider.translate(base_desc, language_name, seed=seed, refinement=refine_phrase).strip() if base_desc else "",
                }
                time.sleep(1)
                return translated

            results, errs = parallel_map_locales(missing_locales, _task, progress_action="Translated", pacing_seconds=0.0)

            success_count = 0
            total_targets = len(missing_locales)
            completed = 0
            last_progress_len = 0
            try:
                line = format_progress(0, total_targets, "Saving locales...")
                print(line, end="\r")
                last_progress_len = len(line)
            except Exception:
                pass

            for loc, data in results.items():
                name = (data.get("name") or "").strip()
                description = (data.get("description") or "").strip() or None
                if not name:
                    language_name = APP_STORE_LOCALES.get(loc, loc)
                    print_error(f"  ❌ Skipping {language_name}: name is empty (required)")
                    completed += 1
                    try:
                        line = format_progress(completed, total_targets, f"Skipped {APP_STORE_LOCALES.get(loc, loc)}")
                        pad = max(0, last_progress_len - len(line))
                        print("\r" + line + (" " * pad), end="")
                        last_progress_len = len(line)
                    except Exception:
                        pass
                    continue

                language_name = APP_STORE_LOCALES.get(loc, loc)
                target_loc_id = existing_locale_ids.get(loc)
                saved = False
                try:
                    if kind == "activity":
                        created = asc.create_game_center_activity_localization(
                            version_id=version_id,
                            locale=loc,
                            name=name,
                            description=description,
                        )
                    else:
                        created = asc.create_game_center_challenge_localization(
                            version_id=version_id,
                            locale=loc,
                            name=name,
                            description=description,
                        )
                    target_loc_id = created.get("data", {}).get("id") or target_loc_id
                    saved = True
                except Exception as e:
                    if "409" in str(e):
                        try:
                            if kind == "activity":
                                refreshed = asc.get_game_center_activity_version_localizations(version_id)
                            else:
                                refreshed = asc.get_game_center_challenge_version_localizations(version_id)
                            refreshed_map = {l.get("attributes", {}).get("locale"): l.get("id") for l in refreshed.get("data", [])}
                            loc_id = refreshed_map.get(loc)
                            if loc_id:
                                target_loc_id = loc_id
                                if kind == "activity":
                                    asc.update_game_center_activity_localization(
                                        loc_id,
                                        name=name,
                                        description=description,
                                    )
                                else:
                                    asc.update_game_center_challenge_localization(
                                        loc_id,
                                        name=name,
                                        description=description,
                                    )
                                saved = True
                            else:
                                raise
                        except Exception:
                            print_error(f"  ❌ Failed to save {language_name}: {e}")
                    else:
                        print_error(f"  ❌ Failed to save {language_name}: {e}")

                if saved:
                    success_count += 1
                    result, err, image_id = _copy_localization_image(asc, kind, origin_payload, target_loc_id, version_id)
                    if result == "commit_failed":
                        print_error(f"  ❌ Image commit failed for {language_name}: {err}")
                    if result not in ("upload_complete", "target_has_image", "commit_failed"):
                        detail = f" ({err})" if err else ""
                        print_warning(f"  ⚠️  Image copy skipped for {language_name}: {result}{detail}")
                completed += 1
                try:
                    status = "Saved" if saved else "Failed"
                    line = format_progress(completed, total_targets, f"{status} {language_name}")
                    pad = max(0, last_progress_len - len(line))
                    print("\r" + line + (" " * pad), end="")
                    last_progress_len = len(line)
                except Exception:
                    pass

            if errs:
                print()
                print_warning(f"{len(errs)} locales failed for {label}")
            try:
                print("\r" + (" " * last_progress_len) + "\r", end="")
            except Exception:
                pass
            total_translated += success_count
            print_success(f"Saved {success_count}/{len(missing_locales)} locales for {label}")

    print()
    if total_translated:
        print_success(f"Created/updated {total_translated} Game Center localizations")
    else:
        print_warning("No Game Center localizations were created")
    return True
