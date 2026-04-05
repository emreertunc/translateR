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
import re
import unicodedata

from utils import get_field_limit



# Symbols explicitly allowed in Apple app names even though they are Unicode 'Symbol' category
_ALLOWED_SYMBOL_CHARS = set('+-=<>|~^*%$#@&')
# Keep script joiners used by some languages (e.g. Persian, Indic scripts).
_ALLOWED_FORMAT_CHARS = {"\u200c", "\u200d"}


def _strip_control_chars(text: str) -> str:
    """Remove characters that Apple's API rejects from name/subtitle fields.
    Strips control characters and disallowed symbols while preserving
    language-critical combining marks and joiners.
    """
    if not text:
        return text
    result = []
    for char in text:
        if char in ('\n', '\r', '\t'):
            result.append(' ')  # Convert whitespace control chars to space
            continue
        cat = unicodedata.category(char)
        if cat.startswith(('L', 'N', 'P', 'Z', 'M')):
            result.append(char)
        elif cat == 'Cf' and char in _ALLOWED_FORMAT_CHARS:
            result.append(char)
        elif cat.startswith('S') and char in _ALLOWED_SYMBOL_CHARS:
            result.append(char)
        # Skip: other symbols (arrows, emoji, math), other control/format chars
    cleaned = re.sub(r'\s+', ' ', ''.join(result)).strip()
    return cleaned



class AppStoreConnectClient:
    """Client for interacting with App Store Connect API."""
    
    API_ROOT = "https://api.appstoreconnect.apple.com"
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
        if endpoint.startswith("http://") or endpoint.startswith("https://"):
            url = endpoint
        elif endpoint.startswith("v1/") or endpoint.startswith("v2/"):
            url = f"{self.API_ROOT}/{endpoint}"
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
                    print(f"⚠️  API conflict detected, retrying in {wait_time:.1f}s (attempt {attempt + 1}/{max_retries + 1})...")
                    time.sleep(wait_time)
                    continue
                else:
                    try:
                        error_body = response.json()
                        errors = error_body.get("errors", [])
                        if errors:
                            detail = errors[0].get("detail", "")
                            title = errors[0].get("title", "")
                            raise requests.exceptions.HTTPError(
                                f"{response.status_code} Client Error: {title} - {detail} for url: {response.url}",
                                response=response
                            )
                    except (ValueError, AttributeError):
                        pass
                    raise e
    
    def get_apps(self) -> Any:
        """Get list of apps."""
        return self._request("GET", "apps")

    def get_app(self, app_id: str) -> Any:
        """Get a single app by ID."""
        return self._request("GET", f"apps/{app_id}")
    
    def get_latest_app_store_version(self, app_id: str) -> Optional[str]:
        """Get the latest editable App Store version ID for an app.

        Prefers versions in an editable state (PREPARE_FOR_SUBMISSION first,
        then other editable states). Falls back to the first version if none
        are in an editable state.
        """
        EDITABLE_STATES = [
            "PREPARE_FOR_SUBMISSION",
            "DEVELOPER_REJECTED",
            "REJECTED",
            "METADATA_REJECTED",
            "WAITING_FOR_REVIEW",
        ]
        response = self._request("GET", f"apps/{app_id}/appStoreVersions")
        versions = response.get("data", [])
        if not versions:
            return None
        for preferred in EDITABLE_STATES:
            for version in versions:
                state = version.get("attributes", {}).get("appVersionState") or \
                        version.get("attributes", {}).get("appStoreState")
                if state == preferred:
                    return version["id"]
        return versions[0]["id"]
    
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
    
    def create_app_info_localization(
        self,
        app_info_id: str,
        locale: str,
        name: str = None,
        subtitle: str = None,
        privacy_policy_url: str = None,
        marketing_url: str = None,
        support_url: str = None,
    ) -> Any:
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
            attributes["name"] = _strip_control_chars(name)
        if subtitle:
            if len(subtitle) > 30:
                subtitle = subtitle[:30]
            attributes["subtitle"] = _strip_control_chars(subtitle)
        if privacy_policy_url:
            limit = get_field_limit("privacy_policy_url") or 255
            attributes["privacyPolicyUrl"] = privacy_policy_url[:limit]
        if marketing_url:
            limit = get_field_limit("marketing_url") or 255
            attributes["marketingUrl"] = marketing_url[:limit]
        if support_url:
            limit = get_field_limit("support_url") or 255
            attributes["supportUrl"] = support_url[:limit]
        
        return self._request("POST", "appInfoLocalizations", data=data)
    
    def update_app_info_localization(
        self,
        localization_id: str,
        name: str = None,
        subtitle: str = None,
        privacy_policy_url: str = None,
        marketing_url: str = None,
        support_url: str = None,
    ) -> Any:
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
            attributes["name"] = _strip_control_chars(name)
        
        if subtitle is not None and subtitle != current_attrs.get("subtitle"):
            if len(subtitle) > 30:
                subtitle = subtitle[:30]
            attributes["subtitle"] = _strip_control_chars(subtitle)

        if privacy_policy_url is not None and privacy_policy_url != current_attrs.get("privacyPolicyUrl"):
            limit = get_field_limit("privacy_policy_url") or len(privacy_policy_url)
            attributes["privacyPolicyUrl"] = privacy_policy_url[:limit]

        if marketing_url is not None and marketing_url != current_attrs.get("marketingUrl"):
            limit = get_field_limit("marketing_url") or len(marketing_url)
            attributes["marketingUrl"] = marketing_url[:limit]

        if support_url is not None and support_url != current_attrs.get("supportUrl"):
            limit = get_field_limit("support_url") or len(support_url)
            attributes["supportUrl"] = support_url[:limit]
        
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
    
    def find_primary_app_info_id(self, app_id: str, editable_only: bool = True) -> Optional[str]:
        """
        Find primary app info ID.

        When editable_only is True (default), returns an editable appInfo ID
        or None if app has no editable appInfo.
        When editable_only is False, falls back using a deterministic
        read-oriented state priority instead of API response order.
        """
        EDITABLE_STATES = [
            "PREPARE_FOR_SUBMISSION",
            "DEVELOPER_REJECTED",
            "REJECTED",
            "METADATA_REJECTED",
            "WAITING_FOR_REVIEW",
        ]
        READ_FALLBACK_STATES = [
            "READY_FOR_SALE",
            "PENDING_DEVELOPER_RELEASE",
            "PROCESSING_FOR_DISTRIBUTION",
            "IN_REVIEW",
            "PENDING_APPLE_RELEASE",
            "DEVELOPER_REMOVED_FROM_SALE",
        ]
        try:
            app_infos = self.get_app_infos(app_id)
            infos = app_infos.get("data", [])

            if not infos:
                return None

            normalized_infos = []
            for info in infos:
                info_id = info.get("id")
                if not info_id:
                    continue
                attrs = info.get("attributes", {})
                state = attrs.get("appStoreState") or attrs.get("appVersionState") or ""
                normalized_infos.append({"id": str(info_id), "state": str(state)})

            if not normalized_infos:
                return None

            for preferred in EDITABLE_STATES:
                for info in normalized_infos:
                    if info["state"] == preferred:
                        return info["id"]

            if editable_only:
                return None

            for preferred in READ_FALLBACK_STATES:
                matched_ids = sorted(
                    info["id"] for info in normalized_infos if info["state"] == preferred
                )
                if matched_ids:
                    return matched_ids[0]

            return sorted(info["id"] for info in normalized_infos)[0]

        except Exception:
            return None

    # ----------------------
    # In-App Purchase helpers
    # ----------------------

    def get_in_app_purchases(self, app_id: str, limit: int = 200) -> Any:
        """List in-app purchases for an app."""
        params = {"limit": max(1, min(limit, 200))}
        return self._request("GET", f"apps/{app_id}/inAppPurchasesV2", params=params)

    def get_in_app_purchase_localizations(self, iap_id: str) -> Any:
        """Get localizations for a specific in-app purchase."""
        return self._request("GET", f"v2/inAppPurchases/{iap_id}/inAppPurchaseLocalizations")

    def get_in_app_purchase_localization(self, localization_id: str) -> Any:
        """Get a single in-app purchase localization."""
        return self._request("GET", f"inAppPurchaseLocalizations/{localization_id}")

    def create_in_app_purchase_localization(
        self,
        iap_id: str,
        locale: str,
        name: str,
        description: Optional[str] = None,
    ) -> Any:
        """Create a localization for an in-app purchase."""
        name_limit = get_field_limit("iap_name") or 30
        desc_limit = get_field_limit("iap_description") or 45
        safe_name = (name or "")[:name_limit]
        safe_description = (description or "")[:desc_limit] if description else None

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
        if safe_description is not None:
            data["data"]["attributes"]["description"] = safe_description

        try:
            return self._request("POST", "inAppPurchaseLocalizations", data=data)
        except requests.exceptions.HTTPError as error:
            status_code = getattr(error.response, "status_code", None)
            if status_code == 409:
                try:
                    localizations = self.get_in_app_purchase_localizations(iap_id)
                    locale_map = {
                        loc.get("attributes", {}).get("locale"): loc.get("id")
                        for loc in localizations.get("data", [])
                        if loc.get("id")
                    }
                    localization_id = locale_map.get(locale)
                    if localization_id:
                        return self.update_in_app_purchase_localization(
                            localization_id,
                            name,
                            description,
                        )
                except Exception:
                    pass
            raise

    def update_in_app_purchase_localization(
        self,
        localization_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Any:
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
    # Subscription helpers
    # ----------------------

    def get_subscription_groups(self, app_id: str, limit: int = 200) -> Any:
        """List subscription groups for an app."""
        params = {"limit": max(1, min(limit, 200))}
        return self._request("GET", f"apps/{app_id}/subscriptionGroups", params=params)

    def get_subscriptions_for_group(self, group_id: str, limit: int = 200) -> Any:
        """List subscriptions for a subscription group."""
        params = {"limit": max(1, min(limit, 200))}
        return self._request("GET", f"subscriptionGroups/{group_id}/subscriptions", params=params)

    def get_subscription_localizations(self, subscription_id: str) -> Any:
        """Get localizations for a specific subscription."""
        return self._request("GET", f"subscriptions/{subscription_id}/subscriptionLocalizations")

    def create_subscription_localization(
        self,
        subscription_id: str,
        locale: str,
        name: str,
        description: Optional[str] = None,
    ) -> Any:
        """Create a subscription localization."""
        name_limit = get_field_limit("subscription_name") or 60
        desc_limit = get_field_limit("subscription_description") or 200
        safe_name = (name or "")[:name_limit]
        safe_description = (description or "")[:desc_limit] if description else None

        data = {
            "data": {
                "type": "subscriptionLocalizations",
                "attributes": {
                    "locale": locale,
                    "name": safe_name,
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
        if safe_description is not None:
            data["data"]["attributes"]["description"] = safe_description

        try:
            return self._request("POST", "subscriptionLocalizations", data=data, max_retries=0)
        except requests.exceptions.HTTPError as error:
            status_code = getattr(error.response, "status_code", None)
            if status_code == 409:
                try:
                    localizations = self.get_subscription_localizations(subscription_id)
                    locale_map = {
                        loc.get("attributes", {}).get("locale"): loc.get("id")
                        for loc in localizations.get("data", [])
                        if loc.get("id")
                    }
                    localization_id = locale_map.get(locale)
                    if localization_id:
                        return self.update_subscription_localization(
                            localization_id,
                            safe_name,
                            safe_description,
                        )
                except Exception:
                    pass
            raise

    def update_subscription_localization(
        self,
        localization_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Any:
        """Update a subscription localization."""
        attrs: Dict[str, Any] = {}
        if name is not None:
            limit = get_field_limit("subscription_name") or len(name)
            attrs["name"] = name[:limit]
        if description is not None:
            limit = get_field_limit("subscription_description") or len(description)
            attrs["description"] = description[:limit]

        if not attrs:
            return self._request("GET", f"subscriptionLocalizations/{localization_id}")

        data = {
            "data": {
                "type": "subscriptionLocalizations",
                "id": localization_id,
                "attributes": attrs,
            }
        }
        return self._request("PATCH", f"subscriptionLocalizations/{localization_id}", data=data, max_retries=0)

    def get_subscription_group_localizations(self, group_id: str) -> Any:
        """Get localizations for a subscription group."""
        return self._request("GET", f"subscriptionGroups/{group_id}/subscriptionGroupLocalizations")

    def create_subscription_group_localization(
        self,
        group_id: str,
        locale: str,
        name: str,
        custom_app_name: Optional[str] = None,
    ) -> Any:
        """Create a subscription group localization."""
        name_limit = get_field_limit("subscription_group_name") or 60
        custom_limit = get_field_limit("subscription_group_custom_app_name") or 30
        safe_name = (name or "")[:name_limit]
        safe_custom = (custom_app_name or "")[:custom_limit] if custom_app_name else None

        data = {
            "data": {
                "type": "subscriptionGroupLocalizations",
                "attributes": {
                    "locale": locale,
                    "name": safe_name,
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
        if safe_custom is not None:
            data["data"]["attributes"]["customAppName"] = safe_custom

        try:
            return self._request("POST", "subscriptionGroupLocalizations", data=data, max_retries=0)
        except requests.exceptions.HTTPError as error:
            status_code = getattr(error.response, "status_code", None)
            if status_code == 409:
                try:
                    localizations = self.get_subscription_group_localizations(group_id)
                    locale_map = {
                        loc.get("attributes", {}).get("locale"): loc.get("id")
                        for loc in localizations.get("data", [])
                        if loc.get("id")
                    }
                    localization_id = locale_map.get(locale)
                    if localization_id:
                        return self.update_subscription_group_localization(
                            localization_id,
                            safe_name,
                            safe_custom,
                        )
                except Exception:
                    pass
            raise

    def update_subscription_group_localization(
        self,
        localization_id: str,
        name: Optional[str] = None,
        custom_app_name: Optional[str] = None,
    ) -> Any:
        """Update a subscription group localization."""
        attrs: Dict[str, Any] = {}
        if name is not None:
            limit = get_field_limit("subscription_group_name") or len(name)
            attrs["name"] = name[:limit]
        if custom_app_name is not None:
            limit = get_field_limit("subscription_group_custom_app_name") or len(custom_app_name)
            attrs["customAppName"] = custom_app_name[:limit]

        if not attrs:
            return self._request("GET", f"subscriptionGroupLocalizations/{localization_id}")

        data = {
            "data": {
                "type": "subscriptionGroupLocalizations",
                "id": localization_id,
                "attributes": attrs,
            }
        }
        return self._request("PATCH", f"subscriptionGroupLocalizations/{localization_id}", data=data, max_retries=0)

    # ----------------------
    # In-App Events helpers
    # ----------------------

    def get_app_events(self, app_id: str, limit: int = 200) -> Any:
        """List in-app events for an app."""
        params = {"limit": max(1, min(limit, 200))}
        return self._request("GET", f"apps/{app_id}/appEvents", params=params)

    def get_app_event_localizations(self, app_event_id: str, limit: int = 200) -> Any:
        """Get localizations for an in-app event."""
        params = {
            "limit": max(1, min(limit, 200)),
            "fields[appEventLocalizations]": "locale,name,shortDescription,longDescription",
        }
        return self._request("GET", f"appEvents/{app_event_id}/localizations", params=params)

    def get_app_event_localization(self, localization_id: str) -> Any:
        """Get a single app event localization."""
        return self._request("GET", f"appEventLocalizations/{localization_id}")

    def create_app_event_localization(
        self,
        app_event_id: str,
        locale: str,
        name: Optional[str] = None,
        short_description: Optional[str] = None,
        long_description: Optional[str] = None,
    ) -> Any:
        """Create an app event localization."""
        name_limit = get_field_limit("app_event_name") or 30
        short_limit = get_field_limit("app_event_short_description") or 50
        long_limit = get_field_limit("app_event_long_description") or 120

        attrs: Dict[str, Any] = {"locale": locale}
        safe_name = (name or "").strip()
        safe_short = (short_description or "").strip()
        safe_long = (long_description or "").strip()
        if safe_name:
            attrs["name"] = safe_name[:name_limit]
        if safe_short:
            attrs["shortDescription"] = safe_short[:short_limit]
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
            return self._request("POST", "appEventLocalizations", data=data, max_retries=0)
        except requests.exceptions.HTTPError as error:
            status_code = getattr(error.response, "status_code", None)
            if status_code == 409:
                try:
                    localizations = self.get_app_event_localizations(app_event_id)
                    locale_map = {
                        loc.get("attributes", {}).get("locale"): loc.get("id")
                        for loc in localizations.get("data", [])
                        if loc.get("id")
                    }
                    localization_id = locale_map.get(locale)
                    if localization_id:
                        return self.update_app_event_localization(
                            localization_id=localization_id,
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
        """Update an app event localization."""
        attrs: Dict[str, Any] = {}
        if name is not None:
            safe_name = (name or "").strip()
            if safe_name:
                limit = get_field_limit("app_event_name") or len(safe_name)
                attrs["name"] = safe_name[:limit]
        if short_description is not None:
            safe_short = (short_description or "").strip()
            if safe_short:
                limit = get_field_limit("app_event_short_description") or len(safe_short)
                attrs["shortDescription"] = safe_short[:limit]
        if long_description is not None:
            safe_long = (long_description or "").strip()
            if safe_long and len(safe_long) >= 2:
                limit = get_field_limit("app_event_long_description") or len(safe_long)
                attrs["longDescription"] = safe_long[:limit]

        if not attrs:
            return self.get_app_event_localization(localization_id)

        data = {
            "data": {
                "type": "appEventLocalizations",
                "id": localization_id,
                "attributes": attrs,
            }
        }
        return self._request("PATCH", f"appEventLocalizations/{localization_id}", data=data, max_retries=0)

    # ----------------------
    # Game Center helpers
    # ----------------------

    def get_game_center_detail(self, app_id: str) -> Any:
        """Get Game Center detail for an app."""
        return self._request("GET", f"v1/apps/{app_id}/gameCenterDetail")

    def get_game_center_group(self, detail_id: str) -> Any:
        """Get Game Center group for a Game Center detail."""
        return self._request("GET", f"v1/gameCenterDetails/{detail_id}/gameCenterGroup")

    def get_game_center_achievements(self, detail_id: str, limit: int = 200) -> Any:
        """List Game Center achievements for a Game Center detail."""
        params = {"limit": max(1, min(limit, 200))}
        return self._request("GET", f"v1/gameCenterDetails/{detail_id}/gameCenterAchievements", params=params)

    def get_game_center_leaderboards(self, detail_id: str, limit: int = 200) -> Any:
        """List Game Center leaderboards for a Game Center detail."""
        params = {"limit": max(1, min(limit, 200))}
        return self._request("GET", f"v1/gameCenterDetails/{detail_id}/gameCenterLeaderboards", params=params)

    def get_game_center_activities(self, detail_id: str, limit: int = 200) -> Any:
        """List Game Center activities for a Game Center detail."""
        params = {"limit": max(1, min(limit, 200))}
        return self._request("GET", f"v1/gameCenterDetails/{detail_id}/gameCenterActivities", params=params)

    def get_game_center_challenges(self, detail_id: str, limit: int = 200) -> Any:
        """List Game Center challenges for a Game Center detail."""
        params = {"limit": max(1, min(limit, 200))}
        return self._request("GET", f"v1/gameCenterDetails/{detail_id}/gameCenterChallenges", params=params)

    def get_game_center_group_achievements(self, group_id: str, limit: int = 200) -> Any:
        """List Game Center achievements for a Game Center group."""
        params = {"limit": max(1, min(limit, 200))}
        return self._request("GET", f"v1/gameCenterGroups/{group_id}/gameCenterAchievements", params=params)

    def get_game_center_group_leaderboards(self, group_id: str, limit: int = 200) -> Any:
        """List Game Center leaderboards for a Game Center group."""
        params = {"limit": max(1, min(limit, 200))}
        return self._request("GET", f"v1/gameCenterGroups/{group_id}/gameCenterLeaderboards", params=params)

    def get_game_center_group_activities(self, group_id: str, limit: int = 200) -> Any:
        """List Game Center activities for a Game Center group."""
        params = {"limit": max(1, min(limit, 200))}
        return self._request("GET", f"v1/gameCenterGroups/{group_id}/gameCenterActivities", params=params)

    def get_game_center_group_challenges(self, group_id: str, limit: int = 200) -> Any:
        """List Game Center challenges for a Game Center group."""
        params = {"limit": max(1, min(limit, 200))}
        return self._request("GET", f"v1/gameCenterGroups/{group_id}/gameCenterChallenges", params=params)

    def get_game_center_achievement_localizations(self, achievement_id: str, limit: int = 200) -> Any:
        """Get localizations for a specific Game Center achievement."""
        params = {"limit": max(1, min(limit, 200))}
        return self._request("GET", f"v1/gameCenterAchievements/{achievement_id}/localizations", params=params)

    def get_game_center_leaderboard_localizations(self, leaderboard_id: str, limit: int = 200) -> Any:
        """Get localizations for a specific Game Center leaderboard."""
        params = {"limit": max(1, min(limit, 200))}
        return self._request("GET", f"v1/gameCenterLeaderboards/{leaderboard_id}/localizations", params=params)

    def get_game_center_activity_versions(self, activity_id: str, limit: int = 200) -> Any:
        """List versions for a Game Center activity."""
        params = {"limit": max(1, min(limit, 200))}
        return self._request("GET", f"v1/gameCenterActivities/{activity_id}/versions", params=params)

    def get_game_center_challenge_versions(self, challenge_id: str, limit: int = 200) -> Any:
        """List versions for a Game Center challenge."""
        params = {"limit": max(1, min(limit, 200))}
        return self._request("GET", f"v1/gameCenterChallenges/{challenge_id}/versions", params=params)

    def get_game_center_activity_version_localizations(self, version_id: str, limit: int = 200) -> Any:
        """Get localizations for a Game Center activity version."""
        params = {"limit": max(1, min(limit, 200))}
        return self._request("GET", f"v1/gameCenterActivityVersions/{version_id}/localizations", params=params)

    def get_game_center_challenge_version_localizations(self, version_id: str, limit: int = 200) -> Any:
        """Get localizations for a Game Center challenge version."""
        params = {"limit": max(1, min(limit, 200))}
        return self._request("GET", f"v1/gameCenterChallengeVersions/{version_id}/localizations", params=params)

    def create_game_center_achievement_localization(
        self,
        achievement_id: str,
        locale: str,
        name: str,
        before_earned_description: str,
        after_earned_description: str,
    ) -> Any:
        """Create a localization for a Game Center achievement."""
        name_limit = get_field_limit("game_center_achievement_name") or 30
        before_limit = get_field_limit("game_center_achievement_before_description") or 200
        after_limit = get_field_limit("game_center_achievement_after_description") or 200

        data = {
            "data": {
                "type": "gameCenterAchievementLocalizations",
                "attributes": {
                    "locale": locale,
                    "name": (name or "").strip()[:name_limit],
                    "beforeEarnedDescription": (before_earned_description or "").strip()[:before_limit],
                    "afterEarnedDescription": (after_earned_description or "").strip()[:after_limit],
                },
                "relationships": {
                    "gameCenterAchievement": {
                        "data": {
                            "type": "gameCenterAchievements",
                            "id": achievement_id,
                        }
                    }
                },
            }
        }
        return self._request("POST", "v1/gameCenterAchievementLocalizations", data=data, max_retries=0)

    def update_game_center_achievement_localization(
        self,
        localization_id: str,
        name: Optional[str] = None,
        before_earned_description: Optional[str] = None,
        after_earned_description: Optional[str] = None,
    ) -> Any:
        """Update an existing Game Center achievement localization."""
        attrs: Dict[str, Any] = {}
        if name is not None:
            limit = get_field_limit("game_center_achievement_name") or len(name)
            attrs["name"] = (name or "").strip()[:limit]
        if before_earned_description is not None:
            limit = get_field_limit("game_center_achievement_before_description") or len(before_earned_description)
            attrs["beforeEarnedDescription"] = (before_earned_description or "").strip()[:limit]
        if after_earned_description is not None:
            limit = get_field_limit("game_center_achievement_after_description") or len(after_earned_description)
            attrs["afterEarnedDescription"] = (after_earned_description or "").strip()[:limit]

        if not attrs:
            return self._request("GET", f"v1/gameCenterAchievementLocalizations/{localization_id}")

        data = {
            "data": {
                "type": "gameCenterAchievementLocalizations",
                "id": localization_id,
                "attributes": attrs,
            }
        }
        return self._request("PATCH", f"v1/gameCenterAchievementLocalizations/{localization_id}", data=data, max_retries=0)

    def create_game_center_leaderboard_localization(
        self,
        leaderboard_id: str,
        locale: str,
        name: str,
        description: Optional[str] = None,
        formatter_suffix: Optional[str] = None,
        formatter_suffix_singular: Optional[str] = None,
        formatter_override: Optional[str] = None,
    ) -> Any:
        """Create a localization for a Game Center leaderboard."""
        name_limit = get_field_limit("game_center_leaderboard_name") or 30
        desc_limit = get_field_limit("game_center_leaderboard_description") or 200

        attrs: Dict[str, Any] = {
            "locale": locale,
            "name": (name or "").strip()[:name_limit],
        }
        if description is not None:
            attrs["description"] = (description or "").strip()[:desc_limit]
        if formatter_suffix is not None:
            attrs["formatterSuffix"] = formatter_suffix
        if formatter_suffix_singular is not None:
            attrs["formatterSuffixSingular"] = formatter_suffix_singular
        if formatter_override is not None:
            attrs["formatterOverride"] = formatter_override

        data = {
            "data": {
                "type": "gameCenterLeaderboardLocalizations",
                "attributes": attrs,
                "relationships": {
                    "gameCenterLeaderboard": {
                        "data": {
                            "type": "gameCenterLeaderboards",
                            "id": leaderboard_id,
                        }
                    }
                },
            }
        }
        return self._request("POST", "v1/gameCenterLeaderboardLocalizations", data=data, max_retries=0)

    def update_game_center_leaderboard_localization(
        self,
        localization_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        formatter_suffix: Optional[str] = None,
        formatter_suffix_singular: Optional[str] = None,
        formatter_override: Optional[str] = None,
    ) -> Any:
        """Update an existing Game Center leaderboard localization."""
        attrs: Dict[str, Any] = {}
        if name is not None:
            limit = get_field_limit("game_center_leaderboard_name") or len(name)
            attrs["name"] = (name or "").strip()[:limit]
        if description is not None:
            limit = get_field_limit("game_center_leaderboard_description") or len(description)
            attrs["description"] = (description or "").strip()[:limit]
        if formatter_suffix is not None:
            attrs["formatterSuffix"] = formatter_suffix
        if formatter_suffix_singular is not None:
            attrs["formatterSuffixSingular"] = formatter_suffix_singular
        if formatter_override is not None:
            attrs["formatterOverride"] = formatter_override

        if not attrs:
            return self._request("GET", f"v1/gameCenterLeaderboardLocalizations/{localization_id}")

        data = {
            "data": {
                "type": "gameCenterLeaderboardLocalizations",
                "id": localization_id,
                "attributes": attrs,
            }
        }
        return self._request("PATCH", f"v1/gameCenterLeaderboardLocalizations/{localization_id}", data=data, max_retries=0)

    def create_game_center_activity_localization(
        self,
        version_id: str,
        locale: str,
        name: str,
        description: Optional[str] = None,
    ) -> Any:
        """Create a localization for a Game Center activity version."""
        name_limit = get_field_limit("game_center_activity_name") or 30
        desc_limit = get_field_limit("game_center_activity_description") or 200

        attrs: Dict[str, Any] = {
            "locale": locale,
            "name": (name or "").strip()[:name_limit],
        }
        if description is not None:
            attrs["description"] = (description or "").strip()[:desc_limit]

        data = {
            "data": {
                "type": "gameCenterActivityLocalizations",
                "attributes": attrs,
                "relationships": {
                    "version": {
                        "data": {
                            "type": "gameCenterActivityVersions",
                            "id": version_id,
                        }
                    }
                },
            }
        }
        return self._request("POST", "v1/gameCenterActivityLocalizations", data=data, max_retries=0)

    def update_game_center_activity_localization(
        self,
        localization_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Any:
        """Update an existing Game Center activity localization."""
        attrs: Dict[str, Any] = {}
        if name is not None:
            limit = get_field_limit("game_center_activity_name") or len(name)
            attrs["name"] = (name or "").strip()[:limit]
        if description is not None:
            limit = get_field_limit("game_center_activity_description") or len(description)
            attrs["description"] = (description or "").strip()[:limit]

        if not attrs:
            return self._request("GET", f"v1/gameCenterActivityLocalizations/{localization_id}")

        data = {
            "data": {
                "type": "gameCenterActivityLocalizations",
                "id": localization_id,
                "attributes": attrs,
            }
        }
        return self._request("PATCH", f"v1/gameCenterActivityLocalizations/{localization_id}", data=data, max_retries=0)

    def create_game_center_challenge_localization(
        self,
        version_id: str,
        locale: str,
        name: str,
        description: Optional[str] = None,
    ) -> Any:
        """Create a localization for a Game Center challenge version."""
        name_limit = get_field_limit("game_center_challenge_name") or 30
        desc_limit = get_field_limit("game_center_challenge_description") or 200

        attrs: Dict[str, Any] = {
            "locale": locale,
            "name": (name or "").strip()[:name_limit],
        }
        if description is not None:
            attrs["description"] = (description or "").strip()[:desc_limit]

        data = {
            "data": {
                "type": "gameCenterChallengeLocalizations",
                "attributes": attrs,
                "relationships": {
                    "version": {
                        "data": {
                            "type": "gameCenterChallengeVersions",
                            "id": version_id,
                        }
                    }
                },
            }
        }
        return self._request("POST", "v1/gameCenterChallengeLocalizations", data=data, max_retries=0)

    def update_game_center_challenge_localization(
        self,
        localization_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Any:
        """Update an existing Game Center challenge localization."""
        attrs: Dict[str, Any] = {}
        if name is not None:
            limit = get_field_limit("game_center_challenge_name") or len(name)
            attrs["name"] = (name or "").strip()[:limit]
        if description is not None:
            limit = get_field_limit("game_center_challenge_description") or len(description)
            attrs["description"] = (description or "").strip()[:limit]

        if not attrs:
            return self._request("GET", f"v1/gameCenterChallengeLocalizations/{localization_id}")

        data = {
            "data": {
                "type": "gameCenterChallengeLocalizations",
                "id": localization_id,
                "attributes": attrs,
            }
        }
        return self._request("PATCH", f"v1/gameCenterChallengeLocalizations/{localization_id}", data=data, max_retries=0)
    
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
    
