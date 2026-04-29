"""
digest_builder.py - E.inCLT Weekly Digest HTML Generator
Reads directly from Google Calendar API — no .ics export needed.

Usage:
    python digest_builder.py

Configuration:
    Update the CONFIG section below before running.
"""

from datetime import datetime, timedelta, timezone
from collections import defaultdict
import base64
import html
import os
import re

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# ── CONFIG ────────────────────────────────────────────────────────────────────

HEADER_IMG_PATH = "header_image.png"
BIRTHDAY_GIF    = "birthday_icon.gif"
OUTPUT_PATH     = "weekly_events.html"
FIXED_WIDTH     = 800

# Set to the Monday of the week you want, or None for auto (current week)
WEEK_START_OVERRIDE = None  # e.g. datetime(2026, 5, 4)

# Map your exact Google Calendar names → digest category
# Run once with SHOW_CALENDAR_NAMES = True below to see your exact names
CALENDARS = {
    "Camp North End (Sandbox)":      "Camp North End Events",
    "Birthdays (Experient)":         "Birthdays",
    "Work Anniversaries (Experient)":"Anniversaries",
    # Add Virto calendar name here when ready:
    # "Virto Office Activity":       "CLT Office Activity",
}

# Set to True on first run to print all your calendar names, then set back to False
SHOW_CALENDAR_NAMES = False

# Optional: path to a Virto iCal export for office activity events.
# Each week, click "Save as iCal" in Virto and save the file here.
# Set to None to skip Virto events.
VIRTO_ICS_PATH = None  # e.g. "virto_office.ics"

SCOPES = ["https://www.googleapis.com/auth/calendar"]  # matches token.json from camp_nc_sync

# Manually injected events — same as before
INJECTED_EVENTS = [
    # {"summary": "...", "start": datetime(2026, 5, 4, 18, 0),
    #  "end": datetime(2026, 5, 4, 21, 0), "location": "..."},
]

# Featured event keyword — any event summary containing this gets the featured section
FEATURED_KEYWORD = None  # e.g. "empanada"

KEYWORD_MAP = {
    "Free Range Bar": "Social",
    "Ice Skating":    "Seasonal Activities",
}

NAMED_HOLIDAYS = {
    "new year's day", "valentine's day", "president's day", "memorial day",
    "independence day", "labor day", "halloween", "thanksgiving day",
    "black friday", "christmas eve", "christmas day",
    "st. patrick's day", "saint patrick's day", "tax day",
    "daylight saving time starts", "daylight savings time starts",
    "good friday", "easter sunday", "easter monday",
}

# ── ICS PARSER (for Virto office calendar) ───────────────────────────────────

def parse_dt(val):
    val = val.strip()
    if val.endswith("Z"):
        val = val[:-1]
    try:
        return datetime.strptime(val[:15], "%Y%m%dT%H%M%S") if "T" in val \
               else datetime.combine(datetime.strptime(val[:8], "%Y%m%d").date(), datetime.min.time())
    except Exception:
        return None

def load_virto_ics(path, sow, eow):
    """Parse a Virto iCal export and return events in the same format as load_from_gcal."""
    if not path or not os.path.exists(path):
        return []

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
        if not start or not (sow.date() <= start.date() < eow.date()):
            continue

        loc = gf("LOCATION").strip() or None
        if loc:
            loc = loc.replace("\\,", ",")

        events.append({
            "uid":         gf("UID"),
            "summary":     gf("SUMMARY"),
            "location":    loc,
            "description": gf("DESCRIPTION"),
            "categories":  "CLT Office Activity",
            "start":       start,
            "end":         parse_dt(me.group(1)) if me else None,
        })

    print(f"  📅 Virto iCal ({path}): {len(events)} events")
    return events


# ── GOOGLE CALENDAR AUTH ──────────────────────────────────────────────────────

def get_cal_service():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow  = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
            with open("token.json", "w") as f:
                f.write(creds.to_json())
    return build("calendar", "v3", credentials=creds)

# ── GOOGLE CALENDAR READER ────────────────────────────────────────────────────

def load_from_gcal(sow, eow):
    """
    Pull events from each calendar in CALENDARS for the given week.
    Returns a list of event dicts matching the format the rest of the script expects.
    """
    service = get_cal_service()

    # List all calendars
    cal_list = service.calendarList().list().execute().get("items", [])

    if SHOW_CALENDAR_NAMES:
        print("\nYour Google Calendars:")
        for c in cal_list:
            print(f"  '{c['summary']}' (id: {c['id']})")
        print()

    # Build name → id map
    cal_map = {c["summary"]: c["id"] for c in cal_list}

    # RFC3339 time bounds for the week
    tz_utc  = timezone.utc
    time_min = datetime.combine(sow.date(), datetime.min.time()).replace(tzinfo=tz_utc).isoformat()
    time_max = datetime.combine(eow.date(), datetime.min.time()).replace(tzinfo=tz_utc).isoformat()

    events = []
    for cal_name, digest_category in CALENDARS.items():
        cal_id = cal_map.get(cal_name)
        if not cal_id:
            print(f"  ⚠️  Calendar not found: '{cal_name}' — check name in CALENDARS config")
            continue

        result = service.events().list(
            calendarId=cal_id,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime",
        ).execute()

        for item in result.get("items", []):
            summary = (item.get("summary") or "").strip()
            if not summary:
                continue

            # Parse start/end — handle all-day (date) vs timed (dateTime)
            start_raw = item["start"].get("dateTime") or item["start"].get("date")
            end_raw   = item["end"].get("dateTime")   or item["end"].get("date")   if "end" in item else None

            start = _parse_gcal_dt(start_raw)
            end   = _parse_gcal_dt(end_raw) if end_raw else None

            if not start:
                continue

            location = (item.get("location") or "").strip() or None
            if location:
                location = location.replace("\\,", ",")

            events.append({
                "uid":          item.get("id", ""),
                "summary":      summary,
                "location":     location,
                "description":  (item.get("description") or "").strip(),
                "categories":   digest_category,   # use the mapped category directly
                "start":        start,
                "end":          end,
                "_cal_name":    cal_name,           # keep for debugging
            })

        print(f"  📅 {cal_name}: {len(result.get('items', []))} events")

    return events

def _parse_gcal_dt(val):
    """Parse a Google Calendar dateTime or date string into a naive datetime."""
    if not val:
        return None
    val = val.strip()
    # All-day: "2026-05-04"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", val):
        return datetime.strptime(val, "%Y-%m-%d")
    # Timed with offset: "2026-05-04T18:00:00-04:00" or "2026-05-04T18:00:00Z"
    try:
        # Strip timezone for naive datetime (keeps local display time)
        clean = re.sub(r"(Z|[+-]\d{2}:\d{2})$", "", val)
        return datetime.strptime(clean[:19], "%Y-%m-%dT%H:%M:%S")
    except Exception:
        return None

# ── ASSET LOADER ──────────────────────────────────────────────────────────────

def load_b64(path):
    if not os.path.exists(path):
        print(f"WARNING: Asset not found: {path}")
        return ""
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

# ── DATE HELPERS ──────────────────────────────────────────────────────────────

def get_week_range():
    if WEEK_START_OVERRIDE:
        sow = WEEK_START_OVERRIDE
    else:
        today = datetime.combine(datetime.today().date(), datetime.min.time())
        sow   = today - timedelta(days=today.weekday())
    return sow, sow + timedelta(days=7)

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

    # If we already have a mapped category from the calendar name, respect it
    # but still allow overrides for birthdays/holidays by keyword
    if "birthday" in lower:
        return "Birthdays", None
    if "anniversary" in lower:
        return "Anniversaries", None
    if is_holiday(summary, description):
        return "Holidays", None

    # Use the calendar-mapped category if available
    if categories and categories not in ("", None):
        if categories == "Birthdays":
            return "Birthdays", None
        if categories == "Anniversaries":
            return "Anniversaries", None
        if categories == "Holidays":
            return "Holidays", None
        if categories == "CLT Office Activity":
            return "CLT Office Activity", None
        if categories == "Camp North End Events":
            pass  # fall through to keyword matching below

    if FEATURED_KEYWORD and FEATURED_KEYWORD.lower() in lower:
        return "🫔 Featured Event", None

    if categories and categories.lower() == "conference":
        return "Conference", None
    if categories:
        matched = next(
            (g for k, g in KEYWORD_MAP.items()
             if k.lower() in lower or k.lower() in loc),
            None
        )
        return (matched or categories), None

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
        f'<img src="data:image/png;base64,{img_b64}" style="display:block;margin:0 auto 20px auto;max-width:100%;">\n'
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
            "background-color:#b5451b;color:#fff;padding:12px 14px;border-radius:6px;"
            "font-size:1.35em;text-align:center;letter-spacing:1px;margin:0 0 8px 0"
            if is_featured else
            "background-color:#004085;color:#fff;padding:10px;border-radius:4px;"
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

    # Pull from Google Calendar
    print("\nFetching from Google Calendar...")
    raw_events = load_from_gcal(sow, eow)

    # Optionally merge Virto office calendar from iCal export
    if VIRTO_ICS_PATH:
        virto_events = load_virto_ics(VIRTO_ICS_PATH, sow, eow)
        raw_events.extend(virto_events)

    print(f"  {len(raw_events)} total events fetched")

    # Group events
    grouped = defaultdict(lambda: defaultdict(list))
    seen    = set()

    # Manually injected events first
    for inj in INJECTED_EVENTS:
        tg, sg = categorize(inj["summary"], inj.get("location"), "", "")
        grouped[tg][sg].append(inj)
        seen.add((inj["summary"].lower().strip(), inj["start"].date()))

    # Process fetched events
    for e in raw_events:
        if not (sow.date() <= e["start"].date() < eow.date()):
            continue
        if "[canceled]" in (e["summary"] or "").lower():
            continue

        s   = e["summary"]
        loc = e["location"]

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

    total = sum(len(evs) for subs in grouped.values() for evs in subs.values())
    print(f"\n  {total} events this week across {len(grouped)} sections")

    # Load assets
    img_b64 = load_b64(HEADER_IMG_PATH)
    gif_b64 = load_b64(BIRTHDAY_GIF)

    # Build and save HTML
    print("Building HTML...")
    body = build_html(grouped, sow, eow, gif_b64, img_b64)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(body)

    print(f"\n{'=' * 60}")
    print(f"  Done! Saved to: {OUTPUT_PATH}")
    print(f"  Week  : {week_label}")
    print(f"  Events: {total}")
    print(f"{'=' * 60}\n")

if __name__ == "__main__":
    main()
