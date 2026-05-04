"""
digest_builder.py - E.inCLT Weekly Digest HTML Generator
Reads a local .ics file and header image, produces weekly_events.html

Usage:
    python digest_builder.py

Configuration:
    Update the CONFIG section below each week before running.
"""

from datetime import datetime, timedelta
from collections import defaultdict
import base64
import html
import os
import re

# ── CONFIG — update these each week ──────────────────────────────────────────

ICS_PATH        = "Office Activity Calendar.ics"   # path to your exported .ics file
HEADER_IMG_PATH = "header_image.png"               # path to your header image
BIRTHDAY_GIF    = "birthday_icon.gif"              # path to birthday gif (keep in same folder)
OUTPUT_PATH     = "weekly_events.html"             # output file name
FIXED_WIDTH     = 800                              # email width in pixels

# Set to the Monday of the week you want to generate, or leave as None for auto (current week)
WEEK_START_OVERRIDE = None  # e.g. datetime(2026, 5, 4) to force a specific week

# Manually injected events — add any events missing from the .ics here
# Format: {"summary": "...", "start": datetime(...), "end": datetime(...), "location": "..."}
# Set "end" to None if no end time. Remove or leave empty list if nothing to inject.
INJECTED_EVENTS = [
    # Example:
    # {"summary": "Singles Night in the Mount", "start": datetime(2026, 3, 21, 18, 0),
    #  "end": datetime(2026, 3, 21, 21, 0), "location": "That's Novel Books — 330 Camp Rd Suite B"},
]

# Featured event keyword — any event summary containing this word gets the featured section
# Set to None to disable featured section
FEATURED_KEYWORD = None   # e.g. "empanada"

# Keywords that map event names/locations to specific sub-categories
KEYWORD_MAP = {
    "Free Range Bar": "Social",
    "Ice Skating":    "Seasonal Activities",
}

# ── HOLIDAY LIST — add to this as needed ─────────────────────────────────────

NAMED_HOLIDAYS = {
    "new year's day", "valentine's day", "president's day", "memorial day",
    "independence day", "labor day", "halloween", "thanksgiving day",
    "black friday", "christmas eve", "christmas day",
    "st. patrick's day", "saint patrick's day", "tax day",
    "daylight saving time starts", "daylight savings time starts",
    "good friday", "easter sunday", "easter monday",
}

# ── ASSET LOADER ──────────────────────────────────────────────────────────────

def load_b64(path):
    if not os.path.exists(path):
        print(f"WARNING: Asset not found: {path}")
        return ""
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

# ── DATE HELPERS ──────────────────────────────────────────────────────────────

def parse_dt(val):
    val = val.strip()
    if val.endswith("Z"):
        val = val[:-1]
    try:
        return datetime.strptime(val[:15], "%Y%m%dT%H%M%S") if "T" in val \
               else datetime.combine(datetime.strptime(val[:8], "%Y%m%d").date(), datetime.min.time())
    except:
        return None

def get_week_range():
    if WEEK_START_OVERRIDE:
        sow = WEEK_START_OVERRIDE
    else:
        today = datetime.combine(datetime.today().date(), datetime.min.time())
        sow   = today - timedelta(days=today.weekday())
    return sow, sow + timedelta(days=7)

# ── ICS PARSER ────────────────────────────────────────────────────────────────

def load_ics(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        content = re.sub(r"\r?\n[ \t]", "", f.read())

    events = []
    for block in re.split(r"BEGIN:VEVENT", content)[1:]:
        block = block.split("END:VEVENT")[0]

        def gf(name, b=block):
            m = re.search(rf"^{name}[;:][^\r\n]*", b, re.MULTILINE)
            return (m.group(0).split(":", 1)[-1].strip() if ":" in m.group(0) else "") if m else ""

        ms    = re.search(r"^DTSTART[^:]*:(\S+)", block, re.MULTILINE)
        me    = re.search(r"^DTEND[^:]*:(\S+)",   block, re.MULTILINE)
        start = parse_dt(ms.group(1)) if ms else None
        if not start:
            continue

        loc = gf("LOCATION").strip() or None
        if loc:
            loc = loc.replace("\\,", ",")

        events.append({
            "uid":         gf("UID"),
            "summary":     gf("SUMMARY"),
            "location":    loc,
            "description": gf("DESCRIPTION"),
            "categories":  gf("CATEGORIES"),
            "start":       start,
            "end":         parse_dt(me.group(1)) if me else None,
        })
    return events

# ── CATEGORIZATION ────────────────────────────────────────────────────────────

def is_holiday(s, d):
    s, d = (s or "").lower(), (d or "").lower()
    return (s in NAMED_HOLIDAYS
            or "public holiday" in d
            or "daylight saving" in s
            or "st. patrick" in s)

def categorize(summary, location, description, categories):
    lower = (summary or "").lower()
    loc   = (location or "").lower()
    desc  = (description or "").lower()

    if "birthday"    in lower: return "Birthdays", None
    if "anniversary" in lower: return "Anniversaries", None
    if is_holiday(summary, description): return "Holidays", None

    if FEATURED_KEYWORD and FEATURED_KEYWORD.lower() in lower:
        return "🫔 Featured Event", None

    if categories and categories.lower() == "conference":
        return "Conference", None
    if categories:
        return "CLT Office Activity", categories

    matched = next(
        (g for k, g in KEYWORD_MAP.items()
         if k.lower() in lower or k.lower() in loc),
        None
    )
    return (matched or "Camp North End Events"), None

# ── HTML BUILDER ──────────────────────────────────────────────────────────────

def build_html(grouped, sow, eow, gif_b64, img_b64):
    week_label = f"{sow.strftime('%B %d')} - {(eow - timedelta(days=1)).strftime('%B %d, %Y')}"

    css = f"""
body{{font-family:Arial,sans-serif;background:#f4f4f4;margin:0;padding:0}}
.wrapper{{width:{FIXED_WIDTH}px;margin:0 auto;background:#fff;border-radius:8px;box-shadow:0 2px 12px rgba(0,0,0,.15)}}
.inner{{padding:20px}}
h1{{text-align:center;color:#333}}
h3{{color:#004085;margin-top:20px;font-size:1.1em}}
.event{{border-bottom:1px solid #ccc;padding:10px;border-radius:6px;margin-bottom:8px}}
.event:last-child{{border-bottom:none}}
.birthday{{background-color:#d6eaff}}
.anniversary{{background-color:#fffbe6;border-left:6px solid #faad14}}
.conference-highlight{{background-color:#fff0cc;border-left:6px solid #ff9900}}
.holiday{{background-color:#e8f5e9;border-left:6px solid #2e7d32}}
.date{{font-weight:bold;color:#28a745}}
.time{{color:#666}}
.location{{color:#555;font-style:italic}}
.summary{{margin-top:2px}}
.summary img{{margin-left:8px;vertical-align:middle}}
.description{{color:#333;margin-top:6px;font-size:.95em;font-style:italic}}
.featured-card{{background-color:#fff0cc;border:2px solid #e8622a;border-left:10px solid #b5451b;border-radius:8px;padding:16px 18px;margin-bottom:12px}}
.featured-card .summary{{font-size:1.15em;font-weight:bold;color:#1a1a1a}}
.featured-card .date{{color:#b5451b;font-weight:bold;font-size:1.05em}}
.featured-card .time{{color:#666;font-size:.95em;margin-top:2px}}
.featured-card .location{{color:#7a4030;font-style:italic;margin-top:4px}}
"""

    out = (
        f'<html><head><meta charset="UTF-8"><style>{css}</style></head>\n'
        f'<body><table width="100%" cellspacing="0" cellpadding="0" style="background:#f4f4f4;">'
        f'<tr><td align="center"><table class="wrapper"><tr><td class="inner">\n'
        f'<img src="data:image/png;base64,{img_b64}" width="{FIXED_WIDTH}" style="display:block;margin:0 auto 20px auto;">\n'
        f'<h1>This Week\'s Office &amp; Camp North End Events</h1>\n'
        f'<p style="text-align:center;color:#666;margin-top:-10px;">{week_label}</p>\n'
    )

    def sort_key(n):
        o = {"🫔 Featured Event": 0, "Birthdays": 1, "Anniversaries": 2,
             "CLT Office Activity": 3, "Conference": 4, "Holidays": 5, "Camp North End Events": 6}
        return (o.get(n, 99), n)

    for tg in sorted(grouped.keys(), key=sort_key):
        is_featured = tg == "🫔 Featured Event"
        h2_style = (
            "background-color:#b5451b;color:#fff;padding:12px 14px;"
            "font-size:1.35em;text-align:center;letter-spacing:1px;margin:0 0 8px 0"
            if is_featured else
            "background-color:#004085;color:#fff;padding:10px;"
            "font-size:1.2em;margin:0 0 8px 0"
        )
        out += f'<h2 style="{h2_style}">{html.escape(tg)}</h2>\n'

        for sg, evs in grouped[tg].items():
            evs.sort(key=lambda e: e["start"])
            if sg:
                out += f'<h3>{html.escape(sg)}</h3>\n'

            for e in evs:
                ds  = e["start"].strftime("%a %b %d, %Y")
                ss  = html.escape(e["summary"] or "")
                sl  = html.escape(e["location"]) if e.get("location") else None
                ht  = e["start"].hour != 0 or e["start"].minute != 0
                ts  = (
                    f"{e['start'].strftime('%I:%M %p')} - {e['end'].strftime('%I:%M %p')}"
                    if ht and e.get("end") else
                    e["start"].strftime("%I:%M %p") if ht else None
                )

                if is_featured:
                    out += f'<div class="featured-card">\n  <div class="date">{ds}</div>\n'
                    if ts:  out += f'  <div class="time">🕛 {ts}</div>\n'
                    out += f'  <div class="summary">🫔 {ss}</div>\n'
                    if sl:  out += f'  <div class="location">📍 {sl}</div>\n'
                    out += '</div>\n'

                elif tg == "Birthdays":
                    out += (
                        f'<div class="event birthday"><div class="date">{ds}</div>'
                        f'<div class="summary">🎂 {ss}'
                        f'<img src="data:image/gif;base64,{gif_b64}" width="44" height="44">'
                        f'</div></div>\n'
                    )

                elif tg == "Anniversaries":
                    out += (
                        f'<div class="event anniversary"><div class="date">{ds}</div>'
                        f'<div class="summary">🏢 {ss}</div></div>\n'
                    )

                elif tg == "Holidays":
                    out += (
                        f'<div class="event holiday"><div class="date">{ds}</div>'
                        f'<div class="summary">🎉 {ss}</div></div>\n'
                    )

                else:
                    xc = " conference-highlight" if tg == "Conference" else ""
                    out += f'<div class="event{xc}">\n  <div class="date">{ds}</div>\n'
                    if ts:  out += f'  <div class="time">{ts}</div>\n'
                    out += f'  <div class="summary">{ss}</div>\n'
                    if sl:  out += f'  <div class="location">@ {sl}</div>\n'
                    out += '</div>\n'

    out += '</td></tr></table></td></tr></table></body></html>'
    return out

# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  E.inCLT Weekly Digest Builder")
    print("=" * 60)

    sow, eow = get_week_range()
    week_label = f"{sow.strftime('%B %d')} - {(eow - timedelta(days=1)).strftime('%B %d, %Y')}"
    print(f"\nWeek: {week_label}")

    # Load and parse ICS
    print(f"Reading: {ICS_PATH}")
    raw_events = load_ics(ICS_PATH)
    print(f"  {len(raw_events)} total events in file")

    # Group events
    grouped   = defaultdict(lambda: defaultdict(list))
    seen      = set()

    # Add any manually injected events first
    for inj in INJECTED_EVENTS:
        tg, sg = categorize(inj["summary"], inj.get("location"), "", "")
        grouped[tg][sg].append(inj)
        seen.add((inj["summary"].lower().strip(), inj["start"].date()))

    # Process ICS events
    for e in raw_events:
        # Skip known non-events
        if "sugarbowl2026" in e["uid"]:
            continue
        # Skip events outside this week
        if not (sow.date() <= e["start"].date() < eow.date()):
            continue
        # Skip canceled events
        if "[canceled]" in (e["summary"] or "").lower():
            continue

        s   = e["summary"]
        loc = e["location"]

        # Deduplicate
        key = (s.lower().strip(), e["start"].date())
        if key in seen:
            continue

        # Parse @ location from summary
        if s and "@" in s:
            before, after = s.split("@", 1)
            s, after = before.strip(), after.strip()
            if after:
                if not loc:
                    loc = after
                elif after.lower() not in loc.lower():
                    loc = f"{loc} {after}"

        tg, sg = categorize(s, loc, e["description"], e["categories"])

        event_data = {"summary": s, "start": e["start"], "location": loc}
        if e["end"]:
            event_data["end"] = e["end"]
        if sg and sg.lower() == "team meeting" and e["description"]:
            event_data["description"] = e["description"]

        grouped[tg][sg].append(event_data)
        seen.add(key)

    # Count events
    total = sum(len(evs) for subs in grouped.values() for evs in subs.values())
    print(f"  {total} events this week across {len(grouped)} sections")

    # Load assets
    img_b64 = load_b64(HEADER_IMG_PATH)
    gif_b64 = load_b64(BIRTHDAY_GIF)

    # Build HTML
    print("Building HTML...")
    body = build_html(grouped, sow, eow, gif_b64, img_b64)

    # Save
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(body)

    print(f"\n{'=' * 60}")
    print(f"  Done! Saved to: {OUTPUT_PATH}")
    print(f"  Week  : {week_label}")
    print(f"  Events: {total}")
    print(f"{'=' * 60}\n")

if __name__ == "__main__":
    main()
