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
from urllib.parse import urlparse, parse_qs

from utils import get_field_limit


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
        """Make authenticated request to App Store Connect API with retry logic.

        Supports both v1 and v2 endpoints: when `endpoint` starts with "v2/" it
        uses the v2 base URL, otherwise defaults to v1.
        """
        headers = {
            "Authorization": f"Bearer {self._generate_token()}",
            "Content-Type": "application/json"
        }
        if endpoint.startswith("v2/"):
            url = f"https://api.appstoreconnect.apple.com/{endpoint}"
        elif endpoint.startswith("v1/"):
            url = f"https://api.appstoreconnect.apple.com/{endpoint}"
        else:
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
                    print(f"⚠️  API conflict detected for {url} (params={params}, data={data}), retrying in {wait_time:.1f}s (attempt {attempt + 1}/{max_retries + 1})...")
                    time.sleep(wait_time)
                    continue
                else:
                    raise e
    
    def get_apps(self, limit: int = 200) -> Any:
        """Get list of apps.

        Args:
            limit: Maximum number of apps to fetch (max 200)
        """
        params = {"limit": max(1, min(limit, 200))}
        return self._request("GET", "apps", params=params)

    def get_apps_page(self, limit: int = 50, cursor: Optional[str] = None) -> Dict[str, Any]:
        """Get a single page of apps with optional cursor-based pagination.

        Args:
            limit: Items per page (1-200)
            cursor: Optional cursor token from previous response's next link

        Returns:
            Dict with keys: 'data' (list of apps), 'next_cursor' (str or None)
        """
        params: Dict[str, Any] = {"limit": max(1, min(limit, 200))}
        if cursor:
            params["cursor"] = cursor
        resp = self._request("GET", "apps", params=params)
        next_link = resp.get("links", {}).get("next")
        next_cursor: Optional[str] = None
        if next_link:
            try:
                qs = parse_qs(urlparse(next_link).query)
                # App Store Connect uses 'cursor' param for pagination
                cur = qs.get("cursor", [])
                if cur:
                    next_cursor = cur[0]
            except Exception:
                next_cursor = None
        return {"data": resp.get("data", []), "next_cursor": next_cursor}
    
    def get_latest_app_store_version(self, app_id: str) -> Optional[str]:
        """Get the latest App Store version ID for an app."""
        response = self._request("GET", f"apps/{app_id}/appStoreVersions")
        versions = response.get("data", [])
        if versions:
            return versions[0]["id"]
        return None

    def get_latest_app_store_version_info(self, app_id: str) -> Optional[Dict[str, str]]:
        """Get latest App Store version info including human-readable version string.

        Returns a dict with keys: 'id', 'versionString', and 'appStoreState'.
        """
        response = self._request("GET", f"apps/{app_id}/appStoreVersions")
        versions = response.get("data", [])
        if not versions:
            return None
        v = versions[0]
        attrs = v.get("attributes", {})
        return {
            "id": v.get("id"),
            "versionString": attrs.get("versionString"),
            "appStoreState": attrs.get("appStoreState"),
        }
    
    def get_app_store_version_localizations(self, version_id: str) -> Any:
        """Get all localizations for a specific App Store version."""
        return self._request("GET", f"appStoreVersions/{version_id}/appStoreVersionLocalizations")
    
    def get_app_store_version_localization(self, localization_id: str) -> Any:
        """Get a specific localization by ID."""
        return self._request("GET", f"appStoreVersionLocalizations/{localization_id}")
    
    def create_app_store_version_localization(self, version_id: str, locale: str,
                                            description: str, keywords: str = None,
                                            promotional_text: str = None,
                                            whats_new: str = None,
                                            marketing_url: str = None,
                                            support_url: str = None) -> Any:
        """
        Create a new localization for an App Store version.
        
        Args:
            version_id: App Store version ID
            locale: Language locale code (e.g., 'en-US')
            description: App description (max 4000 chars)
            keywords: App keywords (max 100 chars)
            promotional_text: Promotional text (max 170 chars)
            whats_new: What's new text (max 4000 chars)
            marketing_url: Marketing URL for the localization
            support_url: Support URL for the localization
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
        if keywords is not None:
            attributes["keywords"] = keywords
        if promotional_text is not None:
            attributes["promotionalText"] = promotional_text
        if whats_new is not None:
            attributes["whatsNew"] = whats_new
        if marketing_url is not None:
            attributes["marketingUrl"] = marketing_url
        if support_url is not None:
            attributes["supportUrl"] = support_url
        
        return self._request("POST", "appStoreVersionLocalizations", data=data)
    
    def update_app_store_version_localization(self, localization_id: str,
                                            description: str = None,
                                            keywords: str = None,
                                            promotional_text: str = None,
                                            whats_new: str = None,
                                            marketing_url: str = None,
                                            support_url: str = None) -> Any:
        """
        Update an existing App Store version localization.
        
        Args:
            localization_id: Localization ID to update
            description: App description (max 4000 chars)
            keywords: App keywords (max 100 chars)
            promotional_text: Promotional text (max 170 chars)
            whats_new: What's new text (max 4000 chars)
            marketing_url: Marketing URL for the localization
            support_url: Support URL for the localization
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

            if marketing_url is not None and marketing_url != current_attrs.get("marketingUrl"):
                attributes["marketingUrl"] = marketing_url

            if support_url is not None and support_url != current_attrs.get("supportUrl"):
                attributes["supportUrl"] = support_url
            
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
            if marketing_url is not None:
                attributes["marketingUrl"] = marketing_url
            if support_url is not None:
                attributes["supportUrl"] = support_url
            
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
        try:
            current = self.get_app_info_localization(localization_id)
            current_attrs = current.get("data", {}).get("attributes", {})
            
            attributes = {}
            
            if name is not None and name != current_attrs.get("name"):
                if len(name) > 30:
                    name = name[:30]
                attributes["name"] = name
            
            if subtitle is not None and subtitle != current_attrs.get("subtitle"):
                if len(subtitle) > 30:
                    subtitle = subtitle[:30]
                attributes["subtitle"] = subtitle
            
            if attributes:
                data = {
                    "data": {
                        "type": "appInfoLocalizations",
                        "id": localization_id,
                        "attributes": attributes
                    }
                }
                return self._request("PATCH", f"appInfoLocalizations/{localization_id}", data=data)
            else:
                return current
                
        except Exception as e:
            data = {
                "data": {
                    "type": "appInfoLocalizations",
                    "id": localization_id,
                    "attributes": {}
                }
            }
            
            attributes = data["data"]["attributes"]
            if name is not None:
                if len(name) > 30:
                    name = name[:30]
                attributes["name"] = name
            if subtitle is not None:
                if len(subtitle) > 30:
                    subtitle = subtitle[:30]
                attributes["subtitle"] = subtitle
            
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

    # ----------------------
    # In-App Purchase helpers
    # ----------------------

    def get_in_app_purchases(self, app_id: str, limit: int = 200) -> Any:
        """List in-app purchases for an app using the app relationship endpoint."""
        params = {"limit": max(1, min(limit, 200))}
        return self._request("GET", f"v1/apps/{app_id}/inAppPurchasesV2", params=params)

    def get_in_app_purchase_localizations(self, iap_id: str) -> Any:
        """Get localizations for a specific in-app purchase (v2 path)."""
        return self._request("GET", f"v2/inAppPurchases/{iap_id}/inAppPurchaseLocalizations")

    def get_in_app_purchase_localization(self, localization_id: str) -> Any:
        """Get a single in-app purchase localization."""
        return self._request("GET", f"inAppPurchaseLocalizations/{localization_id}")

    def create_in_app_purchase_localization(self, iap_id: str, locale: str,
                                           name: str,
                                           description: Optional[str] = None) -> Any:
        """Create a localization for an in-app purchase (name + description) via v1 endpoint with v2 relationship."""
        name_limit = get_field_limit("iap_name") or 30
        desc_limit = get_field_limit("iap_description") or 45
        safe_name = (name or "")[:name_limit]
        safe_desc = (description or "")[:desc_limit] if description else None
        data = {
            "data": {
                "type": "inAppPurchaseLocalizations",
                "attributes": {
                    "locale": locale,
                    "name": safe_name,
                },
                "relationships": {
                    "inAppPurchaseV2": {
                        "data": {
                            "type": "inAppPurchases",
                            "id": iap_id,
                        }
                    }
                }
            }
        }
        if safe_desc is not None:
            data["data"]["attributes"]["description"] = safe_desc
        try:
            return self._request("POST", "v1/inAppPurchaseLocalizations", data=data)
        except requests.exceptions.HTTPError as e:
            status = getattr(e.response, "status_code", None)
            if status == 409:
                try:
                    locs = self.get_in_app_purchase_localizations(iap_id)
                    loc_map = {
                        l.get("attributes", {}).get("locale"): l.get("id")
                        for l in locs.get("data", [])
                        if l.get("id")
                    }
                    loc_id = loc_map.get(locale)
                    if loc_id:
                        return self.update_in_app_purchase_localization(loc_id, name, description)
                except Exception:
                    pass
            raise

    # ----------------------
    # Subscriptions
    # ----------------------

    def get_subscription_groups(self, app_id: str, limit: int = 200) -> Any:
        params = {"limit": max(1, min(limit, 200))}
        return self._request("GET", f"v1/apps/{app_id}/subscriptionGroups", params=params)

    def get_subscriptions_for_group(self, group_id: str, limit: int = 200) -> Any:
        params = {"limit": max(1, min(limit, 200))}
        return self._request("GET", f"v1/subscriptionGroups/{group_id}/subscriptions", params=params)

    def get_subscription_localizations(self, subscription_id: str) -> Any:
        return self._request("GET", f"v1/subscriptions/{subscription_id}/subscriptionLocalizations")

    def create_subscription_localization(self, subscription_id: str, locale: str,
                                        name: str,
                                        description: Optional[str] = None) -> Any:
        data = {
            "data": {
                "type": "subscriptionLocalizations",
                "attributes": {
                    "locale": locale,
                    "name": name,
                },
                "relationships": {
                    "subscription": {
                        "data": {
                            "type": "subscriptions",
                            "id": subscription_id,
                        }
                    }
                }
            }
        }
        if description is not None:
            data["data"]["attributes"]["description"] = description
        try:
            return self._request("POST", "v1/subscriptionLocalizations", data=data, max_retries=0)
        except requests.exceptions.HTTPError as e:
            status = getattr(e.response, "status_code", None)
            if status == 409:
                try:
                    locs = self.get_subscription_localizations(subscription_id)
                    loc_map = {
                        l.get("attributes", {}).get("locale"): l.get("id")
                        for l in locs.get("data", []) if l.get("id")
                    }
                    loc_id = loc_map.get(locale)
                    if loc_id:
                        return self.update_subscription_localization(loc_id, name, description)
                except Exception:
                    pass
                # If we reach here and handled conflict, return current localizations
                return loc_map if 'loc_map' in locals() else None
            raise

    def update_subscription_localization(self, localization_id: str,
                                         name: Optional[str] = None,
                                         description: Optional[str] = None) -> Any:
        attrs: Dict[str, Any] = {}
        if name is not None:
            attrs["name"] = name
        if description is not None:
            attrs["description"] = description
        if not attrs:
            return self._request("GET", f"v1/subscriptionLocalizations/{localization_id}")
        data = {
            "data": {
                "type": "subscriptionLocalizations",
                "id": localization_id,
                "attributes": attrs,
            }
        }
        return self._request("PATCH", f"v1/subscriptionLocalizations/{localization_id}", data=data, max_retries=0)

    # Subscription Group Localizations
    def get_subscription_group_localizations(self, group_id: str) -> Any:
        return self._request("GET", f"v1/subscriptionGroups/{group_id}/subscriptionGroupLocalizations")

    def create_subscription_group_localization(self, group_id: str, locale: str,
                                               name: str,
                                               custom_app_name: Optional[str] = None) -> Any:
        name_limit = get_field_limit("subscription_group_name") or len(name or "")
        custom_limit = get_field_limit("subscription_group_custom_app_name") or len(custom_app_name or "")
        data = {
            "data": {
                "type": "subscriptionGroupLocalizations",
                "attributes": {
                    "locale": locale,
                    "name": (name or "")[:name_limit],
                },
                "relationships": {
                    "subscriptionGroup": {
                        "data": {
                            "type": "subscriptionGroups",
                            "id": group_id,
                        }
                    }
                }
            }
        }
        if custom_app_name is not None:
            data["data"]["attributes"]["customAppName"] = (custom_app_name or "")[:custom_limit]
        try:
            return self._request("POST", "v1/subscriptionGroupLocalizations", data=data, max_retries=0)
        except requests.exceptions.HTTPError as e:
            status = getattr(e.response, "status_code", None)
            if status == 409:
                try:
                    locs = self.get_subscription_group_localizations(group_id)
                    loc_map = {
                        l.get("attributes", {}).get("locale"): l.get("id")
                        for l in locs.get("data", []) if l.get("id")
                    }
                    loc_id = loc_map.get(locale)
                    if loc_id:
                        return self.update_subscription_group_localization(loc_id, name, custom_app_name)
                except Exception:
                    pass
            raise

    def update_subscription_group_localization(self, localization_id: str,
                                                name: Optional[str] = None,
                                                custom_app_name: Optional[str] = None) -> Any:
        attrs: Dict[str, Any] = {}
        if name is not None:
            limit = get_field_limit("subscription_group_name") or len(name)
            attrs["name"] = name[:limit]
        if custom_app_name is not None:
            limit = get_field_limit("subscription_group_custom_app_name") or len(custom_app_name)
            attrs["customAppName"] = custom_app_name[:limit]
        if not attrs:
            return self._request("GET", f"v1/subscriptionGroupLocalizations/{localization_id}")
        data = {
            "data": {
                "type": "subscriptionGroupLocalizations",
                "id": localization_id,
                "attributes": attrs,
            }
        }
        return self._request("PATCH", f"v1/subscriptionGroupLocalizations/{localization_id}", data=data, max_retries=0)

    def update_in_app_purchase_localization(self, localization_id: str,
                                           name: Optional[str] = None,
                                           description: Optional[str] = None) -> Any:
        """Update an existing in-app purchase localization."""
        name_limit = get_field_limit("iap_name") or 30
        desc_limit = get_field_limit("iap_description") or 45
        attrs: Dict[str, Any] = {}
        if name is not None:
            attrs["name"] = name[:name_limit]
        if description is not None:
            attrs["description"] = description[:desc_limit]
        if not attrs:
            return self.get_in_app_purchase_localization(localization_id)
        data = {
            "data": {
                "type": "inAppPurchaseLocalizations",
                "id": localization_id,
                "attributes": attrs,
            }
        }
        return self._request("PATCH", f"inAppPurchaseLocalizations/{localization_id}", data=data)

    # ----------------------
    # In-App Events (App Events)
    # ----------------------

    def get_app_events(self, app_id: str, limit: int = 200) -> Any:
        """List in-app events (appEvents) for an app."""
        params = {"limit": max(1, min(limit, 200))}
        return self._request("GET", f"v1/apps/{app_id}/appEvents", params=params)

    def get_app_event_localizations(self, app_event_id: str, limit: int = 200) -> Any:
        """Get localizations for a specific in-app event (appEvents).

        Note: Some App Store Connect responses may omit attributes unless fields are requested.
        We explicitly request locale + translatable fields so workflows can reliably detect existing locales.
        """
        params = {
            "limit": max(1, min(limit, 200)),
            "fields[appEventLocalizations]": "locale,name,shortDescription,longDescription",
        }
        return self._request("GET", f"v1/appEvents/{app_event_id}/localizations", params=params)

    def get_app_event(self, app_event_id: str, include_localizations: bool = False) -> Any:
        """Get a single app event, optionally including localizations."""
        params: Dict[str, Any] = {}
        if include_localizations:
            params["include"] = "localizations"
            params["limit[localizations]"] = 50
            params["fields[appEventLocalizations]"] = "locale,name,shortDescription,longDescription"
        return self._request("GET", f"v1/appEvents/{app_event_id}", params=params or None)

    def _get_app_event_localization_id_map(self, app_event_id: str) -> Dict[str, str]:
        """Best-effort map of locale -> appEventLocalization id for an event."""
        loc_map: Dict[str, str] = {}
        # Primary: /localizations endpoint
        try:
            locs = self.get_app_event_localizations(app_event_id)
            for l in (locs.get("data", []) if isinstance(locs, dict) else []):
                attrs = (l.get("attributes", {}) or {})
                locale = (attrs.get("locale") or "").strip()
                lid = l.get("id")
                if locale and lid:
                    loc_map[locale] = lid
        except Exception:
            pass
        if loc_map:
            return loc_map

        # Fallback: include localizations from appEvents/{id}
        try:
            resp = self.get_app_event(app_event_id, include_localizations=True)
            included = resp.get("included", []) if isinstance(resp, dict) else []
            for item in included:
                if item.get("type") != "appEventLocalizations":
                    continue
                attrs = (item.get("attributes", {}) or {})
                locale = (attrs.get("locale") or "").strip()
                lid = item.get("id")
                if locale and lid:
                    loc_map[locale] = lid
        except Exception:
            pass
        return loc_map

    def _app_event_localization_id_for_locale(self, loc_map: Dict[str, str], locale: str) -> str:
        """Return localization id for an exact locale, with safe fallback for root-only locales.

        Only allows root matching when the requested locale has no region/script
        (e.g., "fi" can match "fi-FI"). Never maps "en-AU" to "en-US".
        """
        if not locale:
            return ""
        loc_id = loc_map.get(locale)
        if loc_id:
            return loc_id
        if "-" in locale:
            return ""
        root = locale.split("-")[0].lower()
        matches = [
            lid
            for code, lid in loc_map.items()
            if code and code.split("-")[0].lower() == root and lid
        ]
        return matches[0] if len(matches) == 1 else ""

    def get_app_event_localization(self, localization_id: str) -> Any:
        """Get a single app event localization."""
        return self._request("GET", f"v1/appEventLocalizations/{localization_id}")

    def create_app_event_localization(
        self,
        app_event_id: str,
        locale: str,
        name: Optional[str] = None,
        short_description: Optional[str] = None,
        long_description: Optional[str] = None,
    ) -> Any:
        """Create a localization for an in-app event (name + short/long descriptions)."""
        name_limit = get_field_limit("app_event_name") or (len(name) if name else 0)
        short_limit = get_field_limit("app_event_short_description") or (len(short_description) if short_description else 0)
        long_limit = get_field_limit("app_event_long_description") or (len(long_description) if long_description else 0)

        attrs: Dict[str, Any] = {"locale": locale}
        safe_name = (name or "").strip() if name is not None else ""
        if safe_name:
            attrs["name"] = safe_name[:name_limit]
        safe_short = (short_description or "").strip() if short_description is not None else ""
        if safe_short:
            attrs["shortDescription"] = safe_short[:short_limit]
        safe_long = (long_description or "").strip() if long_description is not None else ""
        # ASC rejects too-short longDescription with ENTITY_ERROR.ATTRIBUTE.INVALID (min length 2)
        if safe_long and len(safe_long) >= 2:
            attrs["longDescription"] = safe_long[:long_limit]

        data = {
            "data": {
                "type": "appEventLocalizations",
                "attributes": attrs,
                "relationships": {
                    "appEvent": {
                        "data": {
                            "type": "appEvents",
                            "id": app_event_id,
                        }
                    }
                },
            }
        }
        try:
            return self._request("POST", "v1/appEventLocalizations", data=data, max_retries=0)
        except requests.exceptions.HTTPError as e:
            status = getattr(e.response, "status_code", None)
            if status == 409:
                if str(getattr(__import__("os"), "environ", {}).get("TRANSLATER_DEBUG_APP_EVENTS", "")).strip().lower() in ("1", "true", "yes", "y", "on"):
                    try:
                        body = e.response.json()
                    except Exception:
                        body = getattr(e.response, "text", None)
                    print(f"[debug] appEventLocalizations create 409 locale={locale} event_id={app_event_id} body={body}")
                try:
                    loc_map = self._get_app_event_localization_id_map(app_event_id)
                    loc_id = self._app_event_localization_id_for_locale(loc_map, locale)
                    if loc_id:
                        return self.update_app_event_localization(
                            loc_id,
                            name=name,
                            short_description=short_description,
                            long_description=long_description,
                        )
                except Exception:
                    pass
            raise

    def update_app_event_localization(
        self,
        localization_id: str,
        name: Optional[str] = None,
        short_description: Optional[str] = None,
        long_description: Optional[str] = None,
    ) -> Any:
        """Update an existing app event localization."""
        attrs: Dict[str, Any] = {}
        if name is not None:
            safe = (name or "").strip()
            if safe:
                limit = get_field_limit("app_event_name") or len(safe)
                attrs["name"] = safe[:limit]
        if short_description is not None:
            safe = (short_description or "").strip()
            if safe:
                limit = get_field_limit("app_event_short_description") or len(safe)
                attrs["shortDescription"] = safe[:limit]
        if long_description is not None:
            safe = (long_description or "").strip()
            if safe and len(safe) >= 2:
                limit = get_field_limit("app_event_long_description") or len(safe)
                attrs["longDescription"] = safe[:limit]
        if not attrs:
            return self.get_app_event_localization(localization_id)
        data = {
            "data": {
                "type": "appEventLocalizations",
                "id": localization_id,
                "attributes": attrs,
            }
        }
        return self._request("PATCH", f"v1/appEventLocalizations/{localization_id}", data=data, max_retries=0)
    
