"""
generate_header.py - Weekly Digest Header Image Generator
Uses OpenAI DALL-E 3 to generate header_image.png each Monday.

Usage:
    python generate_header.py

Set your OpenAI API key as an environment variable:
    Windows: set OPENAI_API_KEY=sk-...
    GitHub Actions: add as a secret named OPENAI_API_KEY
"""

import os
import sys
import json
import urllib.request
import urllib.parse
from datetime import datetime, timedelta

# pip install openai
from openai import OpenAI

# ── CONFIG ────────────────────────────────────────────────────────────────────

OUTPUT_PATH = "header_image.png"   # saved alongside digest_builder.py

# Image generation settings
# gpt-image-1 is the same model ChatGPT uses in the chat interface —
# significantly better text rendering than dall-e-3
IMAGE_SIZE    = "1536x1024"  # gpt-image-1 supports this exact size
IMAGE_QUALITY = "medium"    # gpt-image-1 options: 'low', 'medium', 'high', 'auto'
IMAGE_MODEL   = "gpt-image-1"

# ── WEEKLY THEMES ─────────────────────────────────────────────────────────────
# Themes are auto-generated each week based on current events in Charlotte
# and nationally. You can still override any specific week by adding it here.
# Format: "YYYY-MM-DD" (Monday of that week): ("Primary Theme", "Wildcard Modifier")

THEMES = {
    # "2026-05-04": ("Summer Kickoff", "Neon glow accents"),  # manual override example
}

# Claude model used to pick theme/wildcard from news context
THEME_MODEL = "gpt-4o-mini"

# ── PROMPT TEMPLATE ───────────────────────────────────────────────────────────

PROMPT_TEMPLATE = """Create a 1536 x 1024 modern editorial header image for a corporate newsletter.

CRITICAL TEXT REQUIREMENTS — render these exactly, letter-perfect:
- Large centered title: the letter E, then a period, then the letters i n C L T, then a space, then the words Weekly Digest
  Written out: E.inCLT Weekly Digest
- Subheader below the title: Office Updates • Events • Celebrations
- Do NOT add any other words, labels, captions, or descriptions anywhere in the image

BOTTOM ICON ROW — exactly 3 icons only, no labels or text beneath them:
- Three minimal modern icons evenly spaced along the bottom third
- Connected left-to-right by a single subtle glowing horizontal line
- Icon 1 (left): envelope/mail icon with a small notification badge
- Icon 2 (center): calendar icon
- Icon 3 (right): party popper / celebration icon
- No text, no captions, no labels under or near the icons

PRIMARY THEME: {theme}
WILDCARD MODIFIER: {wildcard}

Style requirements:
- Professional, clean, editorial (not stock photo)
- Strong typography hierarchy — title must be the dominant visual element
- Plenty of negative space for readability
- Balanced composition with text clearly legible against the background
- Cohesive color palette based on the theme
- Subtle depth via lighting, blur, or overlays based on the wildcard

Avoid:
- Any misspelled words — especially the title text
- Extra icons beyond the 3 specified
- Any text labels under the icons
- Duplicate buildings or distorted skylines
- Cluttered or busy scenes
- Overly cartoonish elements"""

# ── HELPERS ───────────────────────────────────────────────────────────────────

def get_current_monday():
    today = datetime.today().date()
    return today - timedelta(days=today.weekday())

def search_current_events(monday):
    """Search for current events in Charlotte and nationally for the given week."""
    week_str = monday.strftime("%B %d, %Y")
    queries = [
        f"Charlotte NC events happenings {week_str}",
        f"national events holidays awareness {monday.strftime('%B %Y')}",
    ]
    snippets = []
    for query in queries:
        try:
            encoded = urllib.parse.quote(query)
            url = f"https://api.search.brave.com/res/v1/web/search?q={encoded}&count=5"
            brave_key = os.getenv("BRAVE_API_KEY")
            if brave_key:
                req = urllib.request.Request(url, headers={
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip",
                    "X-Subscription-Token": brave_key,
                })
                with urllib.request.urlopen(req, timeout=10) as r:
                    data = json.loads(r.read())
                    for result in data.get("web", {}).get("results", [])[:3]:
                        snippets.append(result.get("description", ""))
        except Exception as e:
            print(f"     Search warning: {e}")
    return " ".join(snippets) if snippets else ""


def auto_generate_theme(monday, openai_client):
    """Use GPT-4o-mini to pick a theme and wildcard based on current events."""
    print("     Auto-generating theme from current events...")
    week_str = monday.strftime("%B %d, %Y")
    month_str = monday.strftime("%B")

    # Get news context if Brave API key is available
    news_context = search_current_events(monday)
    if news_context:
        print(f"     Found news context ({len(news_context)} chars)")
    else:
        print("     No news context found — generating from date/season only")

    context_block = f"News snippets:\n{news_context[:1500]}" if news_context else                     f"Week of {week_str} in {month_str}. Consider seasonal themes, Charlotte culture, or general office/corporate themes."

    prompt = f"""You are helping generate a weekly newsletter header image theme for a Charlotte, NC corporate office newsletter called "E.inCLT Weekly Digest".

The week is: {week_str}

{context_block}

Based on what's happening this week in Charlotte or nationally, suggest:
1. A PRIMARY THEME for the header image (e.g. "Spring Festival Season in Charlotte", "NBA Playoffs Energy", "Memorial Day Weekend")
2. A WILDCARD MODIFIER that adds visual interest (e.g. "Watercolor wash overlay", "Neon glow accents", "Cinematic lens flare")

Rules:
- Theme should feel timely and relevant to the week
- Avoid anything political or controversial
- Keep it professional and suitable for a corporate newsletter
- Wildcard should be a visual/artistic style modifier, not a second theme

Respond in this exact JSON format with no other text:
{{"theme": "...", "wildcard": "..."}}"""

    response = openai_client.chat.completions.create(
        model=THEME_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=150,
        response_format={"type": "json_object"},
    )
    data = json.loads(response.choices[0].message.content)
    return data["theme"], data["wildcard"]


def get_theme_for_week(monday, openai_client):
    """Return (theme, wildcard) for the given Monday — manual override or auto-generated."""
    key = monday.strftime("%Y-%m-%d")
    if key in THEMES:
        theme, wildcard = THEMES[key]
        print(f"     Using manual theme override")
        print(f"     Theme: {theme}")
        print(f"     Wildcard: {wildcard}")
        return theme, wildcard

    theme, wildcard = auto_generate_theme(monday, openai_client)
    print(f"     Theme: {theme}")
    print(f"     Wildcard: {wildcard}")
    return theme, wildcard

# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  E.inCLT Header Image Generator")
    print("=" * 60)

    # Check API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("\n❌ OPENAI_API_KEY environment variable not set.")
        print("   Set it with: set OPENAI_API_KEY=sk-...")
        sys.exit(1)

    monday = get_current_monday()
    print(f"\nWeek of: {monday.strftime('%B %d, %Y')}")

    # Generate theme using gpt-4o-mini (same OpenAI key, costs <$0.001 per week)
    client = OpenAI(api_key=api_key)
    theme, wildcard = get_theme_for_week(monday, client)
    prompt = PROMPT_TEMPLATE.format(theme=theme, wildcard=wildcard)

    print(f"\nCalling DALL-E 3 API...")

    response = client.images.generate(
        model=IMAGE_MODEL,
        prompt=prompt,
        size=IMAGE_SIZE,
        quality=IMAGE_QUALITY,
        n=1,
    )

    print(f"     Image generated ✅")

    # gpt-image-1 returns base64-encoded image data
    import base64
    image_data = base64.b64decode(response.data[0].b64_json)
    print(f"\nSaving to: {OUTPUT_PATH}")
    with open(OUTPUT_PATH, "wb") as f:
        f.write(image_data)

    size_kb = os.path.getsize(OUTPUT_PATH) // 1024
    print(f"     Saved ({size_kb} KB)")
    print(f"\n{'=' * 60}")
    print(f"  Done! header_image.png is ready for digest_builder.py")
    print(f"{'=' * 60}\n")

if __name__ == "__main__":
    main()
