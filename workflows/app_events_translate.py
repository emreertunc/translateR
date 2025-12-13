"""
In-App Events localization translation workflow.

Translates app event localization fields (name, shortDescription, longDescription)
to missing locales using the configured AI provider.
"""

import time
import os
from typing import Dict, List, Optional

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
    format_progress,
)

_DEBUG_APP_EVENTS = os.environ.get("TRANSLATER_DEBUG_APP_EVENTS", "").strip().lower() in ("1", "true", "yes", "y", "on")


def _debug(msg: str) -> None:
    if _DEBUG_APP_EVENTS:
        try:
            print_info(f"[debug] {msg}")
        except Exception:
            print(f"[debug] {msg}")


def _debug_http_error(prefix: str, err: Exception) -> None:
    if not _DEBUG_APP_EVENTS:
        return
    try:
        resp = getattr(err, "response", None)
        status = getattr(resp, "status_code", None)
        body = None
        if resp is not None:
            try:
                body = resp.json()
            except Exception:
                try:
                    body = resp.text
                except Exception:
                    body = None
        _debug(f"{prefix}: status={status} body={body}")
    except Exception:
        _debug(f"{prefix}: {err}")


def _extract_asc_errors(err: Exception) -> List[Dict]:
    """Best-effort extract ASC JSON:API errors from a requests HTTPError."""
    resp = getattr(err, "response", None)
    if resp is None:
        return []
    try:
        body = resp.json()
    except Exception:
        return []
    errors = body.get("errors")
    return errors if isinstance(errors, list) else []


def _has_validation_error(err: Exception) -> bool:
    errors = _extract_asc_errors(err)
    return any((e or {}).get("code") == "ENTITY_ERROR.ATTRIBUTE.INVALID" for e in errors)


def _ensure_min_len(text: str, min_len: int) -> str:
    t = (text or "").strip()
    return t if len(t) >= min_len else ""


def _translate_with_min_len(
    provider,
    source_text: str,
    language_name: str,
    *,
    max_length: int,
    seed: Optional[int],
    refinement: str,
    min_len: int,
    field_label: str,
) -> str:
    """Translate and ensure at least min_len characters, retrying once with stronger guidance."""
    base_guidance = (
        f"Context: App Store in-app event localization field '{field_label}'. "
        f"Return ONLY the translated text (no quotes, no labels, no markdown, no explanations). "
        f"Preserve meaning, marketing tone, and formatting (including newlines). "
        f"Keep app/product names, brand names, URLs, numbers, and placeholders unchanged (e.g., {{var}}, %d, %@). "
        f"Do not output an empty string; minimum length is {min_len} characters."
    )
    if max_length:
        base_guidance += f" Maximum length is {max_length} characters."
    merged_refinement = (refinement or "").strip()
    merged_refinement = (merged_refinement + " " + base_guidance).strip() if merged_refinement else base_guidance

    translated = provider.translate(source_text, language_name, max_length=max_length, seed=seed, refinement=merged_refinement)
    if _ensure_min_len(translated, min_len):
        return translated.strip()

    stronger = merged_refinement + (
        f" Retry: your previous output was too short/empty. "
        f"Translate fully and ensure at least {min_len} characters."
    )
    _debug(f"retry translation field={field_label} locale={language_name} (min_len={min_len})")
    translated = provider.translate(source_text, language_name, max_length=max_length, seed=seed, refinement=stronger)
    return translated.strip()


def _prompt_line(ui, message: str, default: str = "") -> str:
    if ui.available():
        res = ui.text(message)
        if res is not None:
            return res.strip()
    raw = input(f"{message}{' (Enter to keep default)' if default else ''}: ").strip()
    return raw if raw else default


def _select_app_events(ui, asc, app_id: str) -> List[Dict]:
    """Let the user pick one or more in-app events to translate."""
    resp = asc.get_app_events(app_id)
    events = resp.get("data", []) if isinstance(resp, dict) else []
    if not events:
        print_warning("No in-app events found for this app")
        return []

    choices = []
    id_to_event: Dict[str, Dict] = {}
    for e in events:
        attrs = e.get("attributes", {}) or {}
        ref = attrs.get("referenceName") or "Untitled Event"
        badge = attrs.get("badge") or ""
        state = attrs.get("eventState") or ""
        primary = attrs.get("primaryLocale") or ""
        label = ref
        if badge:
            label += f" — {badge}"
        if state:
            label += f" ({state})"
        if primary:
            label += f" [{primary}]"
        choices.append({"name": label, "value": e.get("id")})
        if e.get("id"):
            id_to_event[e.get("id")] = e

    selected_ids: List[str] = []
    if ui.available():
        selected_ids = ui.checkbox(
            "Select in-app events to localize (Space to toggle, Enter to confirm)",
            choices,
            add_back=True,
        ) or []
    else:
        print("Available in-app events:")
        for idx, choice in enumerate(choices, 1):
            print(f"{idx:2d}. {choice['name']}")
        raw = input("Enter event numbers (comma-separated): ").strip()
        if raw:
            try:
                nums = [int(x) for x in raw.replace(" ", "").split(",") if x]
                for n in nums:
                    if 1 <= n <= len(choices):
                        selected_ids.append(choices[n - 1]["value"])
            except Exception:
                selected_ids = []

    if not selected_ids:
        print_warning("No in-app events selected")
        return []
    return [id_to_event[eid] for eid in selected_ids if eid in id_to_event]


def _unique_root_match(loc_map: Dict[str, str], locale_code: str) -> str:
    """Return a single matching localization id by language root (e.g., fi vs fi-FI).

    Only returns an id when the match is unambiguous.
    """
    root = (locale_code or "").split("-")[0].lower()
    if not root:
        return ""
    matches = [
        lid
        for code, lid in loc_map.items()
        if code and code.split("-")[0].lower() == root and lid
    ]
    return matches[0] if len(matches) == 1 else ""


def _find_existing_locale_id(loc_map: Dict[str, str], locale_code: str) -> str:
    """Find an existing localization id for a locale.

    Prefers exact match; falls back to unambiguous language-root match only when
    the requested locale has no region/script (e.g., "fi" matching "fi-FI").
    """
    if not locale_code:
        return ""
    loc_id = loc_map.get(locale_code)
    if loc_id:
        return loc_id
    # Never map region/script locales like en-AU to a different variant like en-US.
    if "-" in locale_code:
        return ""
    return _unique_root_match(loc_map, locale_code)


def run(cli) -> bool:
    ui = cli.ui
    asc = cli.asc_client

    print_info("In-App Events Translation Mode - Translate event name and descriptions")

    app_id = ui.prompt_app_id(asc)
    if app_id is None:
        print_info("Cancelled")
        return True

    # Prefill locales from app's latest version (helps default-check common targets)
    app_locales = set()
    try:
        latest_ver = asc.get_latest_app_store_version(app_id)
        if latest_ver:
            locs = asc.get_app_store_version_localizations(latest_ver).get("data", [])
            app_locales = {l.get("attributes", {}).get("locale") for l in locs if l.get("attributes", {}).get("locale")}
    except Exception:
        pass

    selected_events = _select_app_events(ui, asc, app_id)
    if not selected_events:
        return True

    if _DEBUG_APP_EVENTS:
        _debug("TRANSLATER_DEBUG_APP_EVENTS enabled")

    from workflows.iap_translate import _pick_provider, _choose_targets  # reuse shared helpers

    provider, provider_key = _pick_provider(cli)
    if not provider:
        return True

    refine_phrase = (getattr(cli, "config", None).get_prompt_refinement() if getattr(cli, "config", None) else "") or ""
    seed = getattr(cli, "session_seed", None)
    pname, pmodel = provider_model_info(provider, provider_key)
    print_info(f"AI provider: {pname} — model: {pmodel or 'n/a'} — seed: {seed}")

    name_limit = get_field_limit("app_event_name") or 30
    short_limit = get_field_limit("app_event_short_description") or 50
    long_limit = get_field_limit("app_event_long_description") or 120

    total_saved = 0
    for idx, event in enumerate(selected_events, 1):
        attrs = event.get("attributes", {}) or {}
        event_id = event.get("id") or ""
        ref = attrs.get("referenceName") or "Untitled Event"
        state = attrs.get("eventState") or ""
        badge = attrs.get("badge") or ""
        label = ref + (f" — {badge}" if badge else "") + (f" ({state})" if state else "")

        print()
        print_info(f"({idx}/{len(selected_events)}) Processing {label}")
        if not event_id:
            print_error("Missing event id; skipping")
            continue

        loc_resp = asc.get_app_event_localizations(event_id)
        localizations = loc_resp.get("data", []) if isinstance(loc_resp, dict) else []
        if not localizations:
            # Fallback: some accounts intermittently omit attributes on /localizations;
            # include=localizations is capped at 50 but enough for supported locales.
            try:
                fallback = asc.get_app_event(event_id, include_localizations=True)
                localizations = [
                    i for i in (fallback.get("included", []) if isinstance(fallback, dict) else [])
                    if i.get("type") == "appEventLocalizations"
                ]
            except Exception:
                localizations = []
            if not localizations:
                print_warning("No existing localizations found; skipping")
                continue

        primary_locale = attrs.get("primaryLocale")
        existing_locale_ids: Dict[str, str] = {}
        for l in localizations:
            attrs_l = (l.get("attributes", {}) or {})
            loc_code = (attrs_l.get("locale") or "").strip()
            loc_id = l.get("id")
            if loc_code and loc_id:
                existing_locale_ids[loc_code] = loc_id
        _debug(f"event_id={event_id} existing_locale_ids={sorted(existing_locale_ids.keys())}")

        base_locale: Optional[str] = None
        if primary_locale and primary_locale in existing_locale_ids:
            base_locale = primary_locale
        else:
            base_locale = detect_base_language(localizations)
        if not base_locale:
            print_error("Could not detect base locale for this event; skipping")
            continue

        base_attrs = next(
            (l.get("attributes", {}) for l in localizations if l.get("attributes", {}).get("locale") == base_locale),
            {},
        ) or {}
        base_name = (base_attrs.get("name") or "").strip()
        base_short = (base_attrs.get("shortDescription") or "").strip()
        base_long = (base_attrs.get("longDescription") or "").strip()

        print_info(f"Base language: {APP_STORE_LOCALES.get(base_locale, base_locale)} [{base_locale}]")

        if not base_name:
            print_warning("Base event name is empty.")
            base_name = _prompt_line(ui, "Enter source event name", default=base_name).strip()
        if not base_short:
            print_warning("Base short description is empty.")
            base_short = _prompt_line(ui, "Enter source short description", default=base_short).strip()
        if not base_long:
            print_warning("Base long description is empty.")
            edited = ui.prompt_multiline("Enter source long description", initial=base_long or "")
            base_long = (edited or "").strip()

        if not base_name or not base_short or not base_long:
            print_error("Source fields (name/short/long) are required to create new localizations; skipping this event.")
            continue

        target_locales = _choose_targets(
            ui,
            list(existing_locale_ids.keys()),
            base_locale,
            preferred_locales=app_locales,
        )
        target_locales = [t for t in target_locales if t != base_locale]
        if not target_locales:
            print_warning("No target locales selected; skipping this event")
            continue

        def _task(loc: str):
            language_name = APP_STORE_LOCALES.get(loc, loc)
            name_t = _translate_with_min_len(
                provider,
                base_name,
                language_name,
                max_length=name_limit,
                seed=seed,
                refinement=refine_phrase,
                min_len=1,
                field_label="name",
            )
            short_t = _translate_with_min_len(
                provider,
                base_short,
                language_name,
                max_length=short_limit,
                seed=seed,
                refinement=refine_phrase,
                min_len=1,
                field_label="shortDescription",
            )
            long_t = _translate_with_min_len(
                provider,
                base_long,
                language_name,
                max_length=long_limit,
                seed=seed,
                refinement=refine_phrase,
                min_len=2,
                field_label="longDescription",
            )
            long_t = _ensure_min_len(long_t, 2) or _ensure_min_len(short_t, 2) or _ensure_min_len(name_t, 2)
            translated = {"name": name_t, "shortDescription": short_t, "longDescription": long_t}
            time.sleep(1)
            return translated

        results, errs = parallel_map_locales(target_locales, _task, progress_action="Translated", pacing_seconds=0.0)
        if errs:
            print_warning(f"Translation errors for {len(errs)}/{len(target_locales)} locales; will save successful ones.")

        saved = 0
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
                refreshed_map: Dict[str, str] = {}
                refreshed = asc.get_app_event_localizations(event_id)
                for l in (refreshed.get("data", []) if isinstance(refreshed, dict) else []):
                    attrs_l = (l.get("attributes", {}) or {})
                    loc_code = (attrs_l.get("locale") or "").strip()
                    loc_id = l.get("id")
                    if loc_code and loc_id:
                        refreshed_map[loc_code] = loc_id
                if not refreshed_map:
                    fallback = asc.get_app_event(event_id, include_localizations=True)
                    for item in (fallback.get("included", []) if isinstance(fallback, dict) else []):
                        if item.get("type") != "appEventLocalizations":
                            continue
                        attrs_l = (item.get("attributes", {}) or {})
                        loc_code = (attrs_l.get("locale") or "").strip()
                        loc_id = item.get("id")
                        if loc_code and loc_id:
                            refreshed_map[loc_code] = loc_id
                existing_locale_ids.clear()
                existing_locale_ids.update(refreshed_map)
                _debug(f"refresh event_id={event_id} locales={sorted(refreshed_map.keys())}")
                return refreshed_map
            except Exception:
                return existing_locale_ids

        for loc, data in results.items():
            loc_id = _find_existing_locale_id(existing_locale_ids, loc)
            _debug(f"save locale={loc} loc_id={loc_id or '(none)'}")
            saved_this_locale = False
            try:
                if loc_id:
                    asc.update_app_event_localization(
                        loc_id,
                        name=data.get("name"),
                        short_description=data.get("shortDescription"),
                        long_description=data.get("longDescription"),
                    )
                else:
                    time.sleep(0.25)
                    asc.create_app_event_localization(
                        event_id,
                        loc,
                        name=data.get("name"),
                        short_description=data.get("shortDescription"),
                        long_description=data.get("longDescription"),
                    )
                    _refresh_locale_ids()
                saved += 1
                total_saved += 1
                completed += 1
                saved_this_locale = True
                # Keep an explicit mapping for this requested locale to prevent repeated create attempts
                if loc_id:
                    existing_locale_ids[loc] = loc_id
                try:
                    line = format_progress(completed, total_targets, f"Saved {APP_STORE_LOCALES.get(loc, loc)}")
                    pad = max(0, last_progress_len - len(line))
                    print("\r" + line + (" " * pad), end="")
                    last_progress_len = len(line)
                except Exception:
                    pass
            except Exception as e:
                if "409" in str(e) and not _has_validation_error(e):
                    _debug_http_error(f"409 while saving locale={loc}", e)
                    # Conflict usually means the locale already exists; refresh and update it.
                    recovered = False
                    for attempt in range(4):
                        try:
                            refreshed_map = _refresh_locale_ids()
                            new_id = _find_existing_locale_id(refreshed_map, loc)
                            _debug(f"recovery attempt={attempt+1} locale={loc} new_id={new_id or '(none)'}")
                            if new_id:
                                try:
                                    asc.update_app_event_localization(
                                        new_id,
                                        name=data.get("name"),
                                        short_description=data.get("shortDescription"),
                                        long_description=data.get("longDescription"),
                                    )
                                    saved += 1
                                    total_saved += 1
                                    completed += 1
                                    existing_locale_ids[loc] = new_id
                                    try:
                                        line = format_progress(completed, total_targets, f"Saved {APP_STORE_LOCALES.get(loc, loc)}")
                                        pad = max(0, last_progress_len - len(line))
                                        print("\r" + line + (" " * pad), end="")
                                        last_progress_len = len(line)
                                    except Exception:
                                        pass
                                    recovered = True
                                    break
                                except Exception as upd_err:
                                    if "409" in str(upd_err):
                                        _debug_http_error(f"409 while updating locale={loc} id={new_id}", upd_err)
                                    # If it already matches, count as success.
                                    if "409" in str(upd_err):
                                        try:
                                            fetched = asc.get_app_event_localization(new_id)
                                            f_attrs = fetched.get("data", {}).get("attributes", {}) if isinstance(fetched, dict) else {}
                                            if (
                                                f_attrs.get("name") == data.get("name")
                                                and f_attrs.get("shortDescription") == data.get("shortDescription")
                                                and f_attrs.get("longDescription") == data.get("longDescription")
                                            ):
                                                saved += 1
                                                total_saved += 1
                                                completed += 1
                                                existing_locale_ids[loc] = new_id
                                                try:
                                                    line = format_progress(completed, total_targets, f"Saved {APP_STORE_LOCALES.get(loc, loc)}")
                                                    pad = max(0, last_progress_len - len(line))
                                                    print("\r" + line + (" " * pad), end="")
                                                    last_progress_len = len(line)
                                                except Exception:
                                                    pass
                                                recovered = True
                                                break
                                        except Exception:
                                            pass
                            time.sleep(0.4 * (attempt + 1))
                        except Exception:
                            time.sleep(0.4 * (attempt + 1))
                    if recovered:
                        saved_this_locale = True

                if saved_this_locale:
                    continue
                language_name = APP_STORE_LOCALES.get(loc, loc)
                _debug_http_error(f"failed locale={loc}", e)
                print_error(f"  ❌ Failed to save {language_name}: {e}")

        try:
            print("\r" + (" " * last_progress_len) + "\r", end="")
        except Exception:
            pass
        print_success(f"Saved {saved}/{len(target_locales)} locales for {label}")

    print()
    print_success(f"In-app events translation finished. Localizations saved: {total_saved}")
    input("\nPress Enter to continue...")
    return True
