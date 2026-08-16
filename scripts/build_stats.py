"""Render assets/stats.svg from live GitHub data.

Self-hosted replacement for third-party README widgets: pulls the contribution
calendar via GraphQL and draws an animated heatmap + stat tiles. Run by
.github/workflows/stats.yml on a schedule.
"""

import datetime as dt
import json
import os
import urllib.request

LOGIN = os.environ.get("GH_LOGIN", "MohdOtaqi")
TOKEN = os.environ["GH_TOKEN"]
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "stats.svg")

SANS = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
LEVELS = ["#0E1726", "#0D5A6E", "#009CB6", "#00CFE8", "#00F2FE"]

QUERY = """
query($login: String!) {
  user(login: $login) {
    repositories(ownerAffiliations: OWNER, isFork: false) { totalCount }
    contributionsCollection {
      totalCommitContributions
      totalPullRequestContributions
      totalIssueContributions
      restrictedContributionsCount
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount weekday } }
      }
    }
  }
}
"""


def fetch():
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": LOGIN}}).encode(),
        headers={"Authorization": f"bearer {TOKEN}", "Content-Type": "application/json",
                 "User-Agent": "mohdotaqi-profile-stats"},
    )
    with urllib.request.urlopen(req) as r:
        body = json.load(r)
    if "errors" in body:
        raise SystemExit(f"GraphQL error: {body['errors']}")
    return body["data"]["user"]


def streaks(days):
    """(current, longest) over the returned calendar window."""
    longest = run = 0
    for d in days:
        run = run + 1 if d["contributionCount"] > 0 else 0
        longest = max(longest, run)

    today = dt.date.today().isoformat()
    cur = 0
    for d in reversed(days):
        if d["date"] > today:
            continue
        if d["contributionCount"] > 0:
            cur += 1
        elif d["date"] == today:
            continue          # today may simply not have happened yet
        else:
            break
    return cur, longest


def thresholds(days):
    """Quartile cut points over active days, the way GitHub shades its own grid."""
    active = sorted(d["contributionCount"] for d in days if d["contributionCount"] > 0)
    if not active:
        return [1, 2, 3]
    return [active[int(len(active) * q)] for q in (0.25, 0.55, 0.80)]


def level(n, cuts):
    if n <= 0:
        return 0
    return 1 if n <= cuts[0] else 2 if n <= cuts[1] else 3 if n <= cuts[2] else 4


def build(user):
    cc = user["contributionsCollection"]
    cal = cc["contributionCalendar"]
    weeks = cal["weeks"]
    days = [d for w in weeks for d in w["contributionDays"]]
    cuts = thresholds(days)
    cur, longest = streaks(days)

    total = cal["totalContributions"]
    commits = cc["totalCommitContributions"] + cc["restrictedContributionsCount"]
    repos = user["repositories"]["totalCount"]

    W, H = 1200, 392
    CELL, GAP = 13, 3.4
    step = CELL + GAP
    grid_w = len(weeks) * step - GAP
    gx = (W - grid_w) / 2
    gy = 214

    tiles = [
        (f"{total:,}", "CONTRIBUTIONS / YEAR", "#00F2FE"),
        (f"{cur}", "CURRENT STREAK (DAYS)", "#7C4DFF"),
        (f"{longest}", "LONGEST STREAK (DAYS)", "#34D399"),
        (f"{repos}", "REPOSITORIES OWNED", "#FBBF24"),
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
    for wi, week in enumerate(weeks):
        col_delay = 0.55 + wi * 0.014
        inner = []
        for d in week["contributionDays"]:
            y = d["weekday"] * step
            lv = level(d["contributionCount"], cuts)
            extra = ''
            if lv == 4:
                extra = f'<animate attributeName="opacity" values="1;0.62;1" dur="3.6s" begin="{(wi % 7) * 0.4:.1f}s" repeatCount="indefinite"/>'
            inner.append(
                f'<rect y="{y:.1f}" width="{CELL}" height="{CELL}" rx="3" fill="{LEVELS[lv]}">{extra}</rect>')
        cells.append(
            f'<g transform="translate({wi * step:.1f} 0)" opacity="0">'
            f'<animate attributeName="opacity" from="0" to="1" dur="0.45s" begin="{col_delay:.2f}s" fill="freeze"/>'
            f'{"".join(inner)}</g>')

    months, seen = [], set()
    for wi, week in enumerate(weeks):
        first = week["contributionDays"][0]["date"]
        d = dt.date.fromisoformat(first)
        key = (d.year, d.month)
        if d.day <= 7 and key not in seen:
            seen.add(key)
            months.append(
                f'<text x="{wi * step:.1f}" y="-10" font-family="{MONO}" font-size="10.5" '
                f'letter-spacing="1.2" fill="#4C5B72">{d.strftime("%b").upper()}</text>')

    legend_x = W - 32 - 180
    legend = "".join(
        f'<rect x="{legend_x + 58 + i * 17:.1f}" y="{H - 34}" width="12" height="12" rx="3" fill="{c}"/>'
        for i, c in enumerate(LEVELS))

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
    <text x="32" y="{gy - 38}" font-family="{MONO}" font-size="11.5" letter-spacing="2" fill="#5B6C86">CONTRIBUTION ACTIVITY &#183; LAST 12 MONTHS &#183; {commits:,} COMMITS</text>

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
    svg = build(fetch())
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"wrote {OUT} ({len(svg)} bytes)")
