#!/usr/bin/env python3
"""Generate unified dark & light, gridless GitHub heatmap, 30-day trend, and metrics SVGs."""

import datetime
import hashlib
import json
import os
import re
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
        "divider": "#21262d",
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
        "divider": "#d8dee4",
        "title": "#1f2328",
        "body": "#57606a",
        "muted": "#656d76",
        "accent": "#0969da",
        "line": "#0969da",
        "area_top": "#0969da",
        "levels": ["#ebedf0", "#b6e3ff", "#54aeff", "#0969da", "#0550ae"],
    },
}

FONT_SANS = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"
FONT_MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
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

    width = 900
    cell = 11.8
    gap = 3.8
    step = cell + gap
    grid_w = len(weeks) * step - gap
    pad_left = (width - grid_w) / 2.0 + 12
    pad_top = 60
    height = 194

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{USERNAME} GitHub contribution calendar">',
        f'  <rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="12" fill="{t["bg"]}" stroke="{t["border"]}" stroke-width="1"/>',
        f'  <text x="26" y="30" fill="{t["muted"]}" font-family="{FONT_MONO}" font-size="11" font-weight="500">Contributions</text>',
        f'  <text x="{width - 26}" y="30" text-anchor="end" fill="{t["body"]}" font-family="{FONT_MONO}" font-size="11">{total} public in the last year</text>',
    ]

    seen_month = None
    last_label_x = -999
    for wi, week in enumerate(weeks):
        if not week["contributionDays"]:
            continue
        first_date = datetime.date.fromisoformat(week["contributionDays"][0]["date"])
        if first_date.month != seen_month:
            x = pad_left + wi * step
            if x - last_label_x >= 36:
                lines.append(
                    f'  <text x="{x:.1f}" y="{pad_top - 10}" fill="{t["muted"]}" font-family="{FONT_MONO}" font-size="9.5">{MONTH_NAMES[first_date.month - 1]}</text>'
                )
                last_label_x = x
            seen_month = first_date.month

    for wd, label in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        y = pad_top + wd * step + 9.5
        lines.append(
            f'  <text x="26" y="{y:.1f}" fill="{t["muted"]}" font-family="{FONT_MONO}" font-size="9.5">{label}</text>'
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
    legend_x = width - 138
    lines.append(
        f'  <text x="{legend_x - 8}" y="{legend_y + 8}" text-anchor="end" fill="{t["muted"]}" font-family="{FONT_MONO}" font-size="9.5">Less</text>'
    )
    for i, col in enumerate(t["levels"]):
        lx = legend_x + i * 14
        lines.append(f'  <rect x="{lx}" y="{legend_y - 1}" width="10" height="10" rx="2" fill="{col}"/>')
    lines.append(
        f'  <text x="{legend_x + 5 * 14 + 4}" y="{legend_y + 8}" fill="{t["muted"]}" font-family="{FONT_MONO}" font-size="9.5">More</text>'
    )

    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def render_activity_curve(calendar: dict, theme_name: str) -> str:
    t = THEMES[theme_name]
    all_days = [d for w in calendar["weeks"] for d in w["contributionDays"]]
    recent = all_days[-30:] if len(all_days) >= 30 else all_days

    width = 900
    height = 178
    pad_left = 30
    pad_right = 30
    pad_top = 48
    pad_bottom = 32
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
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{USERNAME} 30-day contribution trend">',
        "  <defs>",
        f'    <linearGradient id="trend-grad-{theme_name}" x1="0" y1="0" x2="0" y2="1">',
        f'      <stop offset="0%" stop-color="{t["area_top"]}" stop-opacity="0.22"/>',
        f'      <stop offset="100%" stop-color="{t["area_top"]}" stop-opacity="0.0"/>',
        "    </linearGradient>",
        "  </defs>",
        f'  <rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="12" fill="{t["bg"]}" stroke="{t["border"]}" stroke-width="1"/>',
        f'  <text x="26" y="30" fill="{t["muted"]}" font-family="{FONT_MONO}" font-size="11" font-weight="500">Last 30 days</text>',
        f'  <text x="{width - 26}" y="30" text-anchor="end" fill="{t["body"]}" font-family="{FONT_MONO}" font-size="11">{recent_total} events · peak {max_val}/day</text>',
        f'  <path d="{area_d}" fill="url(#trend-grad-{theme_name})"/>',
        f'  <path d="{line_d}" fill="none" stroke="{t["line"]}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
    ]

    for x, y, day in pts:
        if day["contributionCount"] > 0:
            lines.append(
                f'  <circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{t["accent"]}" stroke="{t["bg"]}" stroke-width="1.5"><title>{day["date"]}: {day["contributionCount"]} contributions</title></circle>'
            )

    tick_indices = sorted(set([0, len(pts) // 4, len(pts) // 2, (3 * len(pts)) // 4, len(pts) - 1]))
    for idx in tick_indices:
        x, _, day = pts[idx]
        lbl = fmt_short_date(day["date"])
        anchor = "start" if idx == 0 else ("end" if idx == len(pts) - 1 else "middle")
        lines.append(
            f'  <text x="{x:.1f}" y="{height - 12}" text-anchor="{anchor}" fill="{t["muted"]}" font-family="{FONT_MONO}" font-size="10">{lbl}</text>'
        )

    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def render_metrics(user: dict, theme_name: str) -> str:
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

    lang_bytes: dict[str, int] = {}
    lang_colors: dict[str, str] = {}
    for node in user["repositories"]["nodes"]:
        for edge in node["languages"]["edges"]:
            name = edge["node"]["name"]
            lang_bytes[name] = lang_bytes.get(name, 0) + edge["size"]
            lang_colors[name] = edge["node"].get("color") or "#58a6ff"

    total_bytes = sum(lang_bytes.values()) or 1
    top_langs = sorted(lang_bytes.items(), key=lambda kv: kv[1], reverse=True)[:6]

    bar_x, bar_y, bar_w, bar_h = 632.5, 48, 245, 7
    bar_segs = []
    cur_x = bar_x
    for idx, (name, sz) in enumerate(top_langs):
        seg_w = (sz / total_bytes) * bar_w
        if idx == len(top_langs) - 1:
            seg_w = max(0.0, (bar_x + bar_w) - cur_x)
        col = lang_colors.get(name, t["accent"])
        bar_segs.append(f'    <rect x="{cur_x:.2f}" y="{bar_y}" width="{seg_w:.2f}" height="{bar_h}" fill="{col}"/>')
        cur_x += seg_w

    lang_legend = []
    for idx, (name, sz) in enumerate(top_langs):
        col_idx = idx % 2
        row_idx = idx // 2
        lx = 636 + col_idx * 124
        ly = 82 + row_idx * 30
        pct = (sz / total_bytes) * 100
        col = lang_colors.get(name, t["accent"])
        lang_legend.append(f'  <circle cx="{lx}" cy="{ly - 4}" r="3.5" fill="{col}"/>')
        lang_legend.append(
            f'  <text x="{lx + 10}" y="{ly}" fill="{t["title"]}" font-family="{FONT_SANS}" font-size="11.5" font-weight="500">{escape(name)}</text>'
        )
        lang_legend.append(
            f'  <text x="{lx + 112}" y="{ly}" text-anchor="end" fill="{t["muted"]}" font-family="{FONT_MONO}" font-size="10.5">{pct:.1f}%</text>'
        )

    act_rows = [
        ("Commits (1Y)", str(commits_1y)),
        ("Pull Requests", str(prs)),
        ("Public Repos", str(repos)),
        ("Stars & Issues", str(stars + issues)),
    ]
    act_svg = []
    for i, (lbl, val) in enumerate(act_rows):
        y = 58 + i * 32
        act_svg.append(f'  <text x="22.5" y="{y}" fill="{t["body"]}" font-family="{FONT_SANS}" font-size="12.5">{escape(lbl)}</text>')
        act_svg.append(f'  <text x="267.5" y="{y}" text-anchor="end" fill="{t["title"]}" font-family="{FONT_MONO}" font-size="13" font-weight="600">{escape(val)}</text>')
        if i < len(act_rows) - 1:
            act_svg.append(f'  <line x1="22.5" y1="{y + 11}" x2="267.5" y2="{y + 11}" stroke="{t["divider"]}" stroke-width="1"/>')

    streak_rows = [
        ("Current Streak", f"{curr_streak}d", curr_range, True),
        ("Longest Streak", f"{long_streak}d", long_range, False),
        ("Public (1Y)", str(contrib_1y), "last 12 months", False),
    ]
    streak_svg = []
    for i, (lbl, val, sub, is_acc) in enumerate(streak_rows):
        y = 60 + i * 42
        vc = t["accent"] if is_acc else t["title"]
        streak_svg.append(f'  <text x="327.5" y="{y}" fill="{t["title"]}" font-family="{FONT_SANS}" font-size="12.5" font-weight="500">{escape(lbl)}</text>')
        streak_svg.append(f'  <text x="327.5" y="{y + 14}" fill="{t["muted"]}" font-family="{FONT_MONO}" font-size="10">{escape(sub)}</text>')
        streak_svg.append(f'  <text x="572.5" y="{y + 6}" text-anchor="end" fill="{vc}" font-family="{FONT_MONO}" font-size="16" font-weight="600">{escape(val)}</text>')
        if i < len(streak_rows) - 1:
            streak_svg.append(f'  <line x1="327.5" y1="{y + 24}" x2="572.5" y2="{y + 24}" stroke="{t["divider"]}" stroke-width="1"/>')

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="900" height="176" viewBox="0 0 900 176" role="img" aria-label="{USERNAME} GitHub Activity, Streak, and Languages">
  <defs>
    <clipPath id="lang-bar-{theme_name}">
      <rect x="{bar_x}" y="{bar_y}" width="{bar_w}" height="{bar_h}" rx="3.5"/>
    </clipPath>
  </defs>

  <!-- Card 1: Activity -->
  <rect x="0.5" y="0.5" width="289" height="175" rx="12" fill="{t["bg"]}" stroke="{t["border"]}" stroke-width="1"/>
  <text x="22.5" y="29" fill="{t["muted"]}" font-family="{FONT_MONO}" font-size="11" font-weight="500">Activity</text>
{chr(10).join(act_svg)}

  <!-- Card 2: Streak -->
  <rect x="305.5" y="0.5" width="289" height="175" rx="12" fill="{t["bg"]}" stroke="{t["border"]}" stroke-width="1"/>
  <text x="327.5" y="29" fill="{t["muted"]}" font-family="{FONT_MONO}" font-size="11" font-weight="500">Streak</text>
{chr(10).join(streak_svg)}

  <!-- Card 3: Languages -->
  <rect x="610.5" y="0.5" width="289" height="175" rx="12" fill="{t["bg"]}" stroke="{t["border"]}" stroke-width="1"/>
  <text x="632.5" y="29" fill="{t["muted"]}" font-family="{FONT_MONO}" font-size="11" font-weight="500">Languages</text>
  <g clip-path="url(#lang-bar-{theme_name})">
    <rect x="{bar_x}" y="{bar_y}" width="{bar_w}" height="{bar_h}" fill="{t["elevated"]}"/>
{chr(10).join(bar_segs)}
  </g>
{chr(10).join(lang_legend)}
</svg>
'''


def update_readme_cache_buster(content_hash: str) -> None:
    readme_path = OUT_DIR.parent / "README.md"
    if not readme_path.exists():
        return
    text = readme_path.read_text(encoding="utf-8")
    updated = re.sub(
        r"(https://raw\.githubusercontent\.com/Java-Mx/Java-Mx/main/assets/(?:heatmap|trend|metrics)-(?:dark|light)\.svg)(?:\?v=[0-9a-f]+)?",
        rf"\1?v={content_hash}",
        text,
    )
    if updated != text:
        readme_path.write_text(updated, encoding="utf-8")


def main() -> None:
    local_json = sys.argv[1] if len(sys.argv) > 1 else None
    user = fetch_user_data(local_json)
    calendar = user["contributionsCollection"]["contributionCalendar"]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    hasher = hashlib.sha256()
    for theme in ("dark", "light"):
        outputs = {
            f"heatmap-{theme}.svg": render_heatmap(calendar, theme),
            f"trend-{theme}.svg": render_activity_curve(calendar, theme),
            f"metrics-{theme}.svg": render_metrics(user, theme),
        }
        for filename, svg in outputs.items():
            (OUT_DIR / filename).write_text(svg, encoding="utf-8")
            hasher.update(svg.encode("utf-8"))
    short_hash = hasher.hexdigest()[:8]
    update_readme_cache_buster(short_hash)
    print(f"Generated unified heatmap, trend, and metrics SVGs for @{USERNAME} ({calendar['totalContributions']} contributions, v={short_hash}).")


if __name__ == "__main__":
    main()
