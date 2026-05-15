# TranslateR

```
████████ ██████   █████  ███   ██  ███████ ██       █████  ████████ ███████ ██████  
   ██    ██   ██ ██   ██ ████  ██  ██      ██      ██   ██    ██    ██      ██   ██ 
   ██    ██████  ███████ ██ ██ ██  ███████ ██      ███████    ██    █████   ██████  
   ██    ██   ██ ██   ██ ██  ████       ██ ██      ██   ██    ██    ██      ██   ██ 
   ██    ██   ██ ██   ██ ██   ███  ███████ ███████ ██   ██    ██    ███████ ██   ██ 
```
<div align="center">

**🌍 AI-Powered App Store Connect Localization Tool**

</div>

Automate App Store Connect localizations with AI translation. Transform your single-language app metadata into 38+ localized versions with just a few commands.

## What It Does

TranslateR connects to your App Store Connect account and translates or updates localized content with AI providers like Claude, GPT, or Gemini.

**Before**: Manually translate and upload metadata for each language  
**After**: Select languages, choose AI provider, hit enter. Done.

## Quick Start

1. **Install**
   ```bash
   git clone https://github.com/emreertunc/translateR.git
   cd translateR
   pip install -r requirements.txt
   ```

2. **Setup** (one-time)
   ```bash
   python3 main.py
   ```
   - Add your App Store Connect API key (.p8 file)
   - Add at least one AI provider API key (Claude/GPT/Gemini)

3. **Use**
   ```bash
   python3 main.py
   ```
   Choose your workflow and follow prompts.

## What You Need

### App Store Connect API Key
1. Go to App Store Connect > Users and Access > Integrations
2. Create API key with **App Manager** role
3. Download the `.p8` file and place it in your project directory
4. Note your Key ID and Issuer ID

### AI Provider (pick one or more)
- **Claude**: [Get key](https://console.anthropic.com/) - Best translation quality (recommended)
- **GPT**: [Get key](https://platform.openai.com/) - Most reliable
- **Gemini**: [Get key](https://makersuite.google.com/) - Fastest

## Main Workflows

Current workflow set:
1. 🌐 Translation Mode
2. 🔄 Update Mode
3. 📋 Copy Mode
4. 🚀 Full Setup Mode
5. 📱 App Name & Subtitle Mode
6. ♻️ Revert App Name Mode
7. 📄 Export Localizations
8. 🛒 IAP Translations
9. 💳 Subscription Translations
10. 🏆 Game Center Translations
11. 🎉 In-App Events Translations

### 1. 🌐 Translation Mode
**Use when**: Adding new languages to your app metadata

- Detects base language and missing target locales
- Translates description, keywords, promotional text, and what's new
- Can include app name and subtitle translation
- Creates missing localizations in App Store Connect

### 2. 🔄 Update Mode
**Use when**: Updating existing localizations for new content

- Works on already existing locales
- Lets you choose specific fields to update
- Useful for new version notes without touching everything
- Preserves untouched fields

### 3. 📋 Copy Mode
**Use when**: Reusing previous version content

- Copies localization content from one version to another
- Updates existing localizations or creates missing ones
- Avoids unnecessary AI translation when text is already ready

### 4. 🚀 Full Setup Mode
**Use when**: Complete localization for new apps

- Translate into ALL 38+ supported languages
- Maximum global reach
- One-command setup

### 5. 📱 App Name & Subtitle Mode
**Use when**: Translating app name and subtitle

- Focuses on app name and subtitle
- Enforces 30-character limits
- Updates app info localizations safely

### 6. ♻️ Revert App Name Mode
**Use when**: Standardizing localized app names to base language

- Resets localized app names to base locale value
- Uses editable-state checks before update
- Useful when brand naming should stay identical across locales

### 7. 📄 Export Localizations
**Use when**: Backing up or auditing existing localizations

- Export all existing localizations to timestamped file
- Choose latest version or specific version
- Complete backup with all metadata fields
- Creates organized JSON export with app details

### 8. 🛒 IAP Translations
**Use when**: Localizing in-app purchase metadata

- Selects one or more IAP items
- Translates IAP name and description into missing locales
- Applies character limits and conflict-safe create/update logic

### 9. 💳 Subscription Translations
**Use when**: Localizing subscription products or groups

- Supports subscription and subscription group scope
- Translates relevant name/description fields
- Creates missing localizations and updates on conflicts

### 10. 🏆 Game Center Translations
**Use when**: Localizing Game Center resources

- Supports achievements, leaderboards, activities, and challenges
- Handles detail/group resources and versioned entities
- Applies locale matching and conflict recovery

### 11. 🎉 In-App Events Translations
**Use when**: Localizing event listing content

- Selects events and translates name/short/long descriptions
- Targets missing locales with safe create/update flow
- Keeps field limits aligned with App Store requirements

## Supported Fields & Languages

**Core metadata fields**: Description (4000), Keywords (100), Promotional Text (170), What's New (4000), App Name (30), Subtitle (30)

**App info URLs**: Privacy Policy URL (255), Marketing URL (255), Support URL (255).
Complete Translation mode copies these URLs from base locale to target locales.

**IAP fields**: Name (30), Description (45)
**Subscription fields**: Name (60), Description (200), Group Name (60), Group Custom App Name (30)
**In-App Event fields**: Name (30), Short Description (50), Long Description (120)
**Game Center text fields**: Name/Description fields up to 30/200 chars by resource type.

**Languages**: All 38 App Store locales including German, French, Spanish, Chinese, Japanese, Korean, Arabic, and more.

## Example Workflow

```bash
$ python3 main.py

TranslateR - App Store Localization Tool
1. 🌐 Translation Mode
2. 🔄 Update Mode
3. 📋 Copy Mode
4. 🚀 Full Setup Mode
5. 📱 App Name & Subtitle Mode
...
10. 🛒 IAP Translations
11. 💳 Subscription Translations
12. 🏆 Game Center
13. 🎉 In-App Events

Choose: 1

Apps found:
1. My Awesome App (v2.1)

Select app: 1
Base language detected: English (US)

Available target languages:
1. German  2. French  3. Spanish  4. Chinese (Simplified)
[... 34 more languages]

Select languages (comma-separated or 'all'): 1,2,3
AI Provider: Claude 4 Sonnet (recommended)

Translating German... ✓
Translating French... ✓  
Translating Spanish... ✓

✅ Translation completed! 3/3 languages successful
```

## Configuration Files

After first run, config files are created in `config/`:

**`api_keys.json`** - Your API keys and credentials  
**`providers.json`** - AI provider settings  
**`instructions.txt`** - Translation guidelines for AI
**`saved_apps.json`** - Saved app IDs and labels

## Logging & Debugging

All AI requests and responses are automatically logged for debugging and quality control:

**Location**: `logs/ai_requests_YYYYMMDD_HHMMSS.log`

**What's logged**:
- All translation requests with original text and parameters
- AI responses with translated text and character counts
- Error details when translations fail
- Character limit retry attempts
- Timestamps for performance analysis

**Log format example**:
```
[2025-08-05 10:30:15] REQUEST
Provider: Anthropic Claude
Model: claude-sonnet-4-6
Target Language: German
Max Length: 100
Original Text (45 chars):
--------------------------------------------------
Transform your ideas into beautiful apps
--------------------------------------------------

[2025-08-05 10:30:18] RESPONSE - SUCCESS
Provider: Anthropic Claude
Translated Text (42 chars):
--------------------------------------------------
Verwandeln Sie Ihre Ideen in schöne Apps
--------------------------------------------------
```

**Benefits**:
- **Debug translation issues** - See exactly what was sent and received
- **Compare AI providers** - Track which providers work best for your content
- **Quality control** - Review translations before publishing
- **Performance monitoring** - Identify slow or failing requests

**Privacy**: API keys are never logged. Log files stay on your machine (not in git).

## Troubleshooting

**Error: "App Store Connect configuration not found"**  
→ Check your .p8 file path and API credentials

**Error: "No AI providers configured"**  
→ Add at least one valid AI provider API key

**Error: "Translation failed"**  
→ Check API quotas/limits, try different provider

## Contributing

1. Fork the repo
2. Create feature branch
3. Follow patterns in existing code
4. Test with real App Store data
5. Submit PR

## License

**MIT License**

Copyright (c) 2025 Emre Ertunç

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

**Author**: Emre Ertunç  
**Contact**: emre@ertunc.com  
**Repository**: https://github.com/emreertunc/translateR

---

⚠️ **Important**: Always review AI translations before publishing. Test with non-production apps first.

💡 **Tip**: Start with major markets (English, Spanish, German, Chinese) before expanding to all languages.
