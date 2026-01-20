"""
Translation Mode workflow with multi-platform handling.
"""

from typing import Dict
import time

from utils import (
    APP_STORE_LOCALES,
    get_field_limit,
    print_info,
    print_warning,
    print_error,
    truncate_keywords,
    detect_base_language,
    parallel_map_locales,
    provider_model_info,
)


def select_platform_versions(ui, asc_client, app_id: str):
    versions_resp = asc_client._request("GET", f"apps/{app_id}/appStoreVersions")
    versions = versions_resp.get("data", [])
    if not versions:
        print_error("No App Store versions found for this app")
        return None, None
    latest_by_platform: Dict[str, dict] = {}
    for v in versions:
        attrs = v.get("attributes", {})
        plat = attrs.get("platform", "UNKNOWN")
        if plat not in latest_by_platform:
            latest_by_platform[plat] = v
    if ui.available():
        choices = []
        for plat, v in latest_by_platform.items():
            attrs = v.get("attributes", {})
            name = f"{attrs.get('platform','?')} v{attrs.get('versionString','?')} ({attrs.get('appStoreState','?')})"
            choices.append({"name": name, "value": plat, "enabled": True})
        picked = ui.checkbox("Select platforms (Space to toggle, Enter to confirm)", choices, add_back=True)
        if not picked:
            print_info("Cancelled")
            return None, None
        selected = {p: latest_by_platform[p] for p in picked}
    else:
        selected = latest_by_platform
    return selected, latest_by_platform


def run(cli) -> bool:
    ui = cli.ui
    asc = cli.asc_client
    manager = cli.ai_manager

    print_info("Translation Mode - Translate existing content to new languages")
    print()

    # Translation type
    include_app_info = False
    if ui.available():
        choice = ui.select(
            "Select translation type",
            [
                {"name": "Metadata Only (description, keywords, promotional text, what's new)", "value": "1"},
                {"name": "Complete Translation (metadata + app name & subtitle)", "value": "2"},
            ], add_back=True,
        )
        if choice is None:
            print_info("Cancelled")
            return True
        include_app_info = (choice == '2')
    else:
        print("1) Metadata Only\n2) Complete Translation")
        raw = input("Select (1-2): ").strip()
        if raw not in ['1', '2']:
            print_error("Invalid selection")
            return True
        include_app_info = (raw == '2')

    # App
    app_id = ui.prompt_app_id(asc)
    if app_id is None:
        print_info("Cancelled")
        return True

    # Platforms
    selected_versions, _ = select_platform_versions(ui, asc, app_id)
    if not selected_versions:
        return True

    # Use first platform to derive base + localizations
    first_ver = next(iter(selected_versions.values()))
    vid = first_ver["id"]
    localizations_response = asc.get_app_store_version_localizations(vid)
    localizations = localizations_response.get("data", [])
    if not localizations:
        print_error("No existing localizations found")
        return True

    base_locale = detect_base_language(localizations)
    if not base_locale:
        print_error("Could not detect base language")
        return True
    print_info(f"Detected base language: {base_locale} ({APP_STORE_LOCALES.get(base_locale, 'Unknown')})")

    # Source base data
    base_data = None
    for loc in localizations:
        if loc["attributes"]["locale"] == base_locale:
            base_data = loc["attributes"]
            break
    if not base_data:
        print_error("Could not find base localization data")
        return True

    # Target languages (union across selected platforms)
    existing_by_platform: Dict[str, set] = {}
    locales_with_empty_description = set()
    for plat, ver in selected_versions.items():
        locs = asc.get_app_store_version_localizations(ver["id"]).get("data", [])
        locale_codes = set()
        for loc in locs:
            attrs = loc.get("attributes", {})
            locale_code = attrs.get("locale")
            if not locale_code:
                continue
            locale_codes.add(locale_code)
            if not (attrs.get("description") or "").strip():
                locales_with_empty_description.add(locale_code)
        existing_by_platform[plat] = locale_codes

    union_existing = set()
    for locales in existing_by_platform.values():
        union_existing.update(locales)

    def _is_locale_available(loc: str) -> bool:
        if loc == base_locale:
            return False
        if loc not in union_existing:
            return True
        return loc in locales_with_empty_description

    available_targets = {k: v for k, v in APP_STORE_LOCALES.items() if _is_locale_available(k)}
    if not available_targets:
        print_warning("All supported languages are already localized for selected platforms")
        return True

    # Choose targets
    if ui.available():
        choices = [{"name": f"{loc} - {nm}", "value": loc} for (loc, nm) in available_targets.items()]
        target_locales = ui.checkbox("Select target languages (Space to toggle, Enter to confirm)", choices, add_back=True)
        if not target_locales:
            print_warning("No target languages selected")
            return True
    else:
        for i, (loc, nm) in enumerate(list(available_targets.items())[:20], 1):
            print(f"{i:2d}. {loc:8} - {nm}")
        raw = input("Enter target locales (comma-separated): ").strip()
        if not raw:
            print_warning("No target languages selected")
            return True
        target_locales = [s.strip() for s in raw.split(',') if s.strip() in available_targets]
        if not target_locales:
            print_warning("No valid target languages selected")
            return True

    # Provider
    provs = manager.list_providers()
    selected_provider = None
    if len(provs) == 1:
        selected_provider = provs[0]
        print_info(f"Using AI provider: {selected_provider}")
    else:
        default_provider = getattr(cli, 'config', None).get_default_ai_provider() if getattr(cli, 'config', None) else None
        if default_provider and default_provider in provs:
            use_default = ui.confirm(f"Use default AI provider: {default_provider}?", True)
            if use_default is None:
                raw = input(f"Use default provider '{default_provider}'? (Y/n): ").strip().lower()
                use_default = raw in ("", "y", "yes")
            if use_default:
                selected_provider = default_provider
        if not selected_provider:
            if ui.available():
                selected_provider = ui.select("Select AI provider", [{"name": p + ("  (default)" if p == default_provider else ""), "value": p} for p in provs], add_back=True)
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
                        return True
    provider = manager.get_provider(selected_provider)
    # Use global refinement (no per-run prompt here; free text not requested)
    refine_phrase = (getattr(cli, 'config', None).get_prompt_refinement() if getattr(cli, 'config', None) else "") or ""
    # Show provider/model and choose seed for this run
    pname, pmodel = provider_model_info(provider, selected_provider)
    seed = getattr(cli, 'session_seed', None)
    print_info(f"AI provider: {pname} — model: {pmodel or 'n/a'} — seed: {seed}")

    # Translate and create per platform (parallel by locale)
    print_info(f"Starting translation for {len(target_locales)} languages across {len(selected_versions)} platform(s)...")
    def _task(loc: str):
        language_name = APP_STORE_LOCALES.get(loc, loc)
        translated = {}
        if base_data.get("description"):
            translated["description"] = provider.translate(base_data["description"], language_name, max_length=get_field_limit("description"), seed=seed, refinement=refine_phrase)
        if base_data.get("keywords"):
            kw = provider.translate(base_data["keywords"], language_name, max_length=get_field_limit("keywords"), is_keywords=True, seed=seed, refinement=refine_phrase)
            translated["keywords"] = truncate_keywords(kw)
        if base_data.get("promotionalText"):
            translated["promotionalText"] = provider.translate(base_data["promotionalText"], language_name, max_length=get_field_limit("promotional_text"), seed=seed, refinement=refine_phrase)
        if base_data.get("whatsNew"):
            translated["whatsNew"] = provider.translate(base_data["whatsNew"], language_name, max_length=get_field_limit("whats_new"), seed=seed, refinement=refine_phrase)
        if base_data.get("marketingUrl"):
            translated["marketingUrl"] = base_data["marketingUrl"]
        if base_data.get("supportUrl"):
            translated["supportUrl"] = base_data["supportUrl"]
        time.sleep(1)
        return translated

    results, errs = parallel_map_locales(target_locales, _task, progress_action="Translated", pacing_seconds=0.0)

    # Warn on empty translations per locale
    for loc in target_locales:
        language_name = APP_STORE_LOCALES.get(loc, loc)
        data = results.get(loc) or {}
        has_any = any((v or "").strip() for v in data.values() if isinstance(v, str))
        if not has_any:
            print_warning(f"Empty translation for {language_name} [{loc}]")

    for target_locale, translated_data in results.items():
        for plat, ver in selected_versions.items():
            locs = asc.get_app_store_version_localizations(ver["id"]).get("data", [])
            exists = any(l["attributes"]["locale"] == target_locale for l in locs)
            if exists:
                loc_id = next(l["id"] for l in locs if l["attributes"]["locale"] == target_locale)
                asc.update_app_store_version_localization(
                    localization_id=loc_id,
                    description=translated_data.get("description"),
                    keywords=translated_data.get("keywords"),
                    promotional_text=translated_data.get("promotionalText"),
                    whats_new=translated_data.get("whatsNew"),
                    marketing_url=translated_data.get("marketingUrl"),
                    support_url=translated_data.get("supportUrl"),
                )
            else:
                asc.create_app_store_version_localization(
                    version_id=ver["id"],
                    locale=target_locale,
                    description=translated_data.get("description", ""),
                    keywords=translated_data.get("keywords"),
                    promotional_text=translated_data.get("promotionalText"),
                    whats_new=translated_data.get("whatsNew"),
                    marketing_url=translated_data.get("marketingUrl"),
                    support_url=translated_data.get("supportUrl"),
                )

    # Optional: App name/subtitle
    if include_app_info:
        print_warning("App name/subtitle translation for multi-platform is not yet implemented in this refactor.")

    input("\nPress Enter to continue...")
    return True
