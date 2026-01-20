# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

TranslateR is an AI-powered App Store Connect localization automation tool. It connects to Apple's App Store Connect API to fetch app metadata, translates content using AI providers (Anthropic Claude, OpenAI GPT, or Google Gemini), and uploads the translated localizations back to App Store Connect. The tool supports 38+ App Store locales and handles all metadata fields including descriptions, keywords, promotional text, what's new notes, in-app purchases, subscriptions, Game Center achievements/leaderboards, and app events.

## Development Commands

### Setup and Installation
```bash
# Create virtual environment (recommended)
python3 -m venv .venv && source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the tool (creates config/ on first run)
python3 main.py
```

### First Run Configuration
On first run, the tool prompts for:
- App Store Connect API credentials (Key ID, Issuer ID, .p8 file path)
- At least one AI provider API key (Anthropic/OpenAI/Google)

These are saved to `config/api_keys.json` (gitignored).

### Running the Tool
```bash
# Interactive CLI with 11 workflows
python3 main.py
```

### Testing
No automated tests are currently implemented. Test manually with non-production apps first. Use the "Export Localizations" workflow to back up before making changes.

## Architecture Overview

### Core Module Responsibilities

- **main.py**: CLI entrypoint, workflow orchestration, main menu loop. Initializes `TranslateRCLI` class which manages the session state (config, ASC client, AI providers, UI wrapper).

- **app_store_client.py**: Complete App Store Connect API wrapper. Handles JWT authentication, HTTP requests with retry logic for 409 conflicts, pagination, and all API endpoints (apps, versions, localizations, IAPs, subscriptions, Game Center, app events). Supports both v1 and v2 endpoints.

- **ai_providers.py**: Multi-provider AI translation system. Defines `AIProvider` abstract base class and concrete implementations: `AnthropicProvider`, `OpenAIProvider`, `GoogleGeminiProvider`. Each provider implements `translate()` method with character limit enforcement, keyword formatting, deterministic seeding, and prompt refinement support. Includes automatic retry logic for character limit violations.

- **config.py**: Configuration file management. `ConfigManager` class handles loading/saving `config/api_keys.json`, `config/providers.json`, `config/instructions.txt`. Supports environment variable overrides for AI keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`/`GEMINI_API_KEY`/`GOOGLE_GEMINI_API_KEY`). Syncs provider catalog with available models on startup.

- **ui.py**: Interactive UI abstraction layer. `UI` class provides TUI (InquirerPy) when available, falls back to stdin/stdout prompts. Methods: `select()`, `checkbox()`, `multiline()`, `prompt_app_id()`. Handles editor integration via `$VISUAL`/`$EDITOR` environment variables for multiline editing.

- **utils.py**: Shared utilities and constants. Includes `APP_STORE_LOCALES` dict (38+ locales), `FIELD_LIMITS` dict (character limits per field), helper functions (`detect_base_language`, `truncate_keywords`, `validate_field_length`, `parallel_map_locales` for concurrent translations), and print helpers (`print_success/error/warning/info`).

- **ai_logger.py**: AI request/response logging. Logs all translation requests, responses, errors, and retry attempts to `logs/ai_requests_YYYYMMDD_HHMMSS.log`. Redacts API keys. Used for debugging translation quality and provider comparison.

- **release_presets.py**: Manages reusable release note templates. Supports built-in presets (fresh features, bug fixes) and custom user-created presets stored in JSON files under `presets/`.

### Workflow Architecture Pattern

All workflows live in `workflows/` and follow a consistent pattern:
- Each workflow is a Python module with a `run(cli)` function as the entry point
- The `cli` parameter is the `TranslateRCLI` instance with access to `ui`, `asc_client`, `ai_manager`, `config`, `session_seed`
- Workflows use `ui.prompt_app_id()` for app selection, `ui.select()`/`ui.checkbox()` for multi-choice prompts
- Translation workflows use `parallel_map_locales()` for concurrent translation of multiple locales
- Always check field character limits via `get_field_limit()` before/after translation
- Return `True` to continue CLI loop, `False` to exit

### Key Workflow Files

- **workflows/release.py**: "What's New" release notes workflow. Supports multi-platform selection (iOS, macOS, tvOS, visionOS), detects base locale, allows source note editing with preset library, translates to target locales, provides review/edit/re-enter loop, applies updates per platform including base locale if empty.

- **workflows/translate.py**: General metadata translation workflow. Supports metadata-only or complete translation (includes app name/subtitle), multi-platform selection, detects missing localizations, translates all metadata fields with character limit enforcement.

- **workflows/promo.py**: Promotional text update workflow. Updates promotional text (170 chars) across all platforms and locales simultaneously.

- **workflows/update_localizations.py**: Fill missing localization fields for existing locales. Detects gaps in metadata coverage.

- **workflows/copy.py**: Copy metadata between versions/platforms without translation.

- **workflows/full_setup.py**: Initial setup for new apps. Translates to all 38+ supported languages in one pass.

- **workflows/export_localizations.py**: Export current App Store metadata to timestamped JSON files in `existing_localizations/` for backup.

- **workflows/manage_presets.py**: Create/browse/delete release note presets. Creates AI-translated presets for all locales automatically.

- **workflows/iap_translate.py**: Translate in-app purchase display names (30 chars) and descriptions (45 chars) for selected IAP products.

- **workflows/subscription_translate.py**: Translate subscription names and descriptions for subscription groups.

- **workflows/game_center_localizations.py**: Translate Game Center achievements and leaderboards with multi-platform support.

- **workflows/app_events_translate.py**: Translate App Store in-app event metadata (name, short description, long description).

## Critical Implementation Details

### Character Limits and Field Validation

Character limits are strictly enforced and defined in `utils.FIELD_LIMITS`:
- App Name: 30 chars
- Subtitle: 30 chars
- Description: 4000 chars
- Keywords: 100 chars (ASO format: `word1,word2,word3` - no spaces after commas)
- Promotional Text: 170 chars
- What's New: 4000 chars
- IAP Name: 30 chars, IAP Description: 45 chars
- Subscription Name: 60 chars, Description: 200 chars
- App Event Name: 30 chars, Short Description: 50 chars, Long Description: 120 chars

**Always** call `get_field_limit(field_name)` before passing to AI providers. Providers automatically retry with stricter prompts if limit is exceeded (see `ai_providers.py` retry logic).

### Translation System Prompts

Base translation instructions are in `config/instructions.txt`. Key requirements:
- Natural language flow for native speakers (avoid robotic literal translations)
- Character limits are CRITICAL and include ALL spaces/punctuation
- Keywords use ASO-optimized format (no spaces after commas)
- Marketing tone preservation
- Cultural adaptation while preserving meaning

Users can add:
1. **Global refinement**: Set via Configuration menu, stored in `providers.json` `prompt_refinement` field
2. **Per-run refinement**: Prompted during each workflow, appended to system message

### Concurrent Translation

Use `parallel_map_locales()` from `utils.py` for concurrent translation:
```python
results = parallel_map_locales(
    locales_to_translate,
    translate_fn,
    progress_label="Translating",
    concurrency=None  # Uses TRANSLATER_CONCURRENCY env var or CPU count
)
```

This provides automatic progress tracking and handles errors gracefully.

### Deterministic Translation (Session Seed)

`cli.session_seed` is a random integer generated once per CLI session. Pass it to `provider.translate(seed=cli.session_seed)` to ensure consistent translations across all locales in a single workflow run (reduces translation variance when re-translating).

### App Store Connect API Patterns

- **Authentication**: JWT tokens generated per request, valid for 20 minutes
- **Retry Logic**: 409 conflicts auto-retry with exponential backoff (3 attempts)
- **Pagination**: Use `get_apps_page()` with cursor-based pagination for large app lists
- **Version Detection**: `get_latest_app_store_version_info()` returns version ID, version string, and state
- **Multi-platform**: Same app can have separate versions for iOS, macOS, tvOS, visionOS - handle per-platform in workflows
- **Base Locale**: Usually `en-US`, detected via `detect_base_language()` by finding locale with most complete metadata

### UI/TUI Behavior

`ui.py` provides dual-mode operation:
- **TUI mode** (InquirerPy available): Arrow-key navigation, fuzzy search in app picker, multi-select checkboxes
- **Fallback mode**: Standard stdin/stdout prompts with numbered choices

For multiline editing:
1. Try `$VISUAL` or `$EDITOR` (e.g., `code -w`, `vim`, `nano`)
2. Fall back to `nano`/`vi` on Unix, `notepad` on Windows
3. Ultimate fallback: EOF-terminated inline editor

### Configuration Files

Created in `config/` on first run (gitignored):
- **api_keys.json**: App Store Connect credentials (key_id, issuer_id, private_key_path) and AI provider API keys (anthropic_api_key, openai_api_key, google_api_key)
- **providers.json**: Provider catalog with models list, default_model per provider, optional default_provider (used as suggested choice in workflows), optional prompt_refinement (global guidance phrase)
- **instructions.txt**: AI system prompt template for translations

Environment variable overrides:
- AI keys: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`/`GEMINI_API_KEY`/`GOOGLE_GEMINI_API_KEY`
- Editor: `VISUAL` or `EDITOR`
- Concurrency: `TRANSLATER_CONCURRENCY` (default: CPU core count)

### Logging and Debugging

All AI requests/responses logged to `logs/ai_requests_YYYYMMDD_HHMMSS.log` with:
- Request: provider, model, target language, max length, original text, seed, refinement
- Response: translated text, character count, success/failure
- Errors: HTTP status, error codes, request IDs, retry attempts
- Never logs API keys

Export workflow saves metadata snapshots to `existing_localizations/` for backup/analysis.

## Coding Conventions

### Python Style
- Python 3, 4-space indentation
- Type hints from `typing` module (Dict, List, Optional, Any)
- Docstrings for modules and complex functions
- snake_case for functions/variables/files
- PascalCase for classes
- UPPER_SNAKE_CASE for constants

### Module Organization
- Keep workflows small and focused on single tasks
- Extract reusable logic to `utils.py` or create new utility modules
- Use existing print helpers: `print_success()`, `print_error()`, `print_warning()`, `print_info()`
- Follow established patterns in existing workflows

### Error Handling
- Validate App Store Connect API responses before accessing nested data
- Use try/except for API calls with informative error messages
- Never commit secrets - use environment variables or config files (gitignored)
- Test against non-production apps first

## Common Development Tasks

### Adding a New Workflow
1. Create `workflows/new_workflow.py` with `run(cli)` function
2. Import in `main.py`: `from workflows.new_workflow import run as new_workflow_run`
3. Add menu item in `TranslateRCLI.show_main_menu()` method
4. Follow existing workflow patterns: app selection, platform selection, base locale detection, translation loop, apply to ASC

### Adding Support for New AI Provider
1. Create new provider class in `ai_providers.py` extending `AIProvider`
2. Implement `translate()` and `get_name()` methods
3. Add provider config to `DEFAULT_PROVIDERS_TEMPLATE` in `config.py`
4. Add initialization logic in `TranslateRCLI.setup_ai_providers()`

### Adding a New Metadata Field
1. Add character limit to `FIELD_LIMITS` in `utils.py`
2. Update relevant workflow to include new field in translation loop
3. Update App Store Connect API client methods if new endpoint needed
4. Update `config/instructions.txt` with field-specific guidelines if needed

### Debugging Translation Issues
1. Check `logs/ai_requests_*.log` for exact prompts and responses
2. Verify character limits in `utils.FIELD_LIMITS` match App Store requirements
3. Test with different providers to compare translation quality
4. Use `export_localizations` workflow to snapshot current state before changes

## Important Notes

- **App Store Connect .p8 Keys**: Default location is `~/.appstoreconnect/private_keys/`, but custom paths are supported
- **API Rate Limits**: Handle 409 conflicts with retry logic (already implemented in `app_store_client.py`)
- **Character Counting**: All limits include spaces, punctuation, special characters
- **Keyword Format**: ASO-optimized format requires no spaces after commas: `word1,word2,word3`
- **Multi-platform Apps**: Same app ID can have separate versions per platform (iOS, macOS, tvOS, visionOS) - workflows must handle per-platform
- **Base Locale Detection**: Usually `en-US`, but workflows auto-detect by finding locale with most complete metadata
- **Translation Consistency**: Use `cli.session_seed` passed to providers for deterministic translations across a workflow run
- **Git Ignored Files**: `config/`, `logs/`, `existing_localizations/`, `__pycache__/` are all gitignored - never commit secrets
