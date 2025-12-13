#!/usr/bin/env python3
"""
TranslateR - App Store Connect Localization Automation Tool

A powerful CLI tool for automating App Store Connect localizations 
with multi-AI provider support.

Author: Emre Ertunç
Contact: emre@ertunc.com
Repository: https://github.com/emreertunc/translater
"""

import sys
import os
import random
import time
import random
import re
from typing import List, Optional, Any, Dict
from pathlib import Path

# Modularized UI and workflows
from ui import UI
from workflows.release import run as release_run
from workflows.promo import run as promo_run
from workflows.translate import run as translate_run
from workflows.update_localizations import run as update_run
from workflows.copy import run as copy_run
from workflows.full_setup import run as full_setup_run
from workflows.app_info import run as app_info_run
from workflows.export_localizations import run as export_run
from workflows.manage_presets import run as manage_presets_run
from workflows.iap_translate import run as iap_translate_run
from workflows.subscription_translate import run as subscription_translate_run
from workflows.app_events_translate import run as app_events_translate_run

from config import ConfigManager
from app_store_client import AppStoreConnectClient
from ai_providers import AIProviderManager, AnthropicProvider, OpenAIProvider, GoogleGeminiProvider
from utils import (
    APP_STORE_LOCALES,
    detect_base_language,
    print_success, print_error, print_warning, print_info, format_progress,
    resolve_private_key_path, DEFAULT_APPSTORE_P8_DIR
)


class TranslateRCLI:
    """Main CLI interface for TranslateR application."""
    
    def __init__(self):
        self.config = ConfigManager()
        self.asc_client = None
        self.ai_manager = AIProviderManager()
        self.ui = UI()
        # Session-wide random seed reused across all translations
        self.session_seed = random.randint(1, 2**31 - 1)
        self.setup_ai_providers()
    
    def setup_ai_providers(self):
        """Initialize AI providers from configuration."""
        try:
            # Reset manager to reflect latest config accurately
            self.ai_manager = AIProviderManager()
            providers_config = self.config.load_providers()
            
            # Setup Anthropic
            anthropic_key = self.config.get_ai_provider_key("anthropic")
            if anthropic_key:
                default_model = providers_config.get("anthropic", {}).get("default_model", "claude-sonnet-4-20250514")
                anthropic = AnthropicProvider(anthropic_key, default_model)
                self.ai_manager.add_provider("anthropic", anthropic)
            
            # Setup OpenAI
            openai_key = self.config.get_ai_provider_key("openai")
            if openai_key:
                default_model = providers_config.get("openai", {}).get("default_model", "gpt-4.1")
                openai = OpenAIProvider(openai_key, default_model)
                self.ai_manager.add_provider("openai", openai)
            
            # Setup Google Gemini
            google_key = self.config.get_ai_provider_key("google")
            if google_key:
                default_model = providers_config.get("google", {}).get("default_model", "gemini-2.5-flash")
                google = GoogleGeminiProvider(google_key, default_model)
                self.ai_manager.add_provider("google", google)
                
        except Exception as e:
            print_error(f"Error setting up AI providers: {e}")
    
    def setup_app_store_client(self):
        """Initialize App Store Connect client."""
        asc_config = self.config.get_app_store_config()
        
        if not asc_config:
            print_error("App Store Connect configuration not found.")
            return self.setup_wizard()
        
        try:
            # Resolve and read private key file (supports ~/.appstoreconnect/private_keys)
            resolved_key_path = resolve_private_key_path(
                key_id=asc_config["key_id"],
                configured_path=asc_config.get("private_key_path")
            )
            with open(resolved_key_path, "r") as f:
                private_key = f.read()
            
            self.asc_client = AppStoreConnectClient(
                key_id=asc_config["key_id"],
                issuer_id=asc_config["issuer_id"],
                private_key=private_key
            )
            
            # Test the connection
            self.asc_client.get_apps()
            print_success("App Store Connect client initialized successfully")
            return True
            
        except Exception as e:
            print_error(f"Failed to initialize App Store Connect client: {e}")
            return self.setup_wizard()
    
    def setup_wizard(self):
        """Guide user through initial setup."""
        print_info("Setting up TranslateR for first time use...")
        print()
        
        # App Store Connect setup
        print("📱 App Store Connect Configuration")
        print("You need your API credentials from App Store Connect:")
        print("1. Go to App Store Connect > Users and Access > Integrations")
        print("2. Create a new API key with App Manager role")
        print("3. Download the .p8 private key file")
        print()
        
        # Discover existing keys in default directory
        keys_dir = DEFAULT_APPSTORE_P8_DIR
        existing_keys: List[Path] = []
        try:
            if keys_dir.exists():
                existing_keys = sorted(keys_dir.glob("*.p8"))
        except Exception:
            existing_keys = []

        selected_path: str = ""
        if existing_keys:
            print()
            print(f"Found {len(existing_keys)} key(s) in {keys_dir}:")
            for idx, p in enumerate(existing_keys, 1):
                print(f"  {idx}. {p.name}")
            print("  0. Enter a custom path")

            choice = input("Select a key (1-{}), 0 for custom, or Enter to skip: ".format(len(existing_keys))).strip()
            if choice.isdigit():
                n = int(choice)
                if 1 <= n <= len(existing_keys):
                    selected_path = str(existing_keys[n - 1])
                elif n == 0:
                    # Will prompt for custom below
                    pass
            elif choice:
                print_warning("Invalid selection; continuing with custom/default option.")

        # If no selection yet, allow manual entry with generic default hint
        default_hint = DEFAULT_APPSTORE_P8_DIR
        if not selected_path:
            entered = input(
                f"Enter path to your .p8 private key file (leave blank to use default in {default_hint}): "
            ).strip()
            selected_path = entered  # may be blank; resolver will handle

        # Try to guess Key ID from selected filename
        key_id_guess = None
        if selected_path:
            try:
                name = Path(os.path.expanduser(selected_path)).name
                m = re.match(r"AuthKey_([A-Za-z0-9]+)\.p8$", name)
                if m:
                    key_id_guess = m.group(1)
            except Exception:
                key_id_guess = None

        # Determine API Key ID (auto-detect from filename when possible)
        if key_id_guess:
            print_info(f"Detected API Key ID: {key_id_guess}")
            key_id = key_id_guess
        else:
            key_id = input("Enter your API Key ID: ").strip()
        if not key_id:
            print_error("API Key ID is required")
            return False

        # Prompt for Issuer ID
        issuer_id = input("Enter your Issuer ID: ").strip()
        if not issuer_id:
            print_error("Issuer ID is required")
            return False

        # Validate resolved key path (blank allowed if default exists)
        try:
            _ = resolve_private_key_path(key_id=key_id, configured_path=selected_path or None)
        except Exception as e:
            print_error(str(e))
            return False
        
        # Save App Store Connect config
        api_keys = self.config.load_api_keys()
        api_keys["app_store_connect"] = {
            "key_id": key_id,
            "issuer_id": issuer_id,
            "private_key_path": selected_path  # may be blank; resolved at runtime
        }
        
        print()
        print("🤖 AI Provider Configuration")
        print("Configure at least one AI provider for translations:")
        
        # AI providers setup
        providers = ["anthropic", "openai", "google"]
        provider_names = {
            "anthropic": "Anthropic Claude",
            "openai": "OpenAI GPT", 
            "google": "Google Gemini"
        }
        
        for provider in providers:
            response = input(f"Do you want to configure {provider_names[provider]}? (y/n): ").strip().lower()
            if response in ['y', 'yes']:
                api_key = input(f"Enter {provider_names[provider]} API key: ").strip()
                if api_key:
                    api_keys["ai_providers"][provider] = api_key
        
        # Check if at least one AI provider is configured
        if not any(api_keys["ai_providers"].values()):
            print_error("You must configure at least one AI provider!")
            return False
        
        # Optionally set default provider now
        configured = [k for k, v in api_keys["ai_providers"].items() if v]
        if len(configured) > 1:
            pick_default = input("Set a default AI provider now? (Y/n): ").strip().lower()
            if pick_default in ("", "y", "yes"):
                for i, p in enumerate(configured, 1):
                    print(f"{i}. {provider_names.get(p, p)} ({p})")
                raw = input("Select default provider (number): ").strip()
                try:
                    idx = int(raw)
                    if 1 <= idx <= len(configured):
                        self.config.set_default_ai_provider(configured[idx - 1])
                        print_success(f"Default AI provider set to: {configured[idx - 1]}")
                except Exception:
                    print_warning("Skipping default provider selection")

        # Save configuration
        self.config.save_api_keys(api_keys)
        print_success("Configuration saved successfully!")
        
        # Reinitialize clients
        self.setup_ai_providers()
        return self.setup_app_store_client()

    def prompt_app_id(self) -> Optional[str]:
        """List available apps and let the user pick one or paste an ID."""
        return self.ui.prompt_app_id(self.asc_client)

    def release_mode(self):
        """Release Mode wrapper."""
        return release_run(self)

    def show_main_menu(self):
        """Display main menu and handle user choice."""
        # TUI-based main menu when available
        if self.ui.available():
            choices = [
                {"name": "🌐 Translation Mode - Translate to new languages", "value": "1"},
                {"name": "📝 Release Mode - Create release notes for new version", "value": "2"},
                {"name": "✨ Promo Mode - Update promotional text across locales", "value": "3"},
                {"name": "🔄 Update Mode - Update existing localizations", "value": "4"},
                {"name": "📋 Copy Mode - Copy from previous version", "value": "5"},
                {"name": "🚀 Full Setup Mode - Complete localization setup", "value": "6"},
                {"name": "📱 App Name & Subtitle Mode - Translate app name and subtitle", "value": "7"},
                {"name": "🛒 IAP Translations - Translate in-app purchase metadata", "value": "8"},
                {"name": "💳 Subscription Translations - Translate subscription metadata", "value": "9"},
                {"name": "🎉 In-App Events - Localize in-app events", "value": "10"},
                {"name": "📄 Export Localizations - Export existing localizations to file", "value": "11"},
                {"name": "🗂️ Manage Presets - Create and organize release note presets", "value": "12"},
                {"name": "⚙️  Configuration - Manage API keys and settings", "value": "13"},
                {"name": "❌ Exit", "value": "14"},
            ]
            choice = self.ui.select("TranslateR — Choose your workflow", choices) or ""
        else:
            print()
            print("🌍 TranslateR - Choose your workflow:")
            print("1. 🌐 Translation Mode - Translate to new languages")
            print("2. 📝 Release Mode - Create release notes for new version")
            print("3. ✨ Promo Mode - Update promotional text across locales")
            print("4. 🔄 Update Mode - Update existing localizations")
            print("5. 📋 Copy Mode - Copy from previous version") 
            print("6. 🚀 Full Setup Mode - Complete localization setup")
            print("7. 📱 App Name & Subtitle Mode - Translate app name and subtitle")
            print("8. 🛒 IAP Translations - Translate in-app purchase metadata")
            print("9. 💳 Subscription Translations - Translate subscription metadata")
            print("10. 🎉 In-App Events - Localize in-app events")
            print("11. 📄 Export Localizations - Export existing localizations to file")
            print("12. 🗂️ Manage Presets - Create and organize release note presets")
            print("13. ⚙️  Configuration - Manage API keys and settings")
            print("14. ❌ Exit")
            print()
            choice = input("Select an option (1-14): ").strip()

        if choice == "1":
            return translate_run(self)
        elif choice == "2":
            return release_run(self)
        elif choice == "3":
            return promo_run(self)
        elif choice == "4":
            return update_run(self)
        elif choice == "5":
            return copy_run(self)
        elif choice == "6":
            return full_setup_run(self)
        elif choice == "7":
            return app_info_run(self)
        elif choice == "8":
            return iap_translate_run(self)
        elif choice == "9":
            return subscription_translate_run(self)
        elif choice == "10":
            return app_events_translate_run(self)
        elif choice == "11":
            return export_run(self)
        elif choice == "12":
            return manage_presets_run(self)
        elif choice == "13":
            return self.configuration_mode()
        elif choice == "14":
            print_info("Thank you for using TranslateR!")
            return False
        else:
            print_error("Invalid choice. Please select 1-14.")
            return True
    
    def translation_mode(self):
        """Handle translation workflow."""
        return translate_run(self)

    def _translate_app_info(self, app_id: str, target_locales: List[str], provider):
        """Helper method to translate app name and subtitle for given locales."""
        try:
            # Find primary app info ID
            app_info_id = self.asc_client.find_primary_app_info_id(app_id)
            if not app_info_id:
                print_error("Could not find app info. App name & subtitle translation skipped.")
                return
            
            # Get existing localizations
            existing_localizations = self.asc_client.get_app_info_localizations(app_info_id)
            existing_locales = []
            localization_map = {}
            
            for loc in existing_localizations.get("data", []):
                locale = loc["attributes"]["locale"]
                existing_locales.append(locale)
                localization_map[locale] = loc["id"]
            
            # Get base language data
            base_locale = detect_base_language(existing_localizations.get("data", []))
            if not base_locale:
                print_error("No base language found for app info. Skipping app name & subtitle.")
                return
            
            base_localization_id = localization_map[base_locale]
            base_data = self.asc_client.get_app_info_localization(base_localization_id)
            base_attrs = base_data.get("data", {}).get("attributes", {})
            
            base_name = base_attrs.get("name", "")
            base_subtitle = base_attrs.get("subtitle", "")
            
            if not base_name and not base_subtitle:
                print_warning("No name or subtitle found in base language. Skipping app name & subtitle.")
                return
            
            print()
            print_info(f"Translating app name & subtitle from {APP_STORE_LOCALES.get(base_locale, base_locale)}")
            if base_name:
                print(f"📱 Name: {base_name}")
            if base_subtitle:
                print(f"📝 Subtitle: {base_subtitle}")
            
            success_count = 0
            
            for i, target_locale in enumerate(target_locales, 1):
                language_name = APP_STORE_LOCALES.get(target_locale, target_locale)
                print()
                print(format_progress(i, len(target_locales), f"Translating {language_name} app info"))
                
                try:
                    translated_data = {}
                    
                    # Translate name
                    if base_name:
                        print(f"  • Translating app name...")
                        translated_name = provider.translate(
                            base_name,
                            language_name,
                            max_length=30,
                            seed=self.session_seed
                        )
                        if len(translated_name) > 30:
                            translated_name = translated_name[:30]
                        translated_data["name"] = translated_name
                    
                    # Translate subtitle
                    if base_subtitle:
                        print(f"  • Translating subtitle...")
                        translated_subtitle = provider.translate(
                            base_subtitle,
                            language_name,
                            max_length=30,
                            seed=self.session_seed
                        )
                        if len(translated_subtitle) > 30:
                            translated_subtitle = translated_subtitle[:30]
                        translated_data["subtitle"] = translated_subtitle
                    
                    # Create or update app info localization
                    if target_locale in existing_locales:
                        # Update existing
                        self.asc_client.update_app_info_localization(
                            localization_map[target_locale],
                            **translated_data
                        )
                    else:
                        # Create new
                        self.asc_client.create_app_info_localization(
                            app_info_id,
                            target_locale,
                            **translated_data
                        )
                    
                    print_success(f"  ✅ {language_name} app info translation completed")
                    success_count += 1
                    time.sleep(1)  # Rate limiting
                    
                except Exception as e:
                    print_error(f"  ❌ Failed to translate {language_name} app info: {str(e)}")
                    continue
            
            print()
            print_success(f"App name & subtitle translation completed! {success_count}/{len(target_locales)} languages processed")
            
        except Exception as e:
            print_error(f"App info translation failed: {str(e)}")
    
    def update_mode(self):
        """Handle update existing localizations workflow."""
        return update_run(self)
    
    def copy_mode(self):
        """Handle copy workflow."""
        return copy_run(self)

    def full_setup_mode(self):
        """Handle full setup workflow."""
        return full_setup_run(self)
    
    def app_name_subtitle_mode(self):
        """Handle app name and subtitle translation workflow."""
        return app_info_run(self)
    
    def export_localizations_mode(self):
        """Handle export existing localizations workflow."""
        return export_run(self)
    
    def configuration_mode(self):
        """Handle configuration management."""
        print_info("Configuration Mode - Manage your settings")
        
        # Show current status
        print()
        providers = self.ai_manager.list_providers()
        print("Available AI Providers:")
        if providers:
            for p in providers:
                model = self.config.get_default_model(p) or "<unset>"
                tag = " (default)" if (self.config.get_default_ai_provider() == p) else ""
                print(f"  • {p}{tag} — model: {model}")
        else:
            print("  ❌ No AI providers configured")
        print("App Store Connect:", "✅ Configured" if self.asc_client else "❌ Not configured")

        # Menu
        if self.ui.available():
            choice = self.ui.select(
                "What would you like to configure?",
                [
                    {"name": "Reconfigure API keys (ASC + AI)", "value": "keys"},
                    {"name": "Set default AI provider", "value": "provider"},
                    {"name": "Set default model per provider", "value": "models"},
                    {"name": "Set translation prompt refinement", "value": "refine"},
                    {"name": "Back", "value": "back"},
                ]
            ) or "back"
        else:
            print()
            print("1) Reconfigure API keys (ASC + AI)")
            print("2) Set default AI provider")
            print("3) Set default model per provider")
            print("4) Set translation prompt refinement")
            print("5) Back")
            raw = input("Select (1-5): ").strip()
            choice = {"1": "keys", "2": "provider", "3": "models", "4": "refine", "5": "back"}.get(raw, "back")

        if choice == "keys":
            # Run the setup wizard to re-enter keys
            ok = self.setup_wizard()
            if ok:
                self.setup_ai_providers()
            return True
        if choice == "provider":
            # Pick default provider among configured
            provs = self.ai_manager.list_providers()
            if not provs:
                print_error("No AI providers configured. Run setup first.")
                return True
            if self.ui.available():
                cur = self.config.get_default_ai_provider()
                selection = self.ui.select(
                    "Select default provider",
                    [{"name": p + ("  (current)" if p == cur else ""), "value": p} for p in provs],
                    add_back=True,
                )
                if not selection:
                    return True
                self.config.set_default_ai_provider(selection)
                print_success(f"Default AI provider set to: {selection}")
            else:
                cur = self.config.get_default_ai_provider()
                for i, p in enumerate(provs, 1):
                    star = " *current" if p == cur else ""
                    print(f"{i}. {p}{star}")
                raw = input("Select default provider (number) or Enter to clear: ").strip()
                if not raw:
                    self.config.set_default_ai_provider("")
                    print_success("Default AI provider cleared")
                else:
                    try:
                        idx = int(raw); assert 1 <= idx <= len(provs)
                        self.config.set_default_ai_provider(provs[idx - 1])
                        print_success(f"Default AI provider set to: {provs[idx - 1]}")
                    except Exception:
                        print_error("Invalid selection")
            return True
        if choice == "models":
            # Set default model for a provider
            provs_cfg = self.config.load_providers()
            prov_keys = [p for p in ["anthropic", "openai", "google"] if p in provs_cfg]
            if self.ui.available():
                cur_provider = self.config.get_default_ai_provider()
                pick = self.ui.select(
                    "Select provider to configure",
                    [{"name": (p + ("  (default provider)" if p == cur_provider else "")), "value": p} for p in prov_keys],
                    add_back=True,
                )
                if not pick:
                    return True
                models = self.config.list_provider_models(pick) or []
                if not models:
                    print_error("No models listed for this provider in config/providers.json")
                    return True
                cur_model = self.config.get_default_model(pick)
                sel_model = self.ui.select(
                    "Select default model",
                    [{"name": (m + ("  (current)" if m == cur_model else "")), "value": m} for m in models],
                    add_back=True,
                )
                if not sel_model:
                    return True
                if self.config.set_default_model(pick, sel_model):
                    print_success(f"Default model for {pick} set to: {sel_model}")
                    # Reinitialize providers to apply
                    self.setup_ai_providers()
                else:
                    print_error("Failed to set default model (not in list?)")
            else:
                # Show provider list with default provider marker and current model
                cur_provider = self.config.get_default_ai_provider()
                print("Providers available to configure:")
                for p in prov_keys:
                    tag = " (default provider)" if p == cur_provider else ""
                    cur_model = self.config.get_default_model(p) or "<unset>"
                    print(f"  • {p}{tag} — current model: {cur_model}")
                pick = input("Enter provider key to configure (anthropic/openai/google): ").strip()
                if pick not in prov_keys:
                    print_error("Invalid provider key")
                    return True
                models = self.config.list_provider_models(pick) or []
                if not models:
                    print_error("No models listed for this provider in config/providers.json")
                    return True
                print("Models:")
                cur_model = self.config.get_default_model(pick)
                for i, m in enumerate(models, 1):
                    star = " *current" if m == cur_model else ""
                    print(f"{i}. {m}{star}")
                raw = input("Select model (number): ").strip()
                try:
                    idx = int(raw); assert 1 <= idx <= len(models)
                    model = models[idx - 1]
                    if self.config.set_default_model(pick, model):
                        print_success(f"Default model for {pick} set to: {model}")
                        self.setup_ai_providers()
                    else:
                        print_error("Failed to set default model")
                except Exception:
                    print_error("Invalid selection")
            return True
        if choice == "refine":
            # Set global prompt refinement phrase
            current = self.config.get_prompt_refinement() or ""
            print_info("Set a short phrase to guide translations (leave blank to clear).")
            print(f"Current: '{current}'")
            phrase = None
            if self.ui.available():
                phrase = self.ui.text("Enter prompt refinement (optional): ")
            if phrase is None:
                phrase = input("Enter prompt refinement (optional): ").strip()
            # Accept blanks to clear
            self.config.set_prompt_refinement(phrase)
            print_success("Prompt refinement updated")
            return True
        # back or unknown
        return True
    
    def show_logo(self):
        """Display ASCII art logo."""
        print()
        print("  ╔════════════════════════════════════════════════════════╗")
        print("  ║                                                        ║")
        print("  ║      ████████ ██████   █████  ███   ██ ███████         ║")
        print("  ║         ██    ██   ██ ██   ██ ████  ██ ██              ║")
        print("  ║         ██    ██████  ███████ ██ ██ ██ ███████         ║")
        print("  ║         ██    ██   ██ ██   ██ ██  ████      ██         ║")
        print("  ║         ██    ██   ██ ██   ██ ██   ███ ███████         ║")
        print("  ║                                                        ║")
        print("  ║      ██       █████  ████████ ███████ \033[38;5;208m██████\033[0m           ║")
        print("  ║      ██      ██   ██    ██    ██      \033[38;5;208m██   ██\033[0m          ║")
        print("  ║      ██      ███████    ██    █████   \033[38;5;208m██████\033[0m           ║")
        print("  ║      ██      ██   ██    ██    ██      \033[38;5;208m██   ██\033[0m          ║")
        print("  ║      ███████ ██   ██    ██    ███████ \033[38;5;208m██   ██\033[0m          ║")
        print("  ║                                                        ║")
        print("  ║         🌍 App Store Connect Localization Tool         ║")
        print("  ║             Multi-AI Provider Translation              ║")
        print("  ║                                                        ║")
        print("  ╚════════════════════════════════════════════════════════╝")
        print()
    
    def run(self):
        """Main application loop."""
        self.show_logo()
        
        # Initialize App Store Connect client
        if not self.setup_app_store_client():
            return
        
        # Check if AI providers are available
        if not self.ai_manager.list_providers():
            print_error("No AI providers configured. Please run setup.")
            if not self.setup_wizard():
                return
        
        # Main application loop
        while True:
            try:
                if not self.show_main_menu():
                    break
            except KeyboardInterrupt:
                print()
                print_info("Exiting TranslateR...")
                break
            except Exception as e:
                print_error(f"An error occurred: {e}")
                input("Press Enter to continue...")


def main():
    """Main entry point for TranslateR application."""
    try:
        cli = TranslateRCLI()
        cli.run()
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print_error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
