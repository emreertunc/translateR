"""
App Store Connect API Client

Handles all interactions with Apple's App Store Connect API for managing
app metadata and localizations.
"""

import jwt
import time
import requests
from typing import Dict, Any, Optional, List
import random


class AppStoreConnectClient:
    """Client for interacting with App Store Connect API."""
    
    BASE_URL = "https://api.appstoreconnect.apple.com/v1"
    
    def __init__(self, key_id: str, issuer_id: str, private_key: str):
        """
        Initialize the App Store Connect client.
        
        Args:
            key_id: API Key ID from App Store Connect
            issuer_id: Issuer ID from App Store Connect
            private_key: Private key content from .p8 file
        """
        self.key_id = key_id
        self.issuer_id = issuer_id
        self.private_key = private_key
    
    def _generate_token(self) -> str:
        """Generate JWT token for API authentication."""
        payload = {
            "iss": self.issuer_id,
            "exp": int(time.time()) + 1200,  # 20 minutes
            "aud": "appstoreconnect-v1"
        }
        headers = {
            "alg": "ES256",
            "kid": self.key_id,
            "typ": "JWT"
        }
        return jwt.encode(payload, self.private_key, algorithm="ES256", headers=headers)
    
    def _request(self, method: str, endpoint: str, 
                 params: Optional[Dict[str, Any]] = None, 
                 data: Optional[Dict[str, Any]] = None,
                 max_retries: int = 3) -> Any:
        """Make authenticated request to App Store Connect API with retry logic."""
        headers = {
            "Authorization": f"Bearer {self._generate_token()}",
            "Content-Type": "application/json"
        }
        url = f"{self.BASE_URL}/{endpoint}"
        
        for attempt in range(max_retries + 1):
            try:
                response = requests.request(method, url, headers=headers, params=params, json=data)
                response.raise_for_status()
                return response.json()
            except requests.exceptions.HTTPError as e:
                if response.status_code == 409 and attempt < max_retries:
                    # Conflict error - retry with exponential backoff
                    wait_time = (2 ** attempt) + random.uniform(0, 1)
                    print(f"⚠️  API conflict detected, retrying in {wait_time:.1f}s (attempt {attempt + 1}/{max_retries + 1})...")
                    time.sleep(wait_time)
                    continue
                else:
                    raise e
    
    def get_apps(self) -> Any:
        """Get list of apps."""
        return self._request("GET", "apps")

    def get_app(self, app_id: str) -> Any:
        """Get a single app by ID."""
        return self._request("GET", f"apps/{app_id}")
    
    def get_latest_app_store_version(self, app_id: str) -> Optional[str]:
        """Get the latest App Store version ID for an app."""
        response = self._request("GET", f"apps/{app_id}/appStoreVersions")
        versions = response.get("data", [])
        if versions:
            return versions[0]["id"]
        return None
    
    def get_app_store_version_localizations(self, version_id: str) -> Any:
        """Get all localizations for a specific App Store version."""
        return self._request("GET", f"appStoreVersions/{version_id}/appStoreVersionLocalizations")
    
    def get_app_store_version_localization(self, localization_id: str) -> Any:
        """Get a specific localization by ID."""
        return self._request("GET", f"appStoreVersionLocalizations/{localization_id}")
    
    def create_app_store_version_localization(self, version_id: str, locale: str,
                                            description: str, keywords: str = None,
                                            promotional_text: str = None,
                                            whats_new: str = None) -> Any:
        """
        Create a new localization for an App Store version.
        
        Args:
            version_id: App Store version ID
            locale: Language locale code (e.g., 'en-US')
            description: App description (max 4000 chars)
            keywords: App keywords (max 100 chars)
            promotional_text: Promotional text (max 170 chars)
            whats_new: What's new text (max 4000 chars)
        """
        data = {
            "data": {
                "type": "appStoreVersionLocalizations",
                "attributes": {
                    "locale": locale,
                    "description": description
                },
                "relationships": {
                    "appStoreVersion": {
                        "data": {
                            "type": "appStoreVersions",
                            "id": version_id
                        }
                    }
                }
            }
        }
        
        # Add optional fields
        attributes = data["data"]["attributes"]
        if keywords:
            attributes["keywords"] = keywords
        if promotional_text:
            attributes["promotionalText"] = promotional_text
        if whats_new:
            attributes["whatsNew"] = whats_new
        
        return self._request("POST", "appStoreVersionLocalizations", data=data)
    
    def update_app_store_version_localization(self, localization_id: str,
                                            description: str = None,
                                            keywords: str = None,
                                            promotional_text: str = None,
                                            whats_new: str = None) -> Any:
        """
        Update an existing App Store version localization.
        
        Args:
            localization_id: Localization ID to update
            description: App description (max 4000 chars)
            keywords: App keywords (max 100 chars)
            promotional_text: Promotional text (max 170 chars)
            whats_new: What's new text (max 4000 chars)
        """
        # First get current localization to check for changes
        try:
            current = self.get_app_store_version_localization(localization_id)
            current_attrs = current.get("data", {}).get("attributes", {})
            
            # Build attributes dict with only changed values
            attributes = {}
            
            if description is not None and description != current_attrs.get("description"):
                attributes["description"] = description
            
            if keywords is not None and keywords != current_attrs.get("keywords"):
                attributes["keywords"] = keywords
            
            if promotional_text is not None and promotional_text != current_attrs.get("promotionalText"):
                attributes["promotionalText"] = promotional_text
            
            if whats_new is not None and whats_new != current_attrs.get("whatsNew"):
                # Ensure what's new doesn't exceed character limit
                if len(whats_new) > 4000:
                    whats_new = whats_new[:3997] + "..."
                attributes["whatsNew"] = whats_new
            
            # Only make request if there are changes
            if attributes:
                data = {
                    "data": {
                        "type": "appStoreVersionLocalizations",
                        "id": localization_id,
                        "attributes": attributes
                    }
                }
                return self._request("PATCH", f"appStoreVersionLocalizations/{localization_id}", data=data)
            else:
                return current  # No changes needed
                
        except Exception as e:
            # Fallback to simpler update if getting current localization fails
            data = {
                "data": {
                    "type": "appStoreVersionLocalizations",
                    "id": localization_id,
                    "attributes": {}
                }
            }
            
            attributes = data["data"]["attributes"]
            if description is not None:
                attributes["description"] = description
            if keywords is not None:
                attributes["keywords"] = keywords
            if promotional_text is not None:
                attributes["promotionalText"] = promotional_text
            if whats_new is not None:
                if len(whats_new) > 4000:
                    whats_new = whats_new[:3997] + "..."
                attributes["whatsNew"] = whats_new
            
            return self._request("PATCH", f"appStoreVersionLocalizations/{localization_id}", data=data)
    
    def get_app_infos(self, app_id: str) -> Any:
        """Get app infos for an app."""
        return self._request("GET", f"apps/{app_id}/appInfos")
    
    def get_app_info_localizations(self, app_info_id: str) -> Any:
        """Get localizations for a specific app info."""
        return self._request("GET", f"appInfos/{app_info_id}/appInfoLocalizations")
    
    def get_app_info_localization(self, localization_id: str) -> Any:
        """Get a specific app info localization by ID."""
        return self._request("GET", f"appInfoLocalizations/{localization_id}")
    
    def create_app_info_localization(self, app_info_id: str, locale: str,
                                   name: str = None, subtitle: str = None) -> Any:
        """
        Create a new app info localization.
        
        Args:
            app_info_id: App Info ID
            locale: Language locale code
            name: App name (max 30 chars)
            subtitle: App subtitle (max 30 chars)
        """
        data = {
            "data": {
                "type": "appInfoLocalizations",
                "attributes": {
                    "locale": locale
                },
                "relationships": {
                    "appInfo": {
                        "data": {
                            "type": "appInfos",
                            "id": app_info_id
                        }
                    }
                }
            }
        }
        
        attributes = data["data"]["attributes"]
        if name:
            if len(name) > 30:
                name = name[:30]
            attributes["name"] = name
        if subtitle:
            if len(subtitle) > 30:
                subtitle = subtitle[:30]
            attributes["subtitle"] = subtitle
        
        return self._request("POST", "appInfoLocalizations", data=data)
    
    def update_app_info_localization(self, localization_id: str,
                                   name: str = None, subtitle: str = None) -> Any:
        """
        Update an existing app info localization.
        
        Args:
            localization_id: App Info Localization ID to update
            name: App name (max 30 chars)
            subtitle: App subtitle (max 30 chars)
        """
        # Best-effort read of current values. If it fails, still attempt PATCH once.
        current = None
        current_attrs = {}
        try:
            current = self.get_app_info_localization(localization_id)
            current_attrs = current.get("data", {}).get("attributes", {})
        except Exception:
            current = None
            current_attrs = {}
        
        attributes = {}
        
        if name is not None and name != current_attrs.get("name"):
            if len(name) > 30:
                name = name[:30]
            attributes["name"] = name
        
        if subtitle is not None and subtitle != current_attrs.get("subtitle"):
            if len(subtitle) > 30:
                subtitle = subtitle[:30]
            attributes["subtitle"] = subtitle
        
        if not attributes:
            return current if current is not None else {"data": {"id": localization_id, "attributes": current_attrs}}
        
        data = {
            "data": {
                "type": "appInfoLocalizations",
                "id": localization_id,
                "attributes": attributes
            }
        }
        
        return self._request("PATCH", f"appInfoLocalizations/{localization_id}", data=data)
    
    def find_primary_app_info_id(self, app_id: str) -> Optional[str]:
        """
        Find the primary app info ID for an app.
        Prefers PREPARE_FOR_SUBMISSION state, falls back to first available.
        """
        try:
            app_infos = self.get_app_infos(app_id)
            infos = app_infos.get("data", [])
            
            if not infos:
                return None
            
            for info in infos:
                state = info.get("attributes", {}).get("appStoreState")
                if state == "PREPARE_FOR_SUBMISSION":
                    return info["id"]
            
            return infos[0]["id"]
            
        except Exception:
            return None
    
    def copy_localization_from_previous_version(self, source_version_id: str, 
                                               target_version_id: str, 
                                               locale: str) -> bool:
        """
        Copy localization data from one version to another.
        
        Args:
            source_version_id: Source App Store version ID
            target_version_id: Target App Store version ID  
            locale: Language locale to copy
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Get source localization
            source_localizations = self.get_app_store_version_localizations(source_version_id)
            source_data = None
            
            for loc in source_localizations.get("data", []):
                if loc["attributes"]["locale"] == locale:
                    source_data = loc["attributes"]
                    break
            
            if not source_data:
                return False
            
            # Check if target localization already exists
            target_localizations = self.get_app_store_version_localizations(target_version_id)
            target_localization_id = None
            
            for loc in target_localizations.get("data", []):
                if loc["attributes"]["locale"] == locale:
                    target_localization_id = loc["id"]
                    break
            
            # Update or create localization
            if target_localization_id:
                self.update_app_store_version_localization(
                    localization_id=target_localization_id,
                    description=source_data.get("description"),
                    keywords=source_data.get("keywords"),
                    promotional_text=source_data.get("promotionalText"),
                    whats_new=source_data.get("whatsNew")
                )
            else:
                self.create_app_store_version_localization(
                    version_id=target_version_id,
                    locale=locale,
                    description=source_data.get("description", ""),
                    keywords=source_data.get("keywords"),
                    promotional_text=source_data.get("promotionalText"),
                    whats_new=source_data.get("whatsNew")
                )
            
            return True
            
        except Exception as e:
            print(f"Error copying localization: {e}")
            return False
    
