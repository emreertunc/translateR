"""Shared workflow helpers."""

from typing import Dict, Iterable, List, Optional, Tuple

from utils import print_error, print_info


def pick_provider(cli, prompt: str = "Select AI provider") -> Tuple[Optional[object], Optional[str]]:
    """Select AI provider with optional configured default."""
    manager = cli.ai_manager
    providers = manager.list_providers()
    if not providers:
        print_error("No AI providers configured. Run setup first.")
        return None, None

    selected_provider: Optional[str] = None
    default_provider = cli.config.get_default_ai_provider()

    if len(providers) == 1:
        selected_provider = providers[0]
        print_info(f"Using AI provider: {selected_provider}")
    else:
        if default_provider and default_provider in providers:
            raw_default = input(f"Use default provider '{default_provider}'? (Y/n): ").strip().lower()
            if raw_default in ("", "y", "yes"):
                selected_provider = default_provider

        if not selected_provider:
            print()
            print(prompt + ":")
            for i, provider_name in enumerate(providers, 1):
                suffix = " (default)" if provider_name == default_provider else ""
                print(f"{i}. {provider_name}{suffix}")

            raw = input("Select provider (number): ").strip()
            try:
                idx = int(raw)
                if 1 <= idx <= len(providers):
                    selected_provider = providers[idx - 1]
            except Exception:
                selected_provider = None

    if not selected_provider:
        print_error("Invalid provider selection")
        return None, None

    return manager.get_provider(selected_provider), selected_provider


def choose_target_locales(
    available_targets: Dict[str, str],
    base_locale: str,
    preferred_locales: Optional[Iterable[str]] = None,
) -> List[str]:
    """Select target locales from available list."""
    preferred_set = set(preferred_locales or [])
    if not available_targets:
        return []

    print("Available target locales:")
    items = list(available_targets.items())
    for i in range(0, len(items), 2):
        left = items[i]
        right = items[i + 1] if i + 1 < len(items) else None
        left_txt = f"{left[0]:8} - {left[1]}"
        right_txt = f"{right[0]:8} - {right[1]}" if right else ""
        print(f"{left_txt:30} {right_txt}")

    default_locales = sorted(loc for loc in preferred_set if loc in available_targets)
    raw = input("Enter target locales (comma-separated, 'all' for every locale): ").strip()

    if not raw:
        return default_locales
    if raw.lower() in ("all", "*"):
        return [loc for loc in available_targets.keys() if loc != base_locale]

    selected = [part.strip() for part in raw.split(",") if part.strip() in available_targets]
    return selected if selected else default_locales


def get_app_locales(asc_client, app_id: str) -> set:
    """Return union of locales across latest version on each platform."""
    versions_resp = asc_client._request("GET", f"apps/{app_id}/appStoreVersions")
    versions = versions_resp.get("data", [])
    latest_by_platform = _pick_latest_versions_by_platform(versions)

    locales = set()
    for version in latest_by_platform.values():
        localizations = asc_client.get_app_store_version_localizations(version["id"]).get("data", [])
        for localization in localizations:
            code = localization.get("attributes", {}).get("locale")
            if code:
                locales.add(code)
    return locales


def _version_tuple(version_string: str) -> Tuple[int, ...]:
    if not version_string:
        return tuple()
    parts = version_string.split(".")
    numbers: List[int] = []
    for part in parts:
        if not part.isdigit():
            return tuple()
        numbers.append(int(part))
    return tuple(numbers)


def _version_sort_key(version: dict) -> Tuple[Tuple[int, ...], str]:
    attrs = version.get("attributes", {})
    version_string = attrs.get("versionString") or ""
    created = attrs.get("createdDate") or attrs.get("releaseDate") or ""
    return _version_tuple(version_string), created


def _pick_latest_versions_by_platform(versions: List[dict]) -> Dict[str, dict]:
    latest_by_platform: Dict[str, dict] = {}
    for version in versions:
        attrs = version.get("attributes", {})
        platform = attrs.get("platform", "UNKNOWN")
        current = latest_by_platform.get(platform)
        if current is None or _version_sort_key(version) > _version_sort_key(current):
            latest_by_platform[platform] = version
    return latest_by_platform
