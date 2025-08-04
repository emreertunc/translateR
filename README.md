# TranslateR 🌍

Automate App Store Connect localizations with AI translation. Transform your single-language app metadata into 38+ localized versions with just a few commands.

## What It Does

TranslateR connects to your App Store Connect account and automatically translates your app's metadata (description, keywords, promotional text, what's new) into multiple languages using AI providers like Claude, GPT, or Gemini.

**Before**: Manually translate and upload metadata for each language  
**After**: Select languages, choose AI provider, hit enter. Done.

## Quick Start

1. **Install**
   ```bash
   git clone https://github.com/your-username/translateR.git
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

## 5 Main Workflows

### 1. 🔄 Translation Mode
**Use when**: Adding new languages to your app

- Detects your base language (usually English)
- Shows untranslated languages
- Translates all metadata fields
- Creates new localizations

### 2. ✏️ Update Mode
**Use when**: Updating existing translations (e.g., new "What's New" content)

- Updates specific fields in existing languages
- Choose which languages and fields to update
- Perfect for version updates

### 3. 📋 Copy Mode
**Use when**: New app version with similar content

- Copy content from previous version
- No translation needed
- Fast setup for new versions

### 4. 🌐 Full Setup Mode  
**Use when**: Complete localization for new apps

- Translate into ALL 38+ supported languages
- Maximum global reach
- One-command setup

### 5. 📱 App Name & Subtitle Mode
**Use when**: Translating app name and subtitle

- Separate workflow for branding elements
- 30-character limits enforced
- Brand-focused translations

## Supported Fields & Languages

**Fields**: Description (4000 chars), Keywords (100 chars), Promotional Text (170 chars), What's New (4000 chars), App Name (30 chars), Subtitle (30 chars)

**Languages**: All 38 App Store locales including German, French, Spanish, Chinese, Japanese, Korean, Arabic, and more.

## Example Workflow

```bash
$ python3 main.py

TranslateR - App Store Localization Tool
1. 🔄 Translation Mode
2. ✏️ Update Mode  
3. 📋 Copy Mode
4. 🌐 Full Setup Mode
5. 📱 App Name & Subtitle Mode

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
Model: claude-sonnet-4-20250514
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

MIT License - Free for personal and commercial use.

---

⚠️ **Important**: Always review AI translations before publishing. Test with non-production apps first.

💡 **Tip**: Start with major markets (English, Spanish, German, Chinese) before expanding to all languages.