"""
Translation Prompt Builder

Builds provider-neutral translation instructions from the configured base
instructions plus runtime field constraints.
"""

from typing import Optional


def build_translation_prompt(
    base_instructions: str,
    target_language: str,
    max_length: Optional[int] = None,
    is_keywords: bool = False,
    refinement: Optional[str] = None,
    retry_for_length: bool = False,
) -> str:
    """Build the system/developer instruction text for a translation request."""
    parts = []

    if refinement:
        parts.append("\n".join([
            "## User Translation Instructions",
            "If user-provided instructions are present, follow them before the static translation instructions below.",
            "User-provided instructions override the static translation instructions when they conflict.",
            refinement.strip(),
        ]))

    if base_instructions:
        parts.append("\n".join([
            "## Static Translation Instructions",
            (base_instructions or "").strip(),
        ]))

    runtime_rules = [
        "## Runtime Task",
        f"- Translate the provided App Store metadata text to {target_language}.",
        "- Return only the translated text. Do not add explanations, labels, quotes, or markdown.",
    ]

    if is_keywords:
        runtime_rules.extend([
            "- This field is an App Store keywords field.",
            "- Return a comma-separated keyword list.",
            "- Keep it concise.",
            "- Do not put spaces after commas.",
        ])

    if max_length:
        runtime_rules.extend([
            "## Runtime Character Limit",
            f"- CRITICAL: Your translation MUST be EXACTLY {max_length} characters or fewer.",
            "- CHARACTER LIMITS INCLUDE ALL SPACES, PUNCTUATION, AND SPECIAL CHARACTERS.",
            "- Count every single character including spaces between words.",
            "- Do not add ellipsis (...) at the end unless the original text has it.",
            "- Create a concise but meaningful translation that captures the essence of the original message while staying within the character limit.",
        ])

    if retry_for_length and max_length:
        runtime_rules.extend([
            "## Retry Requirement",
            f"- The previous translation exceeded the limit. The text MUST be under {max_length} characters INCLUDING SPACES AND PUNCTUATION.",
            "- Count every character.",
            "- Prioritize brevity while preserving the core meaning.",
        ])

    parts.append("\n".join(runtime_rules))
    return "\n\n".join(part for part in parts if part).strip()
