#!/usr/bin/env python3
"""Generate dark & light, gridless GitHub contribution, activity, and statistics SVGs."""

import datetime
import json
import os
import sys
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape

USERNAME = os.environ.get("GITHUB_USERNAME", "Java-Mx")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
OUT_DIR = Path(__file__).resolve().parent.parent / "assets"

QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      totalCommitContributions
      restrictedContributionsCount
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
    pullRequests {
      totalCount
    }
    issues {
      totalCount
    }
    repositories(first: 100, ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC) {
      totalCount
      nodes {
        stargazerCount
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges {
            size
            node {
              name
              color
            }
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
        "elevated": "#161b22",
        "border": "#21262d",
        "elevated_border": "#30363d",
        "title": "#e6edf3",
        "body": "#8b949e",
        "muted": "#7d8590",
        "accent": "#58a6ff",
        "line": "#2f81f7",
        "area_top": "#2f81f7",
        "levels": ["#161b22", "#0c2d6b", "#1f6feb", "#388bfd", "#58a6ff"],
    },
    "light": {
        "bg": "#f6f8fa",
        "elevated": "#ffffff",
        "border": "#d0d7de",
        "elevated_border": "#d0d7de",
        "title": "#1f2328",
        "body": "#57606a",
        "muted": "#656d76",
        "accent": "#0969da",
        "line": "#0969da",
        "area_top": "#0969da",
        "levels": ["#ebedf0", "#b6e3ff", "#54aeff", "#0969da", "#0550ae"],
    },
}

MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def fetch_user_data(local_json: str | None = None) -> dict:
    if local_json:
        data = json.loads(Path(local_json).read_text(encoding="utf-8"))
        return data["data"]["user"]
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
    return data["data"]["user"]


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


def fmt_short_date(iso_str: str) -> str:
    dt = datetime.date.fromisoformat(iso_str)
    return f"{MONTH_NAMES[dt.month - 1]} {dt.day}"


def compute_streaks(days: list[dict]) -> tuple[int, str, int, str]:
    longest = 0
    longest_start = longest_end = ""
    run = 0
    run_start = ""
    for d in days:
        if d["contributionCount"] > 0:
            if run == 0:
                run_start = d["date"]
            run += 1
            if run >= longest:
                longest = run
                longest_start = run_start
                longest_end = d["date"]
        else:
            run = 0

    # Current streak (allowing today to be 0 if yesterday was active)
    curr = 0
    curr_start = curr_end = ""
    idx = len(days) - 1
    if idx >= 0 and days[idx]["contributionCount"] == 0:
        idx -= 1
    while idx >= 0 and days[idx]["contributionCount"] > 0:
        if curr == 0:
            curr_end = days[idx]["date"]
        curr_start = days[idx]["date"]
        curr += 1
        idx -= 1

    curr_range = (
        f"{fmt_short_date(curr_start)} – {fmt_short_date(curr_end)}"
        if curr > 1
        else (fmt_short_date(curr_start) if curr == 1 else "—")
    )
    longest_range = (
        f"{fmt_short_date(longest_start)} – {fmt_short_date(longest_end)}"
        if longest > 1
        else (fmt_short_date(longest_start) if longest == 1 else "—")
    )
    return curr, curr_range, longest, longest_range


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

    for wd, label in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        y = pad_top + wd * step + 9
        lines.append(
            f'  <text x="20" y="{y:.1f}" fill="{t["muted"]}" font-family="-apple-system, BlinkMacSystemFont, \'Segoe UI\', Helvetica, Arial, sans-serif" font-size="9.5">{label}</text>'
        )

    for wi, week in enumerate(weeks):
        for day in week["contributionDays"]:
            x = pad_left + wi * step
            y = pad_top + day["weekday"] * step
            lvl = level_for_count(day["contributionCount"], max_count)
            fill = t["levels"][lvl]
            lines.append(
                f'  <rect x="{x:.1f}" y="{y:.1f}" width="{cell}" height="{cell}" rx="2.5" fill="{fill}"><title>{day["date"]}: {day["contributionCount"]} contributions</title></rect>'
            )

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

    for x, y, day in pts:
        if day["contributionCount"] > 0:
            lines.append(
                f'  <circle cx="{x:.1f}" cy="{y:.1f}" r="3.2" fill="{t["accent"]}" stroke="{t["bg"]}" stroke-width="1.5"><title>{day["date"]}: {day["contributionCount"]} contributions</title></circle>'
            )

    tick_indices = sorted(set([0, len(pts) // 4, len(pts) // 2, (3 * len(pts)) // 4, len(pts) - 1]))
    for idx in tick_indices:
        x, _, day = pts[idx]
        lbl = fmt_short_date(day["date"])
        anchor = "start" if idx == 0 else ("end" if idx == len(pts) - 1 else "middle")
        lines.append(
            f'  <text x="{x:.1f}" y="{height - 12}" text-anchor="{anchor}" fill="{t["muted"]}" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="10">{lbl}</text>'
        )

    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def render_stats_dashboard(user: dict, theme_name: str) -> str:
    t = THEMES[theme_name]
    cc = user["contributionsCollection"]
    cal = cc["contributionCalendar"]
    all_days = [d for w in cal["weeks"] for d in w["contributionDays"]]

    commits_1y = cc["totalCommitContributions"]
    contrib_1y = cal["totalContributions"]
    prs = user["pullRequests"]["totalCount"]
    issues = user["issues"]["totalCount"]
    repos = user["repositories"]["totalCount"]
    stars = sum(n["stargazerCount"] for n in user["repositories"]["nodes"])

    curr_streak, curr_range, long_streak, long_range = compute_streaks(all_days)

    # Aggregate top languages across non-fork public repos
    lang_bytes: dict[str, int] = {}
    lang_colors: dict[str, str] = {}
    for node in user["repositories"]["nodes"]:
        for edge in node["languages"]["edges"]:
            name = edge["node"]["name"]
            lang_bytes[name] = lang_bytes.get(name, 0) + edge["size"]
            lang_colors[name] = edge["node"].get("color") or "#58a6ff"

    total_bytes = sum(lang_bytes.values()) or 1
    top_langs = sorted(lang_bytes.items(), key=lambda kv: kv[1], reverse=True)[:6]

    # Build stacked language bar (width = 248px)
    bar_x, bar_y, bar_w, bar_h = 631.5, 50, 248, 8
    bar_segs = []
    cur_x = bar_x
    for idx, (name, sz) in enumerate(top_langs):
        seg_w = (sz / total_bytes) * bar_w
        if idx == len(top_langs) - 1:
            seg_w = max(0.0, (bar_x + bar_w) - cur_x)
        col = lang_colors.get(name, t["accent"])
        bar_segs.append(f'    <rect x="{cur_x:.2f}" y="{bar_y}" width="{seg_w:.2f}" height="{bar_h}" fill="{col}"/>')
        cur_x += seg_w

    # Language legend (2 columns x 3 rows)
    lang_legend = []
    for idx, (name, sz) in enumerate(top_langs):
        col_idx = idx % 2
        row_idx = idx // 2
        lx = 635 + col_idx * 126
        ly = 84 + row_idx * 28
        pct = (sz / total_bytes) * 100
        col = lang_colors.get(name, t["accent"])
        lang_legend.append(f'  <circle cx="{lx}" cy="{ly - 4}" r="4" fill="{col}"/>')
        lang_legend.append(
            f'  <text x="{lx + 11}" y="{ly}" fill="{t["title"]}" font-family="-apple-system, BlinkMacSystemFont, \'Segoe UI\', Helvetica, Arial, sans-serif" font-size="11.5" font-weight="500">{escape(name)}</text>'
        )
        lang_legend.append(
            f'  <text x="{lx + 112}" y="{ly}" text-anchor="end" fill="{t["muted"]}" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="10.5">{pct:.1f}%</text>'
        )

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="900" height="172" viewBox="0 0 900 172" role="img" aria-label="{USERNAME} GitHub Statistics, Contribution Streak, and Top Languages">
  <defs>
    <clipPath id="lang-bar-{theme_name}">
      <rect x="{bar_x}" y="{bar_y}" width="{bar_w}" height="{bar_h}" rx="4"/>
    </clipPath>
  </defs>

  <!-- Card 1: Engineering Activity (288px) -->
  <rect x="0.5" y="0.5" width="288" height="171" rx="12" fill="{t["bg"]}" stroke="{t["border"]}" stroke-width="1"/>
  <text x="20" y="29" fill="{t["accent"]}" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="10.5" font-weight="600" letter-spacing="1.2">GITHUB ACTIVITY</text>

  <!-- 2x2 KPI tiles -->
  <rect x="18" y="44" width="121" height="52" rx="8" fill="{t["elevated"]}" stroke="{t["border"]}" stroke-width="1"/>
  <text x="30" y="69" fill="{t["title"]}" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="20" font-weight="700">{commits_1y}</text>
  <text x="30" y="86" fill="{t["muted"]}" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif" font-size="10.5">Commits (1Y)</text>

  <rect x="149" y="44" width="121" height="52" rx="8" fill="{t["elevated"]}" stroke="{t["border"]}" stroke-width="1"/>
  <text x="161" y="69" fill="{t["title"]}" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="20" font-weight="700">{prs}</text>
  <text x="161" y="86" fill="{t["muted"]}" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif" font-size="10.5">Pull Requests</text>

  <rect x="18" y="106" width="121" height="50" rx="8" fill="{t["elevated"]}" stroke="{t["border"]}" stroke-width="1"/>
  <text x="30" y="130" fill="{t["title"]}" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="20" font-weight="700">{repos}</text>
  <text x="30" y="147" fill="{t["muted"]}" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif" font-size="10.5">Public Repos</text>

  <rect x="149" y="106" width="121" height="50" rx="8" fill="{t["elevated"]}" stroke="{t["border"]}" stroke-width="1"/>
  <text x="161" y="130" fill="{t["title"]}" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="20" font-weight="700">{stars + issues}</text>
  <text x="161" y="147" fill="{t["muted"]}" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif" font-size="10.5">Stars &amp; Issues</text>

  <!-- Card 2: Contribution Streak (288px) -->
  <rect x="306" y="0.5" width="288" height="171" rx="12" fill="{t["bg"]}" stroke="{t["border"]}" stroke-width="1"/>
  <text x="326" y="29" fill="{t["accent"]}" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="10.5" font-weight="600" letter-spacing="1.2">CONSISTENCY &amp; STREAK</text>

  <!-- Center Current Streak Ring -->
  <circle cx="450" cy="78" r="28" fill="{t["elevated"]}" stroke="{t["line"]}" stroke-width="2.5"/>
  <text x="450" y="85" text-anchor="middle" fill="{t["title"]}" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="22" font-weight="700">{curr_streak}</text>
  <text x="450" y="124" text-anchor="middle" fill="{t["accent"]}" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif" font-size="11.5" font-weight="600">Current Streak</text>
  <text x="450" y="141" text-anchor="middle" fill="{t["muted"]}" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="9.5">{escape(curr_range)}</text>

  <!-- Left: 1Y Total -->
  <text x="358" y="84" text-anchor="middle" fill="{t["title"]}" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="20" font-weight="700">{contrib_1y}</text>
  <text x="358" y="104" text-anchor="middle" fill="{t["muted"]}" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif" font-size="10.5">1Y Total</text>
  <text x="358" y="120" text-anchor="middle" fill="{t["muted"]}" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="9.5">Public</text>

  <!-- Right: Longest Streak -->
  <text x="542" y="84" text-anchor="middle" fill="{t["title"]}" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="20" font-weight="700">{long_streak}d</text>
  <text x="542" y="104" text-anchor="middle" fill="{t["muted"]}" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif" font-size="10.5">Longest</text>
  <text x="542" y="120" text-anchor="middle" fill="{t["muted"]}" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="9.5">{escape(long_range)}</text>

  <!-- Card 3: Top Languages (288px) -->
  <rect x="611.5" y="0.5" width="288" height="171" rx="12" fill="{t["bg"]}" stroke="{t["border"]}" stroke-width="1"/>
  <text x="631.5" y="29" fill="{t["accent"]}" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="10.5" font-weight="600" letter-spacing="1.2">TOP LANGUAGES</text>

  <g clip-path="url(#lang-bar-{theme_name})">
    <rect x="{bar_x}" y="{bar_y}" width="{bar_w}" height="{bar_h}" fill="{t["elevated"]}"/>
{chr(10).join(bar_segs)}
  </g>

{chr(10).join(lang_legend)}
</svg>
'''


def main() -> None:
    local_json = sys.argv[1] if len(sys.argv) > 1 else None
    user = fetch_user_data(local_json)
    calendar = user["contributionsCollection"]["contributionCalendar"]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for theme in ("dark", "light"):
        (OUT_DIR / f"contrib-{theme}.svg").write_text(render_heatmap(calendar, theme), encoding="utf-8")
        (OUT_DIR / f"activity-{theme}.svg").write_text(render_activity_curve(calendar, theme), encoding="utf-8")
        (OUT_DIR / f"stats-{theme}.svg").write_text(render_stats_dashboard(user, theme), encoding="utf-8")
    print(f"Generated dark/light contribution, activity, and stats SVGs for @{USERNAME} ({calendar['totalContributions']} contributions).")


if __name__ == "__main__":
    main()
