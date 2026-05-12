import time
from typing import Dict, Any, List, Optional
from utils import (
    APP_STORE_LOCALES, print_success, print_error, print_warning, print_info,
    format_progress, detect_base_language, find_matching_locale_entry
)
from workflows.helpers import get_app_locales

def _select_iaps(asc_client, app_id: str) -> List[Dict]:
    """Prompt user to select one or more IAPs."""
    response = asc_client.get_in_app_purchases(app_id)
    items = response.get("data", []) if isinstance(response, dict) else []
    if not items:
        print_error("No in-app purchases found for this app")
        return []

    print("\nAvailable IAPs:")
    for idx, item in enumerate(items, 1):
        attrs = item.get("attributes", {})
        name = attrs.get("referenceName") or attrs.get("name") or "Untitled IAP"
        product_id = attrs.get("productId")
        print(f"{idx:2d}. {name} [{product_id}]")

    print("\nSelect IAPs to remove localizations from (comma-separated numbers, or 'all'):")
    raw = input("> ").strip().lower()
    if not raw:
        return []

    selected = []
    if raw == "all":
        selected = items
    else:
        try:
            indexes = [int(v.strip()) for v in raw.split(",") if v.strip()]
            for idx in indexes:
                if 1 <= idx <= len(items):
                    selected.append(items[idx - 1])
        except ValueError:
            print_error("Invalid input")
            return []
    
    return selected

def _select_subscriptions(asc_client, app_id: str) -> List[Dict]:
    """Prompt user to select one or more subscriptions."""
    groups = asc_client.get_subscription_groups(app_id).get("data", [])
    all_subs = []
    for group in groups:
        group_id = group["id"]
        subs = asc_client.get_subscriptions_for_group(group_id).get("data", [])
        all_subs.extend(subs)
    
    if not all_subs:
        print_error("No subscriptions found for this app")
        return []

    print("\nAvailable Subscriptions:")
    for idx, item in enumerate(all_subs, 1):
        attrs = item.get("attributes", {})
        name = attrs.get("name") or "Untitled Subscription"
        product_id = attrs.get("productId")
        print(f"{idx:2d}. {name} [{product_id}]")

    print("\nSelect Subscriptions to remove localizations from (comma-separated numbers, or 'all'):")
    raw = input("> ").strip().lower()
    if not raw:
        return []

    selected = []
    if raw == "all":
        selected = all_subs
    else:
        try:
            indexes = [int(v.strip()) for v in raw.split(",") if v.strip()]
            for idx in indexes:
                if 1 <= idx <= len(all_subs):
                    selected.append(all_subs[idx - 1])
        except ValueError:
            print_error("Invalid input")
            return []
    
    return selected

def run(cli):
    """
    Remove Mode Workflow:
    1. Select App.
    2. Select Categories (Metadata, IAPs, etc.).
    3. Select items within categories (if applicable).
    4. Select locales to remove (usually all except base).
    5. Perform removal.
    """
    print_info("Remove Localization Mode - Delete localizations across languages")
    print()
    
    try:
        # 1. Select App
        app_id = cli._get_app_id()
        if not app_id:
            return True
            
        # 2. Select Categories
        print_info("Select categories to remove localizations from:")
        categories = {
            "1": ("App Metadata (Description, Keywords, etc.)", "metadata"),
            "2": ("In-App Purchases", "iap"),
            "3": ("Subscriptions", "subscriptions"),
            "4": ("Game Center", "game_center"),
            "5": ("In-App Events", "events")
        }
        
        for key, (name, _) in categories.items():
            print(f"{key}. {name}")
            
        print()
        print("Select categories (comma-separated numbers, e.g., '1,2'):")
        cat_input = input("> ").strip().lower()
        
        if not cat_input:
            print_error("No categories selected")
            return True
            
        selected_cat_keys = [k.strip() for k in cat_input.split(",")]
        selected_types = []
        for k in selected_cat_keys:
            if k in categories:
                selected_types.append(categories[k][1])
            else:
                print_error(f"Invalid category: {k}")
                return True
                
        # 3. Select items within categories
        iap_items = []
        if "iap" in selected_types:
            iap_items = _select_iaps(cli.asc_client, app_id)
            if not iap_items:
                selected_types.remove("iap")

        sub_items = []
        if "subscriptions" in selected_types:
            sub_items = _select_subscriptions(cli.asc_client, app_id)
            if not sub_items:
                selected_types.remove("subscriptions")

        # 4. Select Locales to remove
        print_info("Fetching existing app locales...")
        app_locales = get_app_locales(cli.asc_client, app_id)
        
        # We need to detect base language to avoid deleting it by mistake
        version_id = cli.asc_client.get_latest_app_store_version(app_id)
        version_locs = cli.asc_client.get_app_store_version_localizations(version_id).get("data", [])
        base_locale = detect_base_language(version_locs)
        
        print_info(f"Base language: {APP_STORE_LOCALES.get(base_locale, base_locale)} ({base_locale})")
        print("\nWhich locales should be removed?")
        print("1. All localizations EXCEPT base language")
        print("2. Select specific locales")
        
        loc_choice = input("Select option (1-2): ").strip()
        
        target_locales = []
        if loc_choice == "1":
            target_locales = [l for l in app_locales if l != base_locale]
        elif loc_choice == "2":
            print(f"Available locales: {', '.join(app_locales)}")
            loc_input = input("Enter locales to remove (comma-separated): ").strip()
            target_locales = [l.strip() for l in loc_input.split(",") if l.strip() in app_locales]
        else:
            print_error("Invalid choice")
            return True

        if not target_locales:
            print_warning("No target locales selected for removal")
            return True

        # 5. Confirmation
        print_warning(f"\nCRITICAL: You are about to DELETE localizations for {len(target_locales)} languages!")
        print(f"Categories: {', '.join(selected_types)}")
        confirm = input("Are you absolutely sure you want to proceed? (type 'DELETE' to confirm): ").strip()
        
        if confirm != "DELETE":
            print_info("Removal cancelled")
            return True

        # 6. Execute removal
        total_deleted = 0
        
        # Removal: Metadata
        if "metadata" in selected_types:
            print_info("Removing App Metadata localizations...")
            app_info_id = cli.asc_client.find_primary_app_info_id(app_id)
            info_locs = cli.asc_client.get_app_info_localizations(app_info_id).get("data", [])
            
            for locale in target_locales:
                # Remove version localization
                v_loc = next((l for l in version_locs if l["attributes"]["locale"] == locale), None)
                if v_loc:
                    try:
                        cli.asc_client.delete_app_store_version_localization(v_loc["id"])
                        print_success(f"  ✅ Deleted Version localization for {locale}")
                        total_deleted += 1
                    except Exception as e:
                        print_error(f"  ❌ Failed to delete Version localization for {locale}: {e}")
                
                # Remove info localization
                i_loc = next((l for l in info_locs if l["attributes"]["locale"] == locale), None)
                if i_loc:
                    try:
                        cli.asc_client.delete_app_info_localization(i_loc["id"])
                        print_success(f"  ✅ Deleted App Info localization for {locale}")
                        total_deleted += 1
                    except Exception as e:
                        print_error(f"  ❌ Failed to delete App Info localization for {locale}: {e}")

        # Removal: IAPs
        if "iap" in selected_types:
            for iap in iap_items:
                iap_id = iap["id"]
                iap_name = iap["attributes"].get("referenceName") or iap_id
                print_info(f"Removing localizations for IAP: {iap_name}")
                locs = cli.asc_client.get_in_app_purchase_localizations(iap_id).get("data", [])
                for locale in target_locales:
                    l_loc = next((l for l in locs if l["attributes"]["locale"] == locale), None)
                    if l_loc:
                        try:
                            cli.asc_client.delete_in_app_purchase_localization(l_loc["id"])
                            print_success(f"  ✅ Deleted IAP localization for {locale}")
                            total_deleted += 1
                        except Exception as e:
                            print_error(f"  ❌ Failed to delete IAP localization for {locale}: {e}")

        # Removal: Subscriptions
        if "subscriptions" in selected_types:
            for sub in sub_items:
                sub_id = sub["id"]
                sub_name = sub["attributes"].get("name") or sub_id
                print_info(f"Removing localizations for Subscription: {sub_name}")
                locs = cli.asc_client.get_subscription_localizations(sub_id).get("data", [])
                for locale in target_locales:
                    l_loc = next((l for l in locs if l["attributes"]["locale"] == locale), None)
                    if l_loc:
                        try:
                            cli.asc_client.delete_subscription_localization(l_loc["id"])
                            print_success(f"  ✅ Deleted Subscription localization for {locale}")
                            total_deleted += 1
                        except Exception as e:
                            print_error(f"  ❌ Failed to delete Subscription localization for {locale}: {e}")

        # Removal: Game Center
        if "game_center" in selected_types:
            print_info("Removing Game Center localizations...")
            gc_resp = cli.asc_client.get_game_center_detail(app_id)
            detail_id = gc_resp.get("data", {}).get("id") if isinstance(gc_resp, dict) else None
            
            if detail_id:
                achs = cli.asc_client.get_game_center_achievements(detail_id).get("data", [])
                for ach in achs:
                    locs = cli.asc_client.get_game_center_achievement_localizations(ach["id"]).get("data", [])
                    for locale in target_locales:
                        l_loc = next((l for l in locs if l["attributes"]["locale"] == locale), None)
                        if l_loc:
                            try:
                                cli.asc_client.delete_game_center_achievement_localization(l_loc["id"])
                                print_success(f"  ✅ Deleted Achievement localization for {locale}")
                                total_deleted += 1
                            except Exception as e:
                                print_error(f"  ❌ Failed to delete Achievement localization for {locale}: {e}")
                
                lbs = cli.asc_client.get_game_center_leaderboards(detail_id).get("data", [])
                for lb in lbs:
                    locs = cli.asc_client.get_game_center_leaderboard_localizations(lb["id"]).get("data", [])
                    for locale in target_locales:
                        l_loc = next((l for l in locs if l["attributes"]["locale"] == locale), None)
                        if l_loc:
                            try:
                                cli.asc_client.delete_game_center_leaderboard_localization(l_loc["id"])
                                print_success(f"  ✅ Deleted Leaderboard localization for {locale}")
                                total_deleted += 1
                            except Exception as e:
                                print_error(f"  ❌ Failed to delete Leaderboard localization for {locale}: {e}")

        # Removal: Events
        if "events" in selected_types:
            events = cli.asc_client.get_app_events(app_id).get("data", [])
            for ev in events:
                print_info(f"Removing localizations for Event: {ev['attributes'].get('referenceName', ev['id'])}")
                locs = cli.asc_client.get_app_event_localizations(ev["id"]).get("data", [])
                for locale in target_locales:
                    l_loc = next((l for l in locs if l["attributes"]["locale"] == locale), None)
                    if l_loc:
                        try:
                            cli.asc_client.delete_app_event_localization(l_loc["id"])
                            print_success(f"  ✅ Deleted Event localization for {locale}")
                            total_deleted += 1
                        except Exception as e:
                            print_error(f"  ❌ Failed to delete Event localization for {locale}: {e}")

        print()
        print_success(f"Removal process completed! Total items deleted: {total_deleted}")
        
    except Exception as e:
        print_error(f"Removal process failed: {e}")
        
    input("\nPress Enter to continue...")
    return True
