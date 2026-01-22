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
import time
from typing import Optional, Dict, Any, List

from config import ConfigManager
from app_store_client import AppStoreConnectClient
from ai_providers import AIProviderManager, AnthropicProvider, OpenAIProvider, GoogleGeminiProvider
from utils import (
    APP_STORE_LOCALES, FIELD_LIMITS, 
    detect_base_language, truncate_keywords, get_field_limit,
    print_success, print_error, print_warning, print_info, format_progress,
    export_existing_localizations
)


class TranslateRCLI:
    """Main CLI interface for TranslateR application."""
    
    def __init__(self):
        self.config = ConfigManager()
        self.asc_client = None
        self.ai_manager = AIProviderManager()
        self.setup_ai_providers()
    
    def setup_ai_providers(self):
        """Initialize AI providers from configuration."""
        try:
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
            # Read private key file
            with open(asc_config["private_key_path"], "r") as f:
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
        
        key_id = input("Enter your API Key ID: ").strip()
        issuer_id = input("Enter your Issuer ID: ").strip()
        private_key_path = input("Enter path to your .p8 private key file (e.g., AuthKey_ABC123.p8 if in project directory): ").strip()
        
        # Validate private key file
        if not os.path.exists(private_key_path):
            print_error(f"Private key file not found: {private_key_path}")
            return False
        
        # Save App Store Connect config
        api_keys = self.config.load_api_keys()
        api_keys["app_store_connect"] = {
            "key_id": key_id,
            "issuer_id": issuer_id,
            "private_key_path": private_key_path
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
        
        # Save configuration
        self.config.save_api_keys(api_keys)
        print_success("Configuration saved successfully!")
        
        # Reinitialize clients
        self.setup_ai_providers()
        return self.setup_app_store_client()

    def _prompt_manual_app_id(self) -> Optional[str]:
        """Prompt user to enter an App ID manually."""
        app_id = input("Enter your App ID: ").strip()
        if not app_id:
            print_error("App ID is required")
            return None
        return app_id

    def _select_saved_app_id(self, saved_apps: Dict[str, str]) -> Optional[str]:
        """Prompt user to select an App ID from saved apps."""
        app_ids = list(saved_apps.keys())
        print()
        print("Saved apps:")
        for i, app_id in enumerate(app_ids, 1):
            app_name = saved_apps.get(app_id, "Unknown")
            print(f"{i}. {app_name} ({app_id})")
        
        while True:
            choice = input("Select app (number): ").strip()
            if not choice:
                print_warning("App selection cancelled")
                return None
            try:
                index = int(choice)
                if 1 <= index <= len(app_ids):
                    return app_ids[index - 1]
                print_error("Invalid choice")
            except ValueError:
                print_error("Please enter a number")

    def _get_app_id(self) -> Optional[str]:
        """Get App ID from saved list or manual input."""
        saved_apps = self.config.load_saved_apps()
        if saved_apps:
            print()
            print("App ID options:")
            print("1. Choose from saved apps")
            print("2. Enter a new App ID")
            
            while True:
                choice = input("Select option (1-2): ").strip()
                if choice == "1":
                    return self._select_saved_app_id(saved_apps)
                if choice == "2":
                    return self._prompt_manual_app_id()
                print_error("Invalid choice. Please select 1 or 2.")
        
        return self._prompt_manual_app_id()

    def _fetch_app_name(self, app_id: str) -> Optional[str]:
        """Fetch app name from App Store Connect."""
        try:
            response = self.asc_client.get_app(app_id)
            return response.get("data", {}).get("attributes", {}).get("name")
        except Exception as e:
            print_warning(f"Failed to fetch app name: {e}")
            return None

    def _maybe_save_app_id(self, app_id: str, app_name: Optional[str] = None):
        """Save or update app ID/name pair after a successful operation."""
        if not app_id:
            return
        
        saved_apps = self.config.load_saved_apps()
        existing_name = saved_apps.get(app_id)
        if existing_name:
            if not app_name:
                app_name = self._fetch_app_name(app_id)
            if app_name and app_name != existing_name:
                saved_apps[app_id] = app_name
                self.config.save_saved_apps(saved_apps)
                print_info("Saved app name updated")
            return
        
        confirm = input("Save this App ID for future use? (y/n): ").strip().lower()
        if confirm not in ["y", "yes"]:
            return
        
        if not app_name:
            app_name = self._fetch_app_name(app_id)
        
        if not app_name:
            app_name = input("Enter a name for this App ID (leave blank to skip): ").strip()
        
        if not app_name:
            print_warning("App ID was not saved")
            return
        
        saved_apps[app_id] = app_name
        self.config.save_saved_apps(saved_apps)
        print_success("App ID saved")

    def _manage_saved_apps(self):
        """Manage saved app IDs (delete/rename/clear)."""
        saved_apps = self.config.load_saved_apps()
        if not saved_apps:
            print_info("No saved apps found")
            return
        
        while True:
            print()
            print("Saved apps:")
            app_ids = list(saved_apps.keys())
            for i, app_id in enumerate(app_ids, 1):
                app_name = saved_apps.get(app_id, "Unknown")
                print(f"{i}. {app_name} ({app_id})")
            
            print()
            print("Manage options:")
            print("1. Delete an app")
            print("2. Rename an app")
            print("3. Clear all saved apps")
            print("4. Back")
            
            choice = input("Select option (1-4): ").strip()
            if choice == "1":
                app_id = self._select_saved_app_id(saved_apps)
                if not app_id:
                    continue
                confirm = input(f"Delete {saved_apps.get(app_id, 'Unknown')}? (y/n): ").strip().lower()
                if confirm in ["y", "yes"]:
                    saved_apps.pop(app_id, None)
                    self.config.save_saved_apps(saved_apps)
                    print_success("Saved app deleted")
                    if not saved_apps:
                        print_info("No saved apps remaining")
                        return
            elif choice == "2":
                app_id = self._select_saved_app_id(saved_apps)
                if not app_id:
                    continue
                new_name = input("Enter new app name: ").strip()
                if not new_name:
                    print_warning("Rename cancelled")
                    continue
                saved_apps[app_id] = new_name
                self.config.save_saved_apps(saved_apps)
                print_success("Saved app renamed")
            elif choice == "3":
                confirm = input("Clear all saved apps? (y/n): ").strip().lower()
                if confirm in ["y", "yes"]:
                    saved_apps = {}
                    self.config.save_saved_apps(saved_apps)
                    print_success("All saved apps cleared")
                    return
            elif choice == "4":
                return
            else:
                print_error("Invalid choice. Please select 1-4.")
    
    def show_main_menu(self):
        """Display main menu and handle user choice."""
        print()
        print("🌍 TranslateR - Choose your workflow:")
        print("1. 🌐 Translation Mode - Translate to new languages")
        print("2. 🔄 Update Mode - Update existing localizations")
        print("3. 📋 Copy Mode - Copy from previous version") 
        print("4. 🚀 Full Setup Mode - Complete localization setup")
        print("5. 📱 App Name & Subtitle Mode - Translate app name and subtitle")
        print("6. 📄 Export Localizations - Export existing localizations to file")
        print("7. ⚙️  Configuration - Manage API keys and settings")
        print("8. ❌ Exit")
        print()
        
        choice = input("Select an option (1-8): ").strip()
        
        if choice == "1":
            return self.translation_mode()
        elif choice == "2":
            return self.update_mode()
        elif choice == "3":
            return self.copy_mode()
        elif choice == "4":
            return self.full_setup_mode()
        elif choice == "5":
            return self.app_name_subtitle_mode()
        elif choice == "6":
            return self.export_localizations_mode()
        elif choice == "7":
            return self.configuration_mode()
        elif choice == "8":
            print_info("Thank you for using TranslateR!")
            return False
        else:
            print_error("Invalid choice. Please select 1-8.")
            return True
    
    def translation_mode(self):
        """Handle translation workflow."""
        print_info("Translation Mode - Translate existing content to new languages")
        print()
        
        # Ask user what to translate
        print("Translation Options:")
        print("1. Metadata Only (description, keywords, promotional text, what's new)")
        print("2. Complete Translation (metadata + app name & subtitle)")
        print()
        
        translation_choice = input("Select translation type (1-2): ").strip()
        
        if translation_choice not in ['1', '2']:
            print_error("Invalid selection. Please choose 1 or 2.")
            return True
            
        include_app_info = translation_choice == '2'
        
        try:
            # Get app ID from user
            app_id = self._get_app_id()
            if not app_id:
                return True
            
            # Get latest app store version
            version_id = self.asc_client.get_latest_app_store_version(app_id)
            if not version_id:
                print_error("No App Store version found for this app")
                return True
            
            print_success(f"Found latest version: {version_id}")
            
            # Get existing localizations
            localizations_response = self.asc_client.get_app_store_version_localizations(version_id)
            localizations = localizations_response.get("data", [])
            
            if not localizations:
                print_error("No existing localizations found")
                return True
            
            # Detect base language
            base_locale = detect_base_language(localizations)
            if not base_locale:
                print_error("Could not detect base language")
                return True
            
            print_info(f"Detected base language: {base_locale} ({APP_STORE_LOCALES.get(base_locale, 'Unknown')})")
            
            # Get base localization data
            base_data = None
            for loc in localizations:
                if loc["attributes"]["locale"] == base_locale:
                    base_data = loc["attributes"]
                    break
            
            if not base_data:
                print_error("Could not find base localization data")
                return True
            
            # Show available target languages
            print()
            print("Available target languages:")
            existing_locales = {loc["attributes"]["locale"] for loc in localizations}
            available_targets = {k: v for k, v in APP_STORE_LOCALES.items() 
                               if k not in existing_locales and k != base_locale}
            
            if not available_targets:
                print_warning("All supported languages are already localized")
                return True
            
            # Display available languages in chunks
            languages_list = list(available_targets.items())
            for i, (locale, name) in enumerate(languages_list[:20], 1):  # Show first 20
                print(f"{i:2d}. {locale:8} - {name}")
            
            if len(languages_list) > 20:
                print(f"... and {len(languages_list) - 20} more languages")
            
            print()
            print("Enter target language locales (comma-separated, e.g., 'de-DE,fr-FR,es-ES'):")
            target_input = input("Target languages: ").strip()
            
            if not target_input:
                print_warning("No target languages selected")
                return True
            
            # Parse target languages
            target_locales = [locale.strip() for locale in target_input.split(",")]
            invalid_locales = [loc for loc in target_locales if loc not in available_targets]
            
            if invalid_locales:
                print_error(f"Invalid language codes: {', '.join(invalid_locales)}")
                return True
            
            # Select AI provider
            providers = self.ai_manager.list_providers()
            if len(providers) == 1:
                selected_provider = providers[0]
                print_info(f"Using AI provider: {selected_provider}")
            else:
                print()
                print("Available AI providers:")
                for i, provider in enumerate(providers, 1):
                    print(f"{i}. {provider}")
                
                while True:
                    try:
                        choice = int(input("Select AI provider (number): ").strip())
                        if 1 <= choice <= len(providers):
                            selected_provider = providers[choice - 1]
                            break
                        else:
                            print_error("Invalid choice")
                    except ValueError:
                        print_error("Please enter a number")
            
            provider = self.ai_manager.get_provider(selected_provider)
            
            # Start translation process
            print()
            print_info(f"Starting translation for {len(target_locales)} languages...")
            success_count = 0
            
            for i, target_locale in enumerate(target_locales, 1):
                language_name = APP_STORE_LOCALES[target_locale]
                print()
                print(format_progress(i, len(target_locales), f"Translating to {language_name}"))
                
                try:
                    # Translate fields
                    translated_data = {}
                    
                    # Description
                    if base_data.get("description"):
                        print(f"  • Translating description...")
                        translated_data["description"] = provider.translate(
                            base_data["description"], 
                            language_name,
                            max_length=get_field_limit("description")
                        )
                    
                    # Keywords
                    if base_data.get("keywords"):
                        print(f"  • Translating keywords...")
                        translated_keywords = provider.translate(
                            base_data["keywords"], 
                            language_name,
                            max_length=get_field_limit("keywords"),
                            is_keywords=True
                        )
                        # Clean and format keywords properly
                        translated_keywords = translated_keywords.strip().rstrip('.')
                        translated_keywords = truncate_keywords(translated_keywords, 100)
                        translated_data["keywords"] = translated_keywords
                    
                    # Promotional text
                    if base_data.get("promotionalText"):
                        print(f"  • Translating promotional text...")
                        translated_data["promotional_text"] = provider.translate(
                            base_data["promotionalText"], 
                            language_name,
                            max_length=get_field_limit("promotional_text")
                        )
                    
                    # What's new
                    if base_data.get("whatsNew"):
                        print(f"  • Translating what's new...")
                        translated_data["whats_new"] = provider.translate(
                            base_data["whatsNew"], 
                            language_name,
                            max_length=get_field_limit("whats_new")
                        )
                    
                    # Create new localization
                    self.asc_client.create_app_store_version_localization(
                        version_id=version_id,
                        locale=target_locale,
                        description=translated_data.get("description", ""),
                        keywords=translated_data.get("keywords"),
                        promotional_text=translated_data.get("promotional_text"),
                        whats_new=translated_data.get("whats_new")
                    )
                    
                    print_success(f"  ✅ {language_name} translation completed")
                    success_count += 1
                    time.sleep(2)  # Rate limiting
                    
                except Exception as e:
                    error_message = str(e)
                    if "409" in error_message and "Conflict" in error_message:
                        # Check if localization actually exists or if it needs to be created in App Store Connect first
                        existing_localizations = self.asc_client.get_app_store_version_localizations(version_id)
                        locale_exists = any(loc["attributes"]["locale"] == target_locale 
                                          for loc in existing_localizations.get("data", []))
                        
                        if locale_exists:
                            print_error(f"  ❌ {language_name} localization already exists. Use Update Mode to modify it.")
                        else:
                            print_error(f"  ❌ {language_name} locale not available. Please add it in App Store Connect first.")
                    else:
                        print_error(f"  ❌ Failed to translate to {language_name}: {error_message}")
                    continue
            
            print()
            print_success("Metadata translation completed!")
            
            # If user requested complete translation, also translate app name & subtitle
            if include_app_info:
                print()
                print_info("Now translating app name & subtitle...")
                self._translate_app_info(app_id, target_locales, provider)
            
            if success_count > 0:
                self._maybe_save_app_id(app_id)
            
        except Exception as e:
            print_error(f"Translation workflow failed: {str(e)}")
        
        input("\nPress Enter to continue...")
        return True
    
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
                            max_length=30
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
                            max_length=30
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
        print_info("Update Mode - Update existing localizations with new content")
        print("Perfect for updating specific fields in existing languages (e.g., What's New for new version)")
        print()
        
        try:
            # Get app ID from user
            app_id = self._get_app_id()
            if not app_id:
                return True
            
            # Get latest app store version
            version_id = self.asc_client.get_latest_app_store_version(app_id)
            if not version_id:
                print_error("No App Store version found for this app")
                return True
            
            print_success(f"Found latest version: {version_id}")
            
            # Get existing localizations
            localizations_response = self.asc_client.get_app_store_version_localizations(version_id)
            localizations = localizations_response.get("data", [])
            
            if not localizations:
                print_error("No existing localizations found")
                return True
            
            # Detect base language
            base_locale = detect_base_language(localizations)
            if not base_locale:
                print_error("Could not detect base language")
                return True
            
            print_info(f"Detected base language: {base_locale} ({APP_STORE_LOCALES.get(base_locale, 'Unknown')})")
            
            # Get base localization data
            base_data = None
            for loc in localizations:
                if loc["attributes"]["locale"] == base_locale:
                    base_data = loc["attributes"]
                    break
            
            if not base_data:
                print_error("Could not find base localization data")
                return True
            
            # Show existing localizations (excluding base language)
            existing_locales = [loc["attributes"]["locale"] for loc in localizations if loc["attributes"]["locale"] != base_locale]
            
            if not existing_locales:
                print_warning("No other localizations found to update. Use Translation Mode to add new languages.")
                return True
            
            print()
            print("Existing localizations to update:")
            for i, locale in enumerate(existing_locales, 1):
                language_name = APP_STORE_LOCALES.get(locale, "Unknown")
                print(f"{i:2d}. {locale} ({language_name})")
            
            # Let user select which languages to update
            print()
            print("Select languages to update:")
            print("• Enter 'all' to update all languages")
            print("• Enter numbers (comma-separated, e.g., '1,3,5')")
            print("• Enter locale codes (comma-separated, e.g., 'zh-Hans,de-DE')")
            
            target_input = input("Languages to update: ").strip()
            
            if not target_input:
                print_warning("No languages selected")
                return True
            
            # Parse target languages
            if target_input.lower() == 'all':
                target_locales = existing_locales
            elif target_input.replace(',', '').replace(' ', '').isdigit():
                # Numbers selected
                try:
                    indices = [int(x.strip()) for x in target_input.split(',')]
                    target_locales = [existing_locales[i-1] for i in indices if 1 <= i <= len(existing_locales)]
                except (ValueError, IndexError):
                    print_error("Invalid numbers. Please use 1-based indexing.")
                    return True
            else:
                # Locale codes
                target_locales = [locale.strip() for locale in target_input.split(",")]
                invalid_locales = [loc for loc in target_locales if loc not in existing_locales]
                
                if invalid_locales:
                    print_error(f"Invalid or non-existing language codes: {', '.join(invalid_locales)}")
                    return True
            
            if not target_locales:
                print_warning("No valid languages selected")
                return True
            
            # Show which fields are available for update
            print()
            print("Available fields to update:")
            available_fields = []
            field_mapping = {
                "description": ("Description", base_data.get("description")),
                "keywords": ("Keywords", base_data.get("keywords")),
                "promotional_text": ("Promotional Text", base_data.get("promotionalText")),
                "whats_new": ("What's New", base_data.get("whatsNew"))
            }
            
            for key, (name, value) in field_mapping.items():
                if value:
                    available_fields.append(key)
                    preview = value[:50] + "..." if len(value) > 50 else value
                    print(f"  • {name}: {preview}")
            
            if not available_fields:
                print_error("No content found in base language to translate")
                return True
            
            # Let user select which fields to update
            print()
            print("Select fields to update:")
            print("• Enter 'all' to update all available fields")
            print("• Enter field names (comma-separated, e.g., 'whats_new,promotional_text')")
            
            fields_input = input("Fields to update: ").strip()
            
            if not fields_input:
                print_warning("No fields selected")
                return True
            
            if fields_input.lower() == 'all':
                selected_fields = available_fields
            else:
                selected_fields = [field.strip() for field in fields_input.split(",")]
                invalid_fields = [field for field in selected_fields if field not in available_fields]
                
                if invalid_fields:
                    print_error(f"Invalid field names: {', '.join(invalid_fields)}")
                    print(f"Available fields: {', '.join(available_fields)}")
                    return True
            
            # Select AI provider
            providers = self.ai_manager.list_providers()
            if len(providers) == 1:
                selected_provider = providers[0]
                print_info(f"Using AI provider: {selected_provider}")
            else:
                print()
                print("Available AI providers:")
                for i, provider in enumerate(providers, 1):
                    print(f"{i}. {provider}")
                
                while True:
                    try:
                        choice = int(input("Select AI provider (number): ").strip())
                        if 1 <= choice <= len(providers):
                            selected_provider = providers[choice - 1]
                            break
                        else:
                            print_error("Invalid choice")
                    except ValueError:
                        print_error("Please enter a number")
            
            provider = self.ai_manager.get_provider(selected_provider)
            
            # Show summary before starting
            print()
            print_info("Update Summary:")
            print(f"  • Languages: {len(target_locales)} ({', '.join(target_locales[:3])}{'...' if len(target_locales) > 3 else ''})")
            print(f"  • Fields: {len(selected_fields)} ({', '.join(selected_fields)})")
            print(f"  • AI Provider: {selected_provider}")
            
            confirm = input("\nProceed with updates? (y/n): ").strip().lower()
            if confirm not in ['y', 'yes']:
                print_info("Update cancelled")
                return True
            
            # Start update process
            print()
            print_info(f"Starting updates for {len(target_locales)} languages...")
            
            # Get existing localization IDs
            localization_ids = {}
            for loc in localizations:
                locale = loc["attributes"]["locale"]
                if locale in target_locales:
                    localization_ids[locale] = loc["id"]
            
            success_count = 0
            for i, target_locale in enumerate(target_locales, 1):
                language_name = APP_STORE_LOCALES.get(target_locale, "Unknown")
                print()
                print(format_progress(i, len(target_locales), f"Updating {language_name}"))
                
                if target_locale not in localization_ids:
                    print_error(f"  ❌ Localization ID not found for {language_name}")
                    continue
                
                try:
                    # Prepare update data
                    update_data = {}
                    
                    for field in selected_fields:
                        field_name, source_content = field_mapping[field]
                        if source_content:
                            print(f"  • Translating {field_name.lower()}...")
                            
                            is_keywords = field == "keywords"
                            max_length = get_field_limit(field.replace("_", ""))
                            
                            translated_content = provider.translate(
                                source_content,
                                language_name,
                                max_length=max_length,
                                is_keywords=is_keywords
                            )
                            
                            if is_keywords:
                                # Clean and format keywords properly
                                translated_content = translated_content.strip().rstrip('.')
                                translated_content = truncate_keywords(translated_content)
                            
                            # Final safeguard: enforce character limits
                            if field == "keywords" and len(translated_content) > 100:
                                translated_content = truncate_keywords(translated_content, 100)
                            elif field == "promotional_text" and len(translated_content) > 170:
                                translated_content = translated_content[:170]
                            elif field == "description" and len(translated_content) > 4000:
                                translated_content = translated_content[:4000]
                            elif field == "whats_new" and len(translated_content) > 4000:
                                translated_content = translated_content[:4000]
                            
                            # Map to API field names
                            api_field_name = {
                                "description": "description",
                                "keywords": "keywords", 
                                "promotional_text": "promotional_text",
                                "whats_new": "whats_new"
                            }[field]
                            
                            update_data[api_field_name] = translated_content
                    
                    # Try to update the localization
                    try:
                        self.asc_client.update_app_store_version_localization(
                            localization_id=localization_ids[target_locale],
                            **update_data
                        )
                        print_success(f"  ✅ {language_name} updated successfully")
                        success_count += 1
                        
                    except Exception as update_error:
                        if "409" in str(update_error):
                            print_warning(f"  ⚠️  Update failed due to API conflict. This localization may be locked.")
                            print_error(f"  ❌ Skipping {language_name}: {str(update_error)}")
                            continue
                        else:
                            raise update_error
                    
                    time.sleep(3)  # Rate limiting
                    
                except Exception as e:
                    print_error(f"  ❌ Failed to update {language_name}: {str(e)}")
                    continue
            
            print()
            print_success(f"Update completed! {success_count}/{len(target_locales)} languages updated successfully")
            
            if success_count > 0:
                self._maybe_save_app_id(app_id)
            
        except Exception as e:
            print_error(f"Update workflow failed: {str(e)}")
        
        input("\nPress Enter to continue...")
        return True
    
    def copy_mode(self):
        """Handle copy workflow."""
        print_info("Copy Mode - Copy content from previous version")
        print()
        
        try:
            # Get app ID from user
            app_id = self._get_app_id()
            if not app_id:
                return True
            
            # Get all app store versions
            versions_response = self.asc_client._request("GET", f"apps/{app_id}/appStoreVersions")
            versions = versions_response.get("data", [])
            
            if len(versions) < 2:
                print_error("Need at least 2 versions to copy content between them")
                return True
            
            # Show available versions
            print("Available versions:")
            for i, version in enumerate(versions[:10], 1):  # Show last 10 versions
                attrs = version["attributes"]
                print(f"{i}. Version {attrs.get('versionString', 'Unknown')} - {attrs.get('appStoreState', 'Unknown')}")
            
            # Select source version
            print()
            while True:
                try:
                    source_choice = int(input("Select source version to copy FROM (number): ").strip())
                    if 1 <= source_choice <= len(versions):
                        source_version = versions[source_choice - 1]
                        break
                    else:
                        print_error("Invalid choice")
                except ValueError:
                    print_error("Please enter a number")
            
            # Select target version
            print()
            while True:
                try:
                    target_choice = int(input("Select target version to copy TO (number): ").strip())
                    if 1 <= target_choice <= len(versions) and target_choice != source_choice:
                        target_version = versions[target_choice - 1]
                        break
                    elif target_choice == source_choice:
                        print_error("Source and target versions cannot be the same")
                    else:
                        print_error("Invalid choice")
                except ValueError:
                    print_error("Please enter a number")
            
            source_version_id = source_version["id"]
            target_version_id = target_version["id"]
            
            print_info(f"Copying from version {source_version['attributes'].get('versionString')} to {target_version['attributes'].get('versionString')}")
            
            # Get localizations from source version
            source_localizations = self.asc_client.get_app_store_version_localizations(source_version_id)
            source_locales = source_localizations.get("data", [])
            
            if not source_locales:
                print_error("No localizations found in source version")
                return True
            
            # Get existing localizations in target version
            target_localizations = self.asc_client.get_app_store_version_localizations(target_version_id)
            target_locales = {loc["attributes"]["locale"]: loc["id"] for loc in target_localizations.get("data", [])}
            
            print()
            print(f"Found {len(source_locales)} localizations in source version")
            
            # Show which locales will be copied
            print("Locales to copy:")
            locales_to_copy = []
            for loc in source_locales:
                locale = loc["attributes"]["locale"]
                language_name = APP_STORE_LOCALES.get(locale, "Unknown")
                status = "UPDATE" if locale in target_locales else "CREATE"
                print(f"  • {locale} ({language_name}) - {status}")
                locales_to_copy.append(locale)
            
            print()
            confirm = input("Proceed with copying? (y/n): ").strip().lower()
            if confirm not in ['y', 'yes']:
                print_info("Copy operation cancelled")
                return True
            
            # Start copying process
            print()
            print_info(f"Starting copy for {len(locales_to_copy)} localizations...")
            
            success_count = 0
            for i, locale in enumerate(locales_to_copy, 1):
                language_name = APP_STORE_LOCALES.get(locale, "Unknown")
                print()
                print(format_progress(i, len(locales_to_copy), f"Copying {language_name}"))
                
                try:
                    success = self.asc_client.copy_localization_from_previous_version(
                        source_version_id, target_version_id, locale
                    )
                    
                    if success:
                        print_success(f"  ✅ {language_name} copied successfully")
                        success_count += 1
                    else:
                        print_error(f"  ❌ Failed to copy {language_name}")
                    
                    time.sleep(1)  # Rate limiting
                    
                except Exception as e:
                    print_error(f"  ❌ Error copying {language_name}: {str(e)}")
                    continue
            
            print()
            print_success(f"Copy workflow completed! {success_count}/{len(locales_to_copy)} localizations copied successfully")
            
            if success_count > 0:
                self._maybe_save_app_id(app_id)
            
        except Exception as e:
            print_error(f"Copy workflow failed: {str(e)}")
        
        input("\nPress Enter to continue...")
        return True
    
    def full_setup_mode(self):
        """Handle full setup workflow."""
        print_info("Full Setup Mode - Complete localization setup")
        print("This mode combines translation and copy workflows for comprehensive setup")
        print()
        
        try:
            # Get app ID from user
            app_id = self._get_app_id()
            if not app_id:
                return True
            
            # Get latest app store version
            version_id = self.asc_client.get_latest_app_store_version(app_id)
            if not version_id:
                print_error("No App Store version found for this app")
                return True
            
            print_success(f"Found latest version: {version_id}")
            
            # Get existing localizations
            localizations_response = self.asc_client.get_app_store_version_localizations(version_id)
            localizations = localizations_response.get("data", [])
            existing_locales = {loc["attributes"]["locale"] for loc in localizations}
            
            # Detect base language
            base_locale = detect_base_language(localizations)
            if not base_locale:
                print_error("Could not detect base language")
                return True
            
            print_info(f"Detected base language: {base_locale} ({APP_STORE_LOCALES.get(base_locale, 'Unknown')})")
            
            # Show current status
            print()
            print("Current localization status:")
            print(f"• Existing localizations: {len(existing_locales)}")
            for locale in sorted(existing_locales):
                language_name = APP_STORE_LOCALES.get(locale, "Unknown")
                print(f"  - {locale} ({language_name})")
            
            # Show missing languages
            missing_locales = set(APP_STORE_LOCALES.keys()) - existing_locales
            print(f"• Missing localizations: {len(missing_locales)}")
            
            if not missing_locales:
                print_info("All supported languages are already localized!")
                input("Press Enter to continue...")
                return True
            
            # Ask user what they want to do
            print()
            print("Full Setup Options:")
            print("1. Add ALL missing languages (translate all)")
            print("2. Add specific languages (choose which ones)")
            print("3. Cancel")
            
            while True:
                choice = input("Select option (1-3): ").strip()
                if choice in ['1', '2', '3']:
                    break
                print_error("Invalid choice. Please select 1-3.")
            
            if choice == '3':
                print_info("Full setup cancelled")
                return True
            
            # Determine target languages
            if choice == '1':
                target_locales = list(missing_locales)
                print_info(f"Will add all {len(target_locales)} missing languages")
            else:  # choice == '2'
                print()
                print("Missing languages:")
                missing_list = list(missing_locales)
                for i, locale in enumerate(missing_list[:20], 1):
                    language_name = APP_STORE_LOCALES[locale]
                    print(f"{i:2d}. {locale:8} - {language_name}")
                
                if len(missing_list) > 20:
                    print(f"... and {len(missing_list) - 20} more")
                
                print()
                print("Enter language locales (comma-separated, e.g., 'de-DE,fr-FR,es-ES'):")
                target_input = input("Target languages: ").strip()
                
                if not target_input:
                    print_warning("No target languages selected")
                    return True
                
                target_locales = [locale.strip() for locale in target_input.split(",")]
                invalid_locales = [loc for loc in target_locales if loc not in missing_locales]
                
                if invalid_locales:
                    print_error(f"Invalid or already existing language codes: {', '.join(invalid_locales)}")
                    return True
            
            # Get base localization data
            base_data = None
            for loc in localizations:
                if loc["attributes"]["locale"] == base_locale:
                    base_data = loc["attributes"]
                    break
            
            if not base_data:
                print_error("Could not find base localization data")
                return True
            
            # Check if base data has content
            if not any([base_data.get("description"), base_data.get("keywords"), 
                       base_data.get("promotionalText"), base_data.get("whatsNew")]):
                print_error("Base localization has no content to translate")
                return True
            
            # Select AI provider
            providers = self.ai_manager.list_providers()
            if len(providers) == 1:
                selected_provider = providers[0]
                print_info(f"Using AI provider: {selected_provider}")
            else:
                print()
                print("Available AI providers:")
                for i, provider in enumerate(providers, 1):
                    print(f"{i}. {provider}")
                
                while True:
                    try:
                        provider_choice = int(input("Select AI provider (number): ").strip())
                        if 1 <= provider_choice <= len(providers):
                            selected_provider = providers[provider_choice - 1]
                            break
                        else:
                            print_error("Invalid choice")
                    except ValueError:
                        print_error("Please enter a number")
            
            provider = self.ai_manager.get_provider(selected_provider)
            
            # Confirm before starting
            print()
            print_info(f"Ready to set up {len(target_locales)} new localizations:")
            for locale in target_locales[:10]:  # Show first 10
                language_name = APP_STORE_LOCALES[locale]
                print(f"  • {locale} ({language_name})")
            if len(target_locales) > 10:
                print(f"  ... and {len(target_locales) - 10} more")
            
            print()
            confirm = input("Proceed with full setup? (y/n): ").strip().lower()
            if confirm not in ['y', 'yes']:
                print_info("Full setup cancelled")
                return True
            
            # Start full setup process
            print()
            print_info(f"Starting full setup for {len(target_locales)} languages...")
            
            success_count = 0
            successful_locales = []
            for i, target_locale in enumerate(target_locales, 1):
                language_name = APP_STORE_LOCALES[target_locale]
                print()
                print(format_progress(i, len(target_locales), f"Setting up {language_name}"))
                
                try:
                    # Translate all available fields
                    translated_data = {}
                    
                    # Description
                    if base_data.get("description"):
                        print(f"  • Translating description...")
                        translated_data["description"] = provider.translate(
                            base_data["description"], 
                            language_name,
                            max_length=get_field_limit("description")
                        )
                    
                    # Keywords
                    if base_data.get("keywords"):
                        print(f"  • Translating keywords...")
                        translated_keywords = provider.translate(
                            base_data["keywords"], 
                            language_name,
                            max_length=get_field_limit("keywords"),
                            is_keywords=True
                        )
                        # Clean and format keywords properly
                        translated_keywords = translated_keywords.strip().rstrip('.')
                        translated_keywords = truncate_keywords(translated_keywords, 100)
                        translated_data["keywords"] = translated_keywords
                    
                    # Promotional text
                    if base_data.get("promotionalText"):
                        print(f"  • Translating promotional text...")
                        translated_data["promotional_text"] = provider.translate(
                            base_data["promotionalText"], 
                            language_name,
                            max_length=get_field_limit("promotional_text")
                        )
                    
                    # What's new
                    if base_data.get("whatsNew"):
                        print(f"  • Translating what's new...")
                        translated_data["whats_new"] = provider.translate(
                            base_data["whatsNew"], 
                            language_name,
                            max_length=get_field_limit("whats_new")
                        )
                    
                    # Create new localization
                    self.asc_client.create_app_store_version_localization(
                        version_id=version_id,
                        locale=target_locale,
                        description=translated_data.get("description", ""),
                        keywords=translated_data.get("keywords"),
                        promotional_text=translated_data.get("promotional_text"),
                        whats_new=translated_data.get("whats_new")
                    )
                    
                    print_success(f"  ✅ {language_name} setup completed")
                    success_count += 1
                    successful_locales.append(target_locale)
                    time.sleep(2)  # Rate limiting
                    
                except Exception as e:
                    error_message = str(e)
                    if "409" in error_message and "Conflict" in error_message:
                        # Check if localization actually exists or if it needs to be created in App Store Connect first
                        existing_localizations = self.asc_client.get_app_store_version_localizations(version_id)
                        locale_exists = any(loc["attributes"]["locale"] == target_locale 
                                          for loc in existing_localizations.get("data", []))
                        
                        if locale_exists:
                            print_error(f"  ❌ {language_name} localization already exists. Use Update Mode to modify it.")
                        else:
                            print_error(f"  ❌ {language_name} locale not available. Please add it in App Store Connect first.")
                    else:
                        print_error(f"  ❌ Failed to setup {language_name}: {error_message}")
                    continue
            
            print()
            print_success(f"Version localization completed! {success_count}/{len(target_locales)} languages set up successfully")
            
            # Now handle app name and subtitle translation for successfully created languages
            if success_count > 0:
                print()
                print_info("Setting up app name and subtitle translations...")
                
                # Get app info ID
                app_info_id = self.asc_client.find_primary_app_info_id(app_id)
                if app_info_id:
                    try:
                        # Get base app info localization
                        existing_app_info = self.asc_client.get_app_info_localizations(app_info_id)
                        base_app_info = None
                        app_info_localization_map = {}
                        
                        # Build map of existing app info localizations
                        for loc in existing_app_info.get("data", []):
                            locale = loc["attributes"]["locale"]
                            app_info_localization_map[locale] = loc["id"]
                            if locale == base_locale:
                                base_app_info = loc
                        
                        if base_app_info:
                            base_app_attrs = base_app_info["attributes"]
                            base_name = base_app_attrs.get("name", "")
                            base_subtitle = base_app_attrs.get("subtitle", "")
                            
                            if base_name or base_subtitle:
                                # Get updated app info localizations (App Store Connect creates them automatically)
                                time.sleep(1)  # Give App Store Connect time to create app info localizations
                                updated_app_info = self.asc_client.get_app_info_localizations(app_info_id)
                                
                                # Update the map with any new localizations
                                for loc in updated_app_info.get("data", []):
                                    locale = loc["attributes"]["locale"]
                                    app_info_localization_map[locale] = loc["id"]
                                
                                app_name_success_count = 0
                                for locale in successful_locales:
                                    language_name = APP_STORE_LOCALES[locale]
                                    
                                    if locale in app_info_localization_map:
                                        try:
                                            print(f"  • Setting up app name/subtitle for {language_name}...")
                                            
                                            # Prepare translation data
                                            translated_name = None
                                            translated_subtitle = None
                                            
                                            if base_name:
                                                translated_name = provider.translate(
                                                    base_name, 
                                                    language_name,
                                                    max_length=get_field_limit("name")
                                                )
                                            
                                            if base_subtitle:
                                                translated_subtitle = provider.translate(
                                                    base_subtitle, 
                                                    language_name,
                                                    max_length=get_field_limit("subtitle")
                                                )
                                            
                                            # Update existing app info localization
                                            self.asc_client.update_app_info_localization(
                                                localization_id=app_info_localization_map[locale],
                                                name=translated_name,
                                                subtitle=translated_subtitle
                                            )
                                            
                                            app_name_success_count += 1
                                            time.sleep(1)  # Rate limiting
                                            
                                        except Exception as e:
                                            print_error(f"    Failed to update app name/subtitle for {language_name}: {str(e)}")
                                            continue
                                    else:
                                        print_warning(f"    App info localization not found for {language_name}")
                                
                                print_success(f"App name/subtitle setup completed! {app_name_success_count}/{len(successful_locales)} languages configured")
                            else:
                                print_info("No app name or subtitle found in base language - skipping app name/subtitle translation")
                        else:
                            print_warning("Could not find base app info localization - skipping app name/subtitle translation")
                    
                    except Exception as e:
                        print_warning(f"App name/subtitle translation failed: {str(e)}")
                else:
                    print_warning("Could not find app info ID - skipping app name/subtitle translation")
            
            # Show final status
            final_localizations = self.asc_client.get_app_store_version_localizations(version_id)
            final_count = len(final_localizations.get("data", []))
            total_supported = len(APP_STORE_LOCALES)
            
            print()
            print_success(f"✅ Full setup completed! Translation and app name/subtitle setup finished")
            print_info(f"Your app now supports {final_count}/{total_supported} available App Store languages")
            coverage = (final_count / total_supported) * 100
            print_info(f"Localization coverage: {coverage:.1f}%")
            
            if success_count > 0:
                self._maybe_save_app_id(app_id)
            
        except Exception as e:
            print_error(f"Full setup failed: {str(e)}")
        
        input("\nPress Enter to continue...")
        return True
    
    def app_name_subtitle_mode(self):
        """Handle app name and subtitle translation workflow."""
        print_info("App Name & Subtitle Mode - Translate app name and subtitle")
        
        try:
            available_apps = self.asc_client.get_apps()
            apps = available_apps.get("data", [])
            
            if not apps:
                print_error("No apps found in your App Store Connect account")
                return True
            
            print()
            print("Available Apps:")
            for i, app in enumerate(apps, 1):
                app_name = app.get("attributes", {}).get("name", "Unknown")
                print(f"{i}. {app_name}")
            
            while True:
                try:
                    choice = int(input("Select app (number): ").strip())
                    if 1 <= choice <= len(apps):
                        selected_app = apps[choice - 1]
                        app_id = selected_app["id"]
                        app_name = selected_app.get("attributes", {}).get("name", "Unknown")
                        break
                    else:
                        print_error("Invalid choice")
                except ValueError:
                    print_error("Please enter a number")
            
            print_info(f"Selected app: {app_name}")
            
            app_info_id = self.asc_client.find_primary_app_info_id(app_id)
            if not app_info_id:
                print_error("Could not find app info for this app")
                return True
            
            existing_localizations = self.asc_client.get_app_info_localizations(app_info_id)
            existing_locales = []
            localization_map = {}
            
            for loc in existing_localizations.get("data", []):
                locale = loc["attributes"]["locale"]
                existing_locales.append(locale)
                localization_map[locale] = loc["id"]
            
            base_locale = detect_base_language(existing_localizations.get("data", []))
            if not base_locale:
                print_error("No base language found. Please create at least one app info localization first.")
                return True
            
            base_localization_id = localization_map[base_locale]
            base_data = self.asc_client.get_app_info_localization(base_localization_id)
            base_attrs = base_data.get("data", {}).get("attributes", {})
            
            base_name = base_attrs.get("name", "")
            base_subtitle = base_attrs.get("subtitle", "")
            
            if not base_name and not base_subtitle:
                print_error(f"No name or subtitle found in base language ({APP_STORE_LOCALES[base_locale]})")
                return True
            
            print()
            print_info(f"Base language: {APP_STORE_LOCALES[base_locale]}")
            if base_name:
                print(f"📱 Name: {base_name}")
            if base_subtitle:
                print(f"📝 Subtitle: {base_subtitle}")
            
            available_targets = [locale for locale in APP_STORE_LOCALES if locale != base_locale]
            
            print()
            print("Available target languages:")
            print(", ".join([f"{locale} ({APP_STORE_LOCALES[locale]})" for locale in available_targets[:10]]))
            if len(available_targets) > 10:
                print(f"... and {len(available_targets) - 10} more")
            
            target_input = input("Enter target language locales (comma-separated, e.g., 'de-DE,fr-FR,es-ES'): ").strip()
            
            if not target_input:
                print_warning("No target languages selected")
                return True
            
            target_locales = [locale.strip() for locale in target_input.split(",")]
            invalid_locales = [loc for loc in target_locales if loc not in available_targets]
            
            if invalid_locales:
                print_error(f"Invalid language codes: {', '.join(invalid_locales)}")
                return True
            
            providers = self.ai_manager.list_providers()
            if len(providers) == 1:
                selected_provider = providers[0]
                print_info(f"Using AI provider: {selected_provider}")
            else:
                print()
                print("Available AI providers:")
                for i, provider in enumerate(providers, 1):
                    print(f"{i}. {provider}")
                
                while True:
                    try:
                        choice = int(input("Select AI provider (number): ").strip())
                        if 1 <= choice <= len(providers):
                            selected_provider = providers[choice - 1]
                            break
                        else:
                            print_error("Invalid choice")
                    except ValueError:
                        print_error("Please enter a number")
            
            provider = self.ai_manager.get_provider(selected_provider)
            
            print()
            print_info(f"Starting app name & subtitle translation for {len(target_locales)} languages...")
            
            success_count = 0
            
            for i, target_locale in enumerate(target_locales, 1):
                language_name = APP_STORE_LOCALES[target_locale]
                print()
                print(format_progress(i, len(target_locales), f"Translating to {language_name}"))
                
                try:
                    translated_name = None
                    translated_subtitle = None
                    
                    if base_name:
                        print("  • Translating app name...")
                        translated_name = provider.translate(
                            text=base_name,
                            target_language=language_name,
                            max_length=30,
                            is_keywords=False
                        )
                    
                    if base_subtitle:
                        print("  • Translating app subtitle...")
                        translated_subtitle = provider.translate(
                            text=base_subtitle,
                            target_language=language_name,
                            max_length=30,
                            is_keywords=False
                        )
                    
                    if target_locale in existing_locales:
                        localization_id = localization_map[target_locale]
                        self.asc_client.update_app_info_localization(
                            localization_id=localization_id,
                            name=translated_name,
                            subtitle=translated_subtitle
                        )
                    else:
                        self.asc_client.create_app_info_localization(
                            app_info_id=app_info_id,
                            locale=target_locale,
                            name=translated_name,
                            subtitle=translated_subtitle
                        )
                    
                    print_success(f"  ✅ {language_name} translation completed")
                    success_count += 1
                    time.sleep(2)
                    
                except Exception as e:
                    error_message = str(e)
                    if "409" in error_message and "Conflict" in error_message:
                        existing_app_info_localizations = self.asc_client.get_app_info_localizations(app_info_id)
                        locale_exists = any(loc["attributes"]["locale"] == target_locale 
                                          for loc in existing_app_info_localizations.get("data", []))
                        
                        if locale_exists:
                            print_error(f"  ❌ {language_name} app info localization already exists. Contact support if this persists.")
                        else:
                            print_error(f"  ❌ {language_name} locale not available. Please add it in App Store Connect first.")
                    else:
                        print_error(f"  ❌ Failed to translate {language_name}: {error_message}")
                    continue
            
            print()
            print_success(f"App name & subtitle translation completed! {success_count}/{len(target_locales)} languages translated successfully")
            
        except Exception as e:
            print_error(f"App name & subtitle translation failed: {str(e)}")
        
        input("\nPress Enter to continue...")
        return True
    
    def export_localizations_mode(self):
        """Handle export existing localizations workflow."""
        print_info("Export Localizations Mode - Export all existing localizations to file")
        print()
        
        try:
            # Get app ID from user
            app_id = self._get_app_id()
            if not app_id:
                return True
            
            # Validate app ID exists by trying to get its versions
            try:
                version_test = self.asc_client.get_latest_app_store_version(app_id)
                if not version_test:
                    print_error("No App Store version found for this app. Please check your App ID.")
                    return True
            except Exception as e:
                print_error(f"Failed to find app with ID '{app_id}'. Please check your App ID.")
                if "404" in str(e):
                    print_error("App not found. Make sure you're using the correct App ID.")
                return True
            
            # Get app name for export file
            apps_response = self.asc_client.get_apps()
            app_name = "Unknown App"
            for app in apps_response.get("data", []):
                if app["id"] == app_id:
                    app_name = app.get("attributes", {}).get("name", "Unknown App")
                    break
            
            print_info(f"Found app: {app_name}")
            
            # Ask for which version to export
            print()
            print("Export options:")
            print("1. Latest App Store version")
            print("2. Specific version")
            
            version_choice = input("Select option (1-2): ").strip()
            
            version_string = "unknown"
            
            if version_choice == "1":
                # Get latest version with version string info
                try:
                    versions_response = self.asc_client._request("GET", f"apps/{app_id}/appStoreVersions")
                    versions = versions_response.get("data", [])
                    
                    if not versions:
                        print_error("No App Store version found for this app")
                        return True
                    
                    version_id = versions[0]["id"]
                    version_string = versions[0]["attributes"].get("versionString", "unknown")
                    print_success(f"Using latest version: {version_string} ({version_id})")
                except Exception as e:
                    print_error(f"Failed to get app versions: {str(e)}")
                    return True
            
            elif version_choice == "2":
                try:
                    versions_response = self.asc_client._request("GET", f"apps/{app_id}/appStoreVersions")
                    versions = versions_response.get("data", [])
                except Exception as e:
                    print_error(f"Failed to get app versions: {str(e)}")
                    return True
                
                if not versions:
                    print_error("No versions found for this app")
                    return True
                
                print()
                print("Available versions:")
                for i, version in enumerate(versions[:10], 1):
                    attrs = version["attributes"]
                    print(f"{i}. Version {attrs.get('versionString', 'Unknown')} - {attrs.get('appStoreState', 'Unknown')}")
                
                while True:
                    try:
                        choice = int(input("Select version (number): ").strip())
                        if 1 <= choice <= len(versions):
                            version_id = versions[choice - 1]["id"]
                            version_string = versions[choice - 1]["attributes"].get("versionString", "Unknown")
                            print_success(f"Selected version: {version_string}")
                            break
                        else:
                            print_error("Invalid choice")
                    except ValueError:
                        print_error("Please enter a number")
            
            else:
                print_error("Invalid choice")
                return True
            
            # Get version localizations
            print()
            print_info("Fetching version localizations...")
            localizations_response = self.asc_client.get_app_store_version_localizations(version_id)
            version_localizations = localizations_response.get("data", [])
            
            # Get app info localizations
            print_info("Fetching app info localizations...")
            app_info_id = self.asc_client.find_primary_app_info_id(app_id)
            app_info_localizations = []
            
            if app_info_id:
                app_info_response = self.asc_client.get_app_info_localizations(app_info_id)
                app_info_localizations = app_info_response.get("data", [])
            
            # Combine both types of localizations
            all_localizations = []
            
            # Process version localizations
            for version_loc in version_localizations:
                locale = version_loc.get("attributes", {}).get("locale")
                combined_attrs = version_loc.get("attributes", {}).copy()
                
                # Find matching app info localization
                for app_info_loc in app_info_localizations:
                    if app_info_loc.get("attributes", {}).get("locale") == locale:
                        app_info_attrs = app_info_loc.get("attributes", {})
                        if app_info_attrs.get("name"):
                            combined_attrs["name"] = app_info_attrs["name"]
                        if app_info_attrs.get("subtitle"):
                            combined_attrs["subtitle"] = app_info_attrs["subtitle"]
                        break
                
                all_localizations.append({
                    "id": version_loc.get("id"),
                    "type": version_loc.get("type"),
                    "attributes": combined_attrs
                })
            
            if not all_localizations:
                print_error("No localizations found for this app")
                return True
            
            print_success(f"Found {len(all_localizations)} localizations")
            
            # Export to file
            print()
            print_info("Creating export file...")
            export_path = export_existing_localizations(all_localizations, app_name, app_id, version_string)
            
            print_success(f"Export completed successfully!")
            print_info(f"File saved to: {export_path}")
            
            # Show summary
            locales_summary = []
            for loc in all_localizations[:5]:
                locale = loc["attributes"].get("locale", "Unknown")
                language_name = APP_STORE_LOCALES.get(locale, "Unknown")
                locales_summary.append(f"{locale} ({language_name})")
            
            if len(all_localizations) > 5:
                locales_summary.append(f"... and {len(all_localizations) - 5} more")
            
            print()
            print_info("Exported languages:")
            for lang in locales_summary:
                print(f"  • {lang}")
            
            self._maybe_save_app_id(app_id, app_name=app_name)
            
        except Exception as e:
            print_error(f"Export failed: {str(e)}")
        
        input("\nPress Enter to continue...")
        return True
    
    def configuration_mode(self):
        """Handle configuration management."""
        print_info("Configuration Mode - Manage your settings")
        
        print()
        print("Available AI Providers:")
        providers = self.ai_manager.list_providers()
        if providers:
            for provider in providers:
                print(f"✅ {provider}")
        else:
            print("❌ No AI providers configured")
        
        print()
        print("App Store Connect:", "✅ Configured" if self.asc_client else "❌ Not configured")
        
        print()
        saved_apps = self.config.load_saved_apps()
        print(f"Saved apps: {len(saved_apps)}")
        
        print()
        manage_saved = input("Do you want to manage saved apps? (y/n): ").strip().lower()
        if manage_saved in ['y', 'yes']:
            self._manage_saved_apps()
        
        print()
        reconfigure = input("Do you want to reconfigure settings? (y/n): ").strip().lower()
        if reconfigure in ['y', 'yes']:
            return self.setup_wizard()
        
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
