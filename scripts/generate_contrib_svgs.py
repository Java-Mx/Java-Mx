#!/usr/bin/env python3
"""Generate dark & light, gridless GitHub contribution heatmap and 30-day activity SVGs."""

import datetime
import json
import os
import sys
import urllib.request
from pathlib import Path

USERNAME = os.environ.get("GITHUB_USERNAME", "Java-Mx")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
OUT_DIR = Path(__file__).resolve().parent.parent / "assets"

QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays {
            date
            contributionCount
            weekday
          }
        }
      }
    }
  }
}
"""

THEMES = {
    "dark": {
        "bg": "#0d1117",
        "border": "#21262d",
        "title": "#e6edf3",
        "muted": "#7d8590",
        "accent": "#58a6ff",
        "line": "#2f81f7",
        "area_top": "#2f81f7",
        "levels": ["#161b22", "#0c2d6b", "#1f6feb", "#388bfd", "#58a6ff"],
    },
    "light": {
        "bg": "#f6f8fa",
        "border": "#d0d7de",
        "title": "#1f2328",
        "muted": "#656d76",
        "accent": "#0969da",
        "line": "#0969da",
        "area_top": "#0969da",
        "levels": ["#ebedf0", "#b6e3ff", "#54aeff", "#0969da", "#0550ae"],
    },
}

MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def fetch_calendar(local_json: str | None = None) -> dict:
    if local_json:
        data = json.loads(Path(local_json).read_text(encoding="utf-8"))
        return data["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    if not TOKEN:
        raise RuntimeError("GITHUB_TOKEN is required when no local JSON path is passed.")
    payload = json.dumps({"query": QUERY, "variables": {"login": USERNAME}}).encode("utf-8")
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=payload,
        headers={
            "Authorization": f"bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "Java-Mx-Profile-Generator",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["data"]["user"]["contributionsCollection"]["contributionCalendar"]


def level_for_count(count: int, max_count: int) -> int:
    if count <= 0:
        return 0
    if max_count <= 4:
        return min(count, 4)
    ratio = count / max_count
    if ratio <= 0.25:
        return 1
    if ratio <= 0.50:
        return 2
    if ratio <= 0.75:
        return 3
    return 4


def render_heatmap(calendar: dict, theme_name: str) -> str:
    t = THEMES[theme_name]
    weeks = calendar["weeks"]
    total = calendar["totalContributions"]

    all_days = [d for w in weeks for d in w["contributionDays"]]
    max_count = max((d["contributionCount"] for d in all_days), default=1)

    cell = 11
    gap = 3.5
    step = cell + gap
    pad_left = 46
    pad_top = 56
    pad_right = 24
    pad_bottom = 34

    width = int(pad_left + len(weeks) * step + pad_right)
    height = int(pad_top + 7 * step + pad_bottom)

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{USERNAME} GitHub contribution calendar">',
        f'  <rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="12" fill="{t["bg"]}" stroke="{t["border"]}" stroke-width="1"/>',
        f'  <text x="24" y="28" fill="{t["title"]}" font-family="-apple-system, BlinkMacSystemFont, \'Segoe UI\', Helvetica, Arial, sans-serif" font-size="13" font-weight="600">{total} public contributions in the last year</text>',
        f'  <text x="{width - 24}" y="28" text-anchor="end" fill="{t["muted"]}" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="11">@{USERNAME}</text>',
    ]

    # Month labels (skip overlapping first label)
    seen_month = None
    last_label_x = -999
    for wi, week in enumerate(weeks):
        if not week["contributionDays"]:
            continue
        first_date = datetime.date.fromisoformat(week["contributionDays"][0]["date"])
        if first_date.month != seen_month:
            x = pad_left + wi * step
            if x - last_label_x >= 34:
                lines.append(
                    f'  <text x="{x:.1f}" y="{pad_top - 10}" fill="{t["muted"]}" font-family="-apple-system, BlinkMacSystemFont, \'Segoe UI\', Helvetica, Arial, sans-serif" font-size="10">{MONTH_NAMES[first_date.month - 1]}</text>'
                )
                last_label_x = x
            seen_month = first_date.month

    # Weekday labels
    for wd, label in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        y = pad_top + wd * step + 9
        lines.append(
            f'  <text x="20" y="{y:.1f}" fill="{t["muted"]}" font-family="-apple-system, BlinkMacSystemFont, \'Segoe UI\', Helvetica, Arial, sans-serif" font-size="9.5">{label}</text>'
        )

    # Heatmap cells (rounded, dark empty cells, zero grid lines)
    for wi, week in enumerate(weeks):
        for day in week["contributionDays"]:
            x = pad_left + wi * step
            y = pad_top + day["weekday"] * step
            lvl = level_for_count(day["contributionCount"], max_count)
            fill = t["levels"][lvl]
            lines.append(
                f'  <rect x="{x:.1f}" y="{y:.1f}" width="{cell}" height="{cell}" rx="2.5" fill="{fill}"><title>{day["date"]}: {day["contributionCount"]} contributions</title></rect>'
            )

    # Legend
    legend_y = height - 16
    legend_x = width - 134
    lines.append(
        f'  <text x="{legend_x - 8}" y="{legend_y + 8}" text-anchor="end" fill="{t["muted"]}" font-family="-apple-system, BlinkMacSystemFont, \'Segoe UI\', Helvetica, Arial, sans-serif" font-size="9.5">Less</text>'
    )
    for i, col in enumerate(t["levels"]):
        lx = legend_x + i * 14
        lines.append(f'  <rect x="{lx}" y="{legend_y - 1}" width="10" height="10" rx="2" fill="{col}"/>')
    lines.append(
        f'  <text x="{legend_x + 5 * 14 + 4}" y="{legend_y + 8}" fill="{t["muted"]}" font-family="-apple-system, BlinkMacSystemFont, \'Segoe UI\', Helvetica, Arial, sans-serif" font-size="9.5">More</text>'
    )

    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def render_activity_curve(calendar: dict, theme_name: str) -> str:
    t = THEMES[theme_name]
    all_days = [d for w in calendar["weeks"] for d in w["contributionDays"]]
    recent = all_days[-30:] if len(all_days) >= 30 else all_days

    width = 840
    height = 190
    pad_left = 36
    pad_right = 28
    pad_top = 48
    pad_bottom = 34
    chart_w = width - pad_left - pad_right
    chart_h = height - pad_top - pad_bottom

    max_val = max((d["contributionCount"] for d in recent), default=1)
    max_val = max(max_val, 1)

    pts = []
    n = max(len(recent) - 1, 1)
    for i, day in enumerate(recent):
        x = pad_left + (i / n) * chart_w
        y = pad_top + chart_h - (day["contributionCount"] / max_val) * chart_h
        pts.append((x, y, day))

    # Smooth monotone-ish cubic Bezier path (zero grid lines)
    def smooth_path(points):
        if not points:
            return ""
        d = [f"M {points[0][0]:.1f} {points[0][1]:.1f}"]
        for i in range(len(points) - 1):
            x0, y0, _ = points[i]
            x1, y1, _ = points[i + 1]
            cx = (x0 + x1) / 2.0
            d.append(f"C {cx:.1f} {y0:.1f}, {cx:.1f} {y1:.1f}, {x1:.1f} {y1:.1f}")
        return " ".join(d)

    line_d = smooth_path(pts)
    base_y = pad_top + chart_h
    area_d = f"{line_d} L {pts[-1][0]:.1f} {base_y:.1f} L {pts[0][0]:.1f} {base_y:.1f} Z" if pts else ""

    recent_total = sum(d["contributionCount"] for d in recent)

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{USERNAME} 30-day contribution activity curve">',
        "  <defs>",
        f'    <linearGradient id="area-grad-{theme_name}" x1="0" y1="0" x2="0" y2="1">',
        f'      <stop offset="0%" stop-color="{t["area_top"]}" stop-opacity="0.28"/>',
        f'      <stop offset="100%" stop-color="{t["area_top"]}" stop-opacity="0.0"/>',
        "    </linearGradient>",
        "  </defs>",
        f'  <rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="12" fill="{t["bg"]}" stroke="{t["border"]}" stroke-width="1"/>',
        f'  <text x="24" y="28" fill="{t["title"]}" font-family="-apple-system, BlinkMacSystemFont, \'Segoe UI\', Helvetica, Arial, sans-serif" font-size="13" font-weight="600">30-Day Contribution Trend</text>',
        f'  <text x="{width - 24}" y="28" text-anchor="end" fill="{t["muted"]}" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="11">{recent_total} commits &amp; events · peak {max_val}/day</text>',
        f'  <path d="{area_d}" fill="url(#area-grad-{theme_name})"/>',
        f'  <path d="{line_d}" fill="none" stroke="{t["line"]}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>',
    ]

    # Subtle dots on active days only
    for x, y, day in pts:
        if day["contributionCount"] > 0:
            lines.append(
                f'  <circle cx="{x:.1f}" cy="{y:.1f}" r="3.2" fill="{t["accent"]}" stroke="{t["bg"]}" stroke-width="1.5"><title>{day["date"]}: {day["contributionCount"]} contributions</title></circle>'
            )

    # Sparse date ticks (start, mid, end — zero grid lines)
    tick_indices = sorted(set([0, len(pts) // 4, len(pts) // 2, (3 * len(pts)) // 4, len(pts) - 1]))
    for idx in tick_indices:
        x, _, day = pts[idx]
        dt = datetime.date.fromisoformat(day["date"])
        lbl = f"{MONTH_NAMES[dt.month - 1]} {dt.day}"
        anchor = "start" if idx == 0 else ("end" if idx == len(pts) - 1 else "middle")
        lines.append(
            f'  <text x="{x:.1f}" y="{height - 12}" text-anchor="{anchor}" fill="{t["muted"]}" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="10">{lbl}</text>'
        )

    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def main() -> None:
    local_json = sys.argv[1] if len(sys.argv) > 1 else None
    calendar = fetch_calendar(local_json)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for theme in ("dark", "light"):
        (OUT_DIR / f"contrib-{theme}.svg").write_text(render_heatmap(calendar, theme), encoding="utf-8")
        (OUT_DIR / f"activity-{theme}.svg").write_text(render_activity_curve(calendar, theme), encoding="utf-8")
    print(f"Generated dark/light contribution SVGs for @{USERNAME} ({calendar['totalContributions']} contributions).")


if __name__ == "__main__":
    main()
