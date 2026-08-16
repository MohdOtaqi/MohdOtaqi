"""Render assets/stats.svg from GitHub's public contribution calendar.

Self-hosted replacement for third-party README widgets. Reads
https://github.com/users/<login>/contributions — the same HTML that backs the
graph on the profile page. That endpoint needs no authentication and already
includes private-repo contributions (they show publicly because "include
private contributions on my profile" is enabled), so this runs on a bare
GitHub Actions runner with no PAT and no secrets.

Shading uses GitHub's own data-level values, so the heatmap matches the real
graph rather than re-deriving its own thresholds.

Run by .github/workflows/stats.yml.
"""

import datetime as dt
import os
import re
import urllib.request

LOGIN = os.environ.get("GH_LOGIN", "MohdOtaqi")
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "stats.svg")

SANS = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
LEVELS = ["#0E1726", "#0D5A6E", "#009CB6", "#00CFE8", "#00F2FE"]

CELL_RE = re.compile(r'<td\b[^>]*class="ContributionCalendar-day"[^>]*>', re.I)
TIP_RE = re.compile(r'<tool-tip\b[^>]*\bfor="(contribution-day-component-[\d-]+)"[^>]*>(.*?)</tool-tip>', re.I | re.S)
TOTAL_RE = re.compile(r'([\d,]+)\s+contributions?\s+in\s+the\s+last\s+year', re.I)


def attr(tag, name):
    m = re.search(r'\b%s="([^"]*)"' % name, tag)
    return m.group(1) if m else None


def fetch(login):
    req = urllib.request.Request(
        f"https://github.com/users/{login}/contributions",
        headers={"User-Agent": "mohdotaqi-profile-stats", "Accept": "text/html"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def parse(html):
    counts = {}
    for cid, text in TIP_RE.findall(html):
        m = re.match(r"\s*([\d,]+)\s+contribution", text.strip())
        counts[cid] = int(m.group(1).replace(",", "")) if m else 0

    days = []
    for tag in CELL_RE.findall(html):
        date, cid = attr(tag, "data-date"), attr(tag, "id")
        if not date or not cid:
            continue
        wd, wk = cid.rsplit("-", 2)[-2:]
        days.append({
            "date": date,
            "level": int(attr(tag, "data-level") or 0),
            "count": counts.get(cid, 0),
            "weekday": int(wd),
            "week": int(wk),
        })
    if not days:
        raise SystemExit("no contribution cells found — GitHub markup may have changed")

    days.sort(key=lambda d: d["date"])
    m = TOTAL_RE.search(html)
    total = int(m.group(1).replace(",", "")) if m else sum(d["count"] for d in days)
    return days, total


def streaks(days):
    """(current, longest). Today is skipped rather than breaking a live streak."""
    longest = run = 0
    for d in days:
        run = run + 1 if d["count"] > 0 else 0
        longest = max(longest, run)

    today = dt.date.today().isoformat()
    cur = 0
    for d in reversed(days):
        if d["date"] > today:
            continue
        if d["count"] > 0:
            cur += 1
        elif d["date"] == today:
            continue          # today may simply not have happened yet
        else:
            break
    return cur, longest


def build(days, total):
    weeks = {}
    for d in days:
        weeks.setdefault(d["week"], []).append(d)
    week_keys = sorted(weeks)

    cur, longest = streaks(days)
    active = sum(1 for d in days if d["count"] > 0)

    W, H = 1200, 392
    CELL, GAP = 13, 3.4
    step = CELL + GAP
    grid_w = len(week_keys) * step - GAP
    gx = (W - grid_w) / 2
    gy = 214

    tiles = [
        (f"{total:,}", "CONTRIBUTIONS / YEAR", "#00F2FE"),
        (f"{cur}", "CURRENT STREAK (DAYS)", "#7C4DFF"),
        (f"{longest}", "LONGEST STREAK (DAYS)", "#34D399"),
        (f"{active}", "ACTIVE DAYS / YEAR", "#FBBF24"),
    ]

    tw, tgap, tx0 = 276.0, 12.0, 32.0
    tile_svg = []
    for i, (val, label, col) in enumerate(tiles):
        x = tx0 + i * (tw + tgap)
        tile_svg.append(f'''
    <g transform="translate({x:.1f} 34)" opacity="0">
      <animate attributeName="opacity" from="0" to="1" dur="0.5s" begin="{0.1 + i * 0.12:.2f}s" fill="freeze"/>
      <rect width="{tw}" height="96" rx="14" fill="#0A101C" stroke="{col}" stroke-opacity="0.28"/>
      <rect x="18" y="20" width="3" height="56" rx="1.5" fill="{col}" opacity="0.75"/>
      <text x="36" y="56" font-family="{SANS}" font-size="34" font-weight="800" fill="#F1F5F9">{val}</text>
      <text x="36" y="78" font-family="{MONO}" font-size="10.5" letter-spacing="1.5" fill="{col}" fill-opacity="0.9">{label}</text>
      <circle cx="{tw - 24}" cy="24" r="3.5" fill="{col}">
        <animate attributeName="opacity" values="1;0.25;1" dur="{2.0 + i * 0.3:.1f}s" repeatCount="indefinite"/>
      </circle>
    </g>''')

    cells = []
    for col_i, wk in enumerate(week_keys):
        inner = []
        for d in weeks[wk]:
            y = d["weekday"] * step
            extra = ''
            if d["level"] == 4:
                extra = (f'<animate attributeName="opacity" values="1;0.62;1" dur="3.6s" '
                         f'begin="{(col_i % 7) * 0.4:.1f}s" repeatCount="indefinite"/>')
            inner.append(f'<rect y="{y:.1f}" width="{CELL}" height="{CELL}" rx="3" '
                         f'fill="{LEVELS[d["level"]]}">{extra}</rect>')
        cells.append(
            f'<g transform="translate({col_i * step:.1f} 0)" opacity="0">'
            f'<animate attributeName="opacity" from="0" to="1" dur="0.45s" '
            f'begin="{0.55 + col_i * 0.014:.2f}s" fill="freeze"/>'
            f'{"".join(inner)}</g>')

    months, seen = [], set()
    for col_i, wk in enumerate(week_keys):
        d = dt.date.fromisoformat(weeks[wk][0]["date"])
        key = (d.year, d.month)
        if d.day <= 7 and key not in seen:
            seen.add(key)
            months.append(
                f'<text x="{col_i * step:.1f}" y="-10" font-family="{MONO}" font-size="10.5" '
                f'letter-spacing="1.2" fill="#4C5B72">{d.strftime("%b").upper()}</text>')

    legend_x = W - 32 - 180
    legend = "".join(
        f'<rect x="{legend_x + 58 + i * 17:.1f}" y="{H - 34}" width="12" height="12" rx="3" fill="{c}"/>'
        for i, c in enumerate(LEVELS))

    span = f'{dt.date.fromisoformat(days[0]["date"]).strftime("%b %Y").upper()} &#8594; {dt.date.fromisoformat(days[-1]["date"]).strftime("%b %Y").upper()}'

    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="GitHub activity: {total} contributions in the last year">
  <title>GitHub activity</title>
  <defs>
    <linearGradient id="sbg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#070B14"/><stop offset="100%" stop-color="#05070E"/>
    </linearGradient>
    <linearGradient id="srule" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="#00F2FE" stop-opacity="0"/>
      <stop offset="50%" stop-color="#00F2FE" stop-opacity="0.8"/>
      <stop offset="100%" stop-color="#00F2FE" stop-opacity="0"/>
    </linearGradient>
    <clipPath id="sclip"><rect width="{W}" height="{H}" rx="18"/></clipPath>
  </defs>

  <g clip-path="url(#sclip)">
    <rect width="{W}" height="{H}" fill="url(#sbg)"/>
    <rect x="200" y="0" width="800" height="2" fill="url(#srule)"/>
{"".join(tile_svg)}

    <rect x="32" y="{gy - 62}" width="{W - 64}" height="1" fill="#16223A"/>
    <text x="32" y="{gy - 38}" font-family="{MONO}" font-size="11.5" letter-spacing="2" fill="#5B6C86">CONTRIBUTION ACTIVITY &#183; {span}</text>

    <g transform="translate({gx:.1f} {gy})">
      {"".join(months)}
      {"".join(cells)}
    </g>

    <text x="{legend_x}" y="{H - 24}" font-family="{MONO}" font-size="10.5" letter-spacing="1.2" fill="#4C5B72">LESS</text>
    {legend}
    <text x="{legend_x + 58 + 5 * 17 + 4:.1f}" y="{H - 24}" font-family="{MONO}" font-size="10.5" letter-spacing="1.2" fill="#4C5B72">MORE</text>

    <rect width="{W}" height="{H}" rx="18" fill="none" stroke="#18243A" stroke-width="1.5"/>
  </g>
</svg>
'''


if __name__ == "__main__":
    days, total = parse(fetch(LOGIN))
    svg = build(days, total)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"wrote {OUT}: {len(days)} days, {total:,} contributions, {len(svg)} bytes")
