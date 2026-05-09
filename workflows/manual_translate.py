import json
import time
from typing import Dict, Any, List, Optional
from utils import (
    APP_STORE_LOCALES, print_success, print_error, print_warning, print_info,
    format_progress, detect_base_language, find_matching_locale_entry,
    truncate_keywords, get_field_limit
)

def run(cli):
    """
    Manual Translation Workflow:
    1. Select App.
    2. Select Categories (Numbered Menu).
    3. Collect base metadata for all selected categories.
    4. Select target locales.
    5. Export JSON + Prompt.
    6. Import translated JSON.
    7. Update App Store for all categories.
    """
    print_info("Manual Translation Mode - Export/Import for external translation")
    print()
    
    try:
        # 1. Select App
        app_id = cli._get_app_id()
        if not app_id:
            return True
            
        # 2. Select Categories
        print_info("Select categories to translate:")
        categories = {
            "1": ("App Metadata", "metadata"),
            "2": ("What's New", "whats_new"),
            "3": ("App Info URLs", "urls"),
            "4": ("In-App Purchases", "iap"),
            "5": ("Subscriptions", "subscriptions"),
            "6": ("Game Center", "game_center"),
            "7": ("In-App Events", "events")
        }
        
        for key, (name, _) in categories.items():
            print(f"{key}. {name}")
            
        print()
        print("Select categories (comma-separated numbers, e.g., '1,4,5' or 'all'):")
        cat_input = input("> ").strip().lower()
        
        if not cat_input:
            print_error("No categories selected")
            return True
            
        selected_cat_keys = []
        if cat_input == "all":
            selected_cat_keys = list(categories.keys())
        else:
            selected_cat_keys = [k.strip() for k in cat_input.split(",")]
            
        selected_types = []
        for k in selected_cat_keys:
            if k in categories:
                selected_types.append(categories[k][1])
            else:
                print_error(f"Invalid category: {k}")
                return True
                
        if not selected_types:
            print_error("No valid categories selected")
            return True
            
        # 3. Collect Base Metadata
        print_info("Fetching existing localizations and base data...")
        
        # We need version and app info IDs for most things
        version_id = cli.asc_client.get_latest_app_store_version(app_id)
        app_info_id = cli.asc_client.find_primary_app_info_id(app_id)
        
        if not version_id or not app_info_id:
            print_error("Could not find editable version or app info")
            return True
            
        version_locs = cli.asc_client.get_app_store_version_localizations(version_id).get("data", [])
        info_locs = cli.asc_client.get_app_info_localizations(app_info_id).get("data", [])
        
        base_locale = detect_base_language(version_locs)
        if not base_locale:
            print_error("Base language not found")
            return True
            
        base_version_loc = next((l for l in version_locs if l["attributes"]["locale"] == base_locale), None)
        base_info_loc = next((l for l in info_locs if l["attributes"]["locale"] == base_locale), None)
        
        source_data = {}
        constraints = []
        
        # Collector: Metadata
        if "metadata" in selected_types or "whats_new" in selected_types or "urls" in selected_types:
            meta = {}
            if "metadata" in selected_types:
                if base_info_loc:
                    meta["name"] = base_info_loc["attributes"].get("name", "")
                    meta["subtitle"] = base_info_loc["attributes"].get("subtitle", "")
                if base_version_loc:
                    meta["description"] = base_version_loc["attributes"].get("description", "")
                    meta["keywords"] = base_version_loc["attributes"].get("keywords", "")
                    meta["promotional_text"] = base_version_loc["attributes"].get("promotionalText", "")
                constraints.extend([
                    "- 'name': max 30 characters",
                    "- 'subtitle': max 30 characters",
                    "- 'description': max 4000 characters",
                    "- 'keywords': max 100 characters (comma-separated tags)",
                    "- 'promotional_text': max 170 characters"
                ])
                
            if "whats_new" in selected_types:
                if base_version_loc:
                    meta["whats_new"] = base_version_loc["attributes"].get("whatsNew", "")
                constraints.append("- 'whats_new': max 4000 characters")
                
            if "urls" in selected_types:
                if base_info_loc:
                    meta["privacy_policy_url"] = base_info_loc["attributes"].get("privacyPolicyUrl", "")
                    meta["marketing_url"] = base_info_loc["attributes"].get("marketingUrl", "")
                    meta["support_url"] = base_info_loc["attributes"].get("supportUrl", "")
            
            source_data["app_metadata"] = meta
            
        # Collector: IAPs
        if "iap" in selected_types:
            print_info("Fetching In-App Purchases...")
            iaps = cli.asc_client.get_in_app_purchases(app_id).get("data", [])
            iap_data = {}
            for iap in iaps:
                iap_id = iap["id"]
                original_name = iap["attributes"].get("name", "Unknown IAP")
                # Get base localization
                locs = cli.asc_client.get_in_app_purchase_localizations(iap_id).get("data", [])
                base_loc = next((l for l in locs if l["attributes"]["locale"] == base_locale), None)
                if base_loc:
                    iap_data[iap_id] = {
                        "original_name": original_name,
                        "name": base_loc["attributes"].get("name", ""),
                        "description": base_loc["attributes"].get("description", "")
                    }
            if iap_data:
                source_data["iaps"] = iap_data
                constraints.extend([
                    "- IAP 'name': max 30 characters",
                    "- IAP 'description': max 45 characters"
                ])

        # Collector: Subscriptions
        if "subscriptions" in selected_types:
            print_info("Fetching Subscriptions...")
            groups = cli.asc_client.get_subscription_groups(app_id).get("data", [])
            sub_data = {"groups": {}, "items": {}}
            for group in groups:
                group_id = group["id"]
                group_name = group["attributes"].get("referenceName", "Unknown Group")
                locs = cli.asc_client.get_subscription_group_localizations(group_id).get("data", [])
                base_loc = next((l for l in locs if l["attributes"]["locale"] == base_locale), None)
                if base_loc:
                    sub_data["groups"][group_id] = {
                        "original_name": group_name,
                        "name": base_loc["attributes"].get("name", ""),
                        "custom_app_name": base_loc["attributes"].get("customAppName", "")
                    }
                
                # Fetch items in group
                subs = cli.asc_client.get_subscriptions_for_group(group_id).get("data", [])
                for sub in subs:
                    sub_id = sub["id"]
                    sub_ref = sub["attributes"].get("name", "Unknown Subscription")
                    sub_locs = cli.asc_client.get_subscription_localizations(sub_id).get("data", [])
                    sbase_loc = next((l for l in sub_locs if l["attributes"]["locale"] == base_locale), None)
                    if sbase_loc:
                        sub_data["items"][sub_id] = {
                            "original_name": sub_ref,
                            "name": sbase_loc["attributes"].get("name", ""),
                            "description": sbase_loc["attributes"].get("description", "")
                        }
            if sub_data["groups"] or sub_data["items"]:
                source_data["subscriptions"] = sub_data
                constraints.extend([
                    "- Subscription 'name': max 60 characters",
                    "- Subscription 'description': max 200 characters",
                    "- Subscription Group 'name': max 60 characters"
                ])

        # Collector: Game Center
        if "game_center" in selected_types:
            print_info("Fetching Game Center data...")
            detail_id = cli.asc_client.get_app_game_center_detail(app_id)
            if detail_id:
                gc_data = {"achievements": {}, "leaderboards": {}}
                
                achs = cli.asc_client.get_game_center_achievements(detail_id).get("data", [])
                for ach in achs:
                    ach_id = ach["id"]
                    ach_ref = ach["attributes"].get("referenceName", "Unknown Achievement")
                    locs = cli.asc_client.get_game_center_achievement_localizations(ach_id).get("data", [])
                    base_loc = next((l for l in locs if l["attributes"]["locale"] == base_locale), None)
                    if base_loc:
                        gc_data["achievements"][ach_id] = {
                            "original_name": ach_ref,
                            "name": base_loc["attributes"].get("name", ""),
                            "before_earned_description": base_loc["attributes"].get("beforeEarnedDescription", ""),
                            "after_earned_description": base_loc["attributes"].get("afterEarnedDescription", "")
                        }
                
                lbs = cli.asc_client.get_game_center_leaderboards(detail_id).get("data", [])
                for lb in lbs:
                    lb_id = lb["id"]
                    lb_ref = lb["attributes"].get("referenceName", "Unknown Leaderboard")
                    locs = cli.asc_client.get_game_center_leaderboard_localizations(lb_id).get("data", [])
                    base_loc = next((l for l in locs if l["attributes"]["locale"] == base_locale), None)
                    if base_loc:
                        gc_data["leaderboards"][lb_id] = {
                            "original_name": lb_ref,
                            "name": base_loc["attributes"].get("name", ""),
                            "description": base_loc["attributes"].get("description", "")
                        }
                
                if gc_data["achievements"] or gc_data["leaderboards"]:
                    source_data["game_center"] = gc_data
                    constraints.extend([
                        "- Achievement 'name': max 30 characters",
                        "- Leaderboard 'name': max 30 characters"
                    ])

        # Collector: Events
        if "events" in selected_types:
            print_info("Fetching In-App Events...")
            events = cli.asc_client.get_app_events(app_id).get("data", [])
            event_data = {}
            for ev in events:
                ev_id = ev["id"]
                ev_ref = ev["attributes"].get("referenceName", "Unknown Event")
                locs = cli.asc_client.get_app_event_localizations(ev_id).get("data", [])
                base_loc = next((l for l in locs if l["attributes"]["locale"] == base_locale), None)
                if base_loc:
                    event_data[ev_id] = {
                        "original_name": ev_ref,
                        "name": base_loc["attributes"].get("name", ""),
                        "short_description": base_loc["attributes"].get("shortDescription", ""),
                        "long_description": base_loc["attributes"].get("longDescription", "")
                    }
            if event_data:
                source_data["events"] = event_data
                constraints.extend([
                    "- Event 'name': max 30 characters",
                    "- Event 'short_description': max 50 characters",
                    "- Event 'long_description': max 500 characters"
                ])

        if not source_data:
            print_error("No translatable data found for selected categories")
            return True
            
        # 4. Select Target Locales
        all_locales = list(APP_STORE_LOCALES.keys())
        print()
        print_info(f"Base Language: {APP_STORE_LOCALES.get(base_locale, base_locale)} ({base_locale})")
        print("Enter target locales (comma-separated, 'all' for every locale):")
        locales_input = input("> ").strip()
        
        if not locales_input:
            print_error("No locales entered")
            return True
            
        if locales_input.lower() == "all":
            target_locales = [l for l in all_locales if l != base_locale]
        else:
            target_locales = [l.strip() for l in locales_input.split(",") if l.strip()]
            
        if not target_locales:
            print_error("No target locales selected")
            return True
            
        # 5. Export Prompt + JSON to File
        prompt_file = "scratch/manual_translation.json"
        
        constraints_str = "\n".join(sorted(list(set(constraints))))
        
        prompt = f"""Please translate the following app metadata into these languages: {', '.join([f"{APP_STORE_LOCALES.get(l, l)} ({l})" for l in target_locales])}.

IMPORTANT CONSTRAINTS:
{constraints_str}

Return ONLY a valid JSON object where keys are the locale codes ({', '.join(target_locales)}) and values are objects containing the translated fields.
DO NOT translate original_name fields, they are for your context.

SOURCE DATA ({base_locale}):
"""
        
        export_data = {
            "instructions": prompt.strip().split("\n"),
            "source_data": source_data
        }
        
        try:
            import os
            os.makedirs("scratch", exist_ok=True)
            with open(prompt_file, "w", encoding="utf-8") as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)
            
            print("\n" + "="*60)
            print_success(f"Prompt and source data written to: {prompt_file}")
            print("1. Open the file and copy the instructions and source data to your LLM.")
            print("2. Once you have the translated JSON, REPLACING EVERYTHING in that file with ONLY the translated JSON.")
            print("3. Save the file and press Enter here to continue.")
            print("="*60 + "\n")
            
        except Exception as e:
            print_error(f"Failed to write prompt file: {e}")
            return True
            
        # 6. Wait for user and Read File
        input("Press Enter once you have saved the translated JSON in the file...")
        
        try:
            with open(prompt_file, "r", encoding="utf-8") as f:
                translated_json_text = f.read().strip()
                
            if not translated_json_text:
                print_error("The file is empty")
                return True
                
            translations = json.loads(translated_json_text)
            
            # Basic validation: check if it's a dict and has at least one valid locale key
            if not isinstance(translations, dict):
                print_error("Invalid JSON format: Root must be an object")
                return True
                
        except json.JSONDecodeError as e:
            print_error(f"Invalid JSON format in {prompt_file}: {e}")
            print_info("Make sure the file contains ONLY the valid JSON object returned by the LLM.")
            return True
        except Exception as e:
            print_error(f"Failed to read translation file: {e}")
            return True
            
        # 7. Update App Store Connect
        print()
        print_info(f"Processing updates for {len(translations)} locales...")
        
        total_locales = len(translations)
        success_count = 0
        
        for i, (locale, data) in enumerate(translations.items(), 1):
            if locale not in APP_STORE_LOCALES:
                print_warning(f"  ⚠️ Skipping unknown locale: {locale}")
                continue
                
            lang_name = APP_STORE_LOCALES.get(locale, locale)
            print()
            print(format_progress(i, total_locales, f"Processing {lang_name}"))
            
            try:
                # Update Metadata
                if "app_metadata" in data:
                    m = data["app_metadata"]
                    # Clean/Truncate
                    name = m.get("name", "").strip()[:get_field_limit("name") or 30] if m.get("name") else None
                    subtitle = m.get("subtitle", "").strip()[:get_field_limit("subtitle") or 30] if m.get("subtitle") else None
                    desc = m.get("description", "").strip()[:get_field_limit("description") or 4000] if m.get("description") else None
                    keys = truncate_keywords(m.get("keywords", ""), get_field_limit("keywords") or 100) if m.get("keywords") else None
                    wn = m.get("whats_new", "").strip()[:get_field_limit("whats_new") or 4000] if m.get("whats_new") else None
                    prom = m.get("promotional_text", "").strip()[:get_field_limit("promotional_text") or 170] if m.get("promotional_text") else None
                    
                    # Update Info
                    if name or subtitle or m.get("privacy_policy_url"):
                        loc = next((l for l in info_locs if l["attributes"]["locale"] == locale), None)
                        if loc:
                            cli.asc_client.update_app_info_localization(
                                loc["id"], name=name, subtitle=subtitle,
                                privacy_policy_url=m.get("privacy_policy_url"),
                                marketing_url=m.get("marketing_url"),
                                support_url=m.get("support_url")
                            )
                        else:
                            cli.asc_client.create_app_info_localization(
                                app_info_id, locale, name=name or "", subtitle=subtitle or ""
                            )
                        print_success(f"    ✅ App Info updated")

                    # Update Version
                    if desc or keys or wn or prom:
                        loc = next((l for l in version_locs if l["attributes"]["locale"] == locale), None)
                        if loc:
                            cli.asc_client.update_app_store_version_localization(
                                loc["id"], description=desc, keywords=keys, whats_new=wn, promotional_text=prom
                            )
                        else:
                            # Fallback description if missing for new creation
                            if not desc:
                                desc = (source_data.get("app_metadata", {}).get("description") or "App Description").strip()[:4000]
                            cli.asc_client.create_app_store_version_localization(
                                version_id, locale, description=desc, keywords=keys, whats_new=wn, promotional_text=prom
                            )
                        print_success(f"    ✅ App Version metadata updated")

                # Update IAPs
                if "iaps" in data:
                    for iap_id, iap_m in data["iaps"].items():
                        cli.asc_client.create_in_app_purchase_localization(
                            iap_id, locale, iap_m.get("name", ""), iap_m.get("description")
                        )
                    print_success(f"    ✅ IAP localizations updated")

                # Update Subscriptions
                if "subscriptions" in data:
                    s = data["subscriptions"]
                    for gid, gm in s.get("groups", {}).items():
                        cli.asc_client.create_subscription_group_localization(
                            gid, locale, gm.get("name", ""), gm.get("custom_app_name")
                        )
                    for sid, sm in s.get("items", {}).items():
                        cli.asc_client.create_subscription_localization(
                            sid, locale, sm.get("name", ""), sm.get("description")
                        )
                    print_success(f"    ✅ Subscription localizations updated")

                # Update Game Center
                if "game_center" in data:
                    gc = data["game_center"]
                    for aid, am in gc.get("achievements", {}).items():
                        cli.asc_client.create_game_center_achievement_localization(
                            aid, locale, am.get("name", ""), 
                            am.get("before_earned_description", ""), 
                            am.get("after_earned_description", "")
                        )
                    for lid, lm in gc.get("leaderboards", {}).items():
                        cli.asc_client.create_game_center_leaderboard_localization(
                            lid, locale, lm.get("name", ""), lm.get("description")
                        )
                    print_success(f"    ✅ Game Center localizations updated")

                # Update Events
                if "events" in data:
                    for eid, em in data["events"].items():
                        cli.asc_client.create_app_event_localization(
                            eid, locale, em.get("name", ""), 
                            em.get("short_description"), 
                            em.get("long_description")
                        )
                    print_success(f"    ✅ Event localizations updated")

                success_count += 1
                time.sleep(0.5)
                
            except Exception as e:
                print_error(f"    ❌ Failed to update {lang_name}: {e}")
                
        print()
        print_success(f"Manual translation update completed! {success_count}/{total_locales} locales processed successfully.")
        
    except Exception as e:
        print_error(f"Manual translation failed: {e}")
        
    input("\nPress Enter to continue...")
    return True
