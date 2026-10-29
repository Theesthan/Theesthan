"""Renders the profile's animated SVGs (title screen, player card, project
cards, link buttons) from live GitHub stats. Run daily by
.github/workflows/player-card.yml; `python scripts/gen.py` needs GITHUB_TOKEN."""
import json
import logging
import math
import os
import random
import textwrap
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from xml.sax.saxutils import escape, quoteattr

from pixelfont import defs_for, text, text_width

LOGIN = os.environ.get("GITHUB_REPOSITORY_OWNER", "Theesthan")
NAME = "EKO"
ROLE = "AI / FULL-STACK ENGINEER"
ASSETS = Path(__file__).resolve().parent.parent / "assets"

BG, PANEL, INK, DIM = "#0b0a1a", "#14122b", "#ece9ff", "#8783b3"
CYAN, PINK, YELLOW, GREEN, ORANGE = "#3ef0ff", "#ff4fd8", "#ffd23f", "#39ff88", "#ff8a3d"

# Markup and build files say little about skills, so they stay off the bars.
IGNORED_LANGS = {"HTML", "CSS", "SCSS", "Mako", "Jinja", "Dockerfile", "Makefile", "Batchfile"}

PROJECTS = [
    {"slug": "voxsentinel", "name": "VoxSentinel", "color": CYAN,
     "tagline": "Real-time speech monitoring with live keyword and sentiment alerts",
     "tech": "PYTHON · FASTAPI · REACT"},
    {"slug": "unseal", "name": "UnSeal", "color": PINK,
     "tagline": "Turns a citizen's concern into a filing-ready RTI application",
     "tech": "FASTAPI · NEXT.JS · LLM"},
    {"slug": "indigoglass-nexus", "name": "IndigoGlass Nexus", "color": YELLOW,
     "tagline": "Demand forecasting and distribution planning for pharma",
     "tech": "FASTAPI · NEXT.JS · NEO4J"},
    {"slug": "ariadne", "name": "Ariadne", "color": GREEN,
     "tagline": "Traces a buried CVE to every application it exposes",
     "tech": "PYTHON · TS · MCP"},
]

BUTTONS = [
    {"slug": "portfolio", "label": "PORTFOLIO", "color": CYAN},
    {"slug": "linkedin", "label": "LINKEDIN", "color": PINK},
    {"slug": "email", "label": "EMAIL", "color": YELLOW},
    {"slug": "x", "label": "X (TWITTER)", "color": GREEN},
]

QUERY = """query($login: String!) { user(login: $login) {
  contributionsCollection { contributionCalendar { totalContributions
    weeks { contributionDays { date contributionCount } } } }
  repositories(ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC, first: 100) {
    totalCount
    nodes { languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
      edges { size node { name } } } } } } }"""

BASE_CSS = (
    "@keyframes blink{50%{opacity:0}}"
    "@keyframes bob{50%{transform:translateY(-4px)}}"
    "@keyframes tw{50%{opacity:.15}}"
    "@keyframes pop{from{opacity:0}}"
    "@keyframes grow{from{transform:scaleX(0)}}"
    "@keyframes glow{50%{stroke-opacity:.35}}"
    ".blink{animation:blink 1s steps(1) infinite}"
    ".bob{animation:bob 2.4s ease-in-out infinite}"
    ".pop{animation:pop .2s steps(1) both}"
    ".grow{transform-box:fill-box;transform-origin:left;animation:grow 1.4s cubic-bezier(.2,.8,.2,1) .3s both}"
    "@media (prefers-reduced-motion:reduce){*{animation:none!important}}"
)


# ---------- stats ----------

def fetch_stats() -> dict:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit("GITHUB_TOKEN is not set")
    body = json.dumps({"query": QUERY, "variables": {"login": LOGIN}}).encode()
    req = Request("https://api.github.com/graphql", data=body,
                  headers={"Authorization": f"bearer {token}", "User-Agent": "profile-card"})
    with urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    if data.get("errors"):
        raise ValueError(f"GraphQL errors: {data['errors']}")
    return data


def level_info(xp: int) -> tuple[int, int, int]:
    """Level n starts at 10*n^2 XP. Returns (level, xp into level, xp span of level)."""
    level = math.isqrt(xp // 10)
    start, end = 10 * level ** 2, 10 * (level + 1) ** 2
    return level, xp - start, end - start


def streak(days: list[dict], today: date) -> int:
    """Consecutive days with contributions, ending today (or yesterday if today is still empty)."""
    counts = {d["date"]: d["contributionCount"] for d in days}
    day = today if counts.get(today.isoformat(), 0) else today - timedelta(days=1)
    n = 0
    while counts.get(day.isoformat(), 0) > 0:
        n, day = n + 1, day - timedelta(days=1)
    return n


def top_languages(repos: list[dict], n: int) -> list[tuple[str, float]]:
    sizes: dict[str, int] = {}
    for repo in repos:
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            if name not in IGNORED_LANGS:
                sizes[name] = sizes.get(name, 0) + edge["size"]
    total = sum(sizes.values()) or 1
    ranked = sorted(sizes.items(), key=lambda kv: kv[1], reverse=True)[:n]
    return [(name, round(size * 100 / total, 1)) for name, size in ranked]


def parse_stats(resp: dict, today: date) -> dict:
    user = resp["data"]["user"]
    cal = user["contributionsCollection"]["contributionCalendar"]
    days = [d for w in cal["weeks"] for d in w["contributionDays"]]
    xp = cal["totalContributions"]
    level, into, span = level_info(xp)
    return {
        "xp": xp, "level": level, "into": into, "span": span,
        "streak": streak(days, today),
        "repos": user["repositories"]["totalCount"],
        "langs": top_languages(user["repositories"]["nodes"], 4),
    }


# ---------- svg ----------

def svg_doc(w: int, h: int, label: str, body: str, css: str = "", defs: str = "") -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
        f'role="img" aria-label={quoteattr(label)} shape-rendering="crispEdges">'
        f"<title>{escape(label)}</title><style>{BASE_CSS}{css}</style>"
        f"<defs>{defs}{defs_for(body)}</defs>{body}</svg>"
    )


def sprite(rows: list[str], palette: dict[str, str], x: float, y: float, px: float, cls: str = "") -> str:
    rects = "".join(
        f'<rect x="{x + i * px}" y="{y + j * px}" width="{px}" height="{px}" fill="{palette[c]}"/>'
        for j, row in enumerate(rows) for i, c in enumerate(row) if c in palette
    )
    return f'<g class="{cls}">{rects}</g>' if cls else rects


def centered(s: str, w: float, y: float, scale: float, fill: str, cls: str | None = None, x0: float = 0) -> str:
    return text(s, x0 + (w - text_width(s, scale)) / 2, y, scale, fill, cls)


ALIEN_A = ["....#....", "...###...", ".#######.", "##.###.##", "#########", ".#.#.#.#.", "#.......#", ".#.....#."]
ALIEN_B = ALIEN_A[:6] + [".#.....#.", "#.......#"]

AVATAR = [
    "...hhhhhh...", "..hhhhhhhh..", ".chhhhhhhhc.", ".chsssssshc.", ".csessssesc.",
    ".cssssssssc.", "..sssmmsss..", "...ssssss...", "..pppssppp..", ".pppppppppp.",
    "pppwppppwppp", "pppwppppwppp", "ppllllllllpp", "..llllllll..",
]
AVATAR_COLORS = {"h": "#2b2350", "c": CYAN, "s": "#f1c39c", "e": "#1b1638", "m": "#c46a5a",
                 "p": PINK, "w": "#ffe3f7", "l": "#9aa3c7"}


def _starfield(w: int, h: int) -> str:
    rng = random.Random(7)  # fixed seed: same sky every day, so only stats cause diffs
    layers = []
    for count, size, color, secs in ((40, 2, DIM, 60), (18, 3, INK, 30)):
        stars = "".join(
            f'<rect x="{rng.randrange(w)}" y="{rng.randrange(h)}" width="{size}" height="{size}" fill="{color}"'
            + (f' style="animation:tw {rng.uniform(1.5, 4):.1f}s infinite"' if rng.random() < .4 else "") + "/>"
            for _ in range(count)
        )
        # Two copies side by side scroll left by one width, so the loop is seamless.
        layers.append(f'<g style="animation:drift {secs}s linear infinite">{stars}'
                      f'<g transform="translate({w} 0)">{stars}</g></g>')
    return "".join(layers)


def render_header(stats: dict) -> str:
    w, h = 840, 260
    lv = f"LV {stats['level']:02d}"
    body = (
        f'<g clip-path="url(#round)"><rect width="{w}" height="{h}" fill="{BG}"/>{_starfield(w, h)}'
        + text("1UP", 24, 18, 2, PINK, "blink")
        + centered("HI-SCORE", w, 14, 2, DIM) + centered(f"{stats['xp']:06d}", w, 34, 2, INK)
        + text(lv, w - 24 - text_width(lv, 2), 18, 2, YELLOW)
        + f'<g class="bob">{centered(NAME, w, 62, 16, PINK)}{centered(NAME, w, 56, 16, "url(#gold)")}</g>'
        + f'<g class="fa">{sprite(ALIEN_A, {"#": GREEN}, 150, 96, 6)}{sprite(ALIEN_A, {"#": CYAN}, 636, 96, 6)}</g>'
        + f'<g class="fb">{sprite(ALIEN_B, {"#": GREEN}, 150, 96, 6)}{sprite(ALIEN_B, {"#": CYAN}, 636, 96, 6)}</g>'
        + centered(ROLE, w, 186, 3, INK) + centered("PRESS START", w, 226, 2, YELLOW, "blink")
        + f'<rect width="{w}" height="{h}" fill="url(#scan)"/><rect width="{w}" height="{h}" fill="url(#vig)"/></g>'
    )
    defs = (
        f'<clipPath id="round"><rect width="{w}" height="{h}" rx="14"/></clipPath>'
        f'<linearGradient id="gold" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{YELLOW}"/>'
        f'<stop offset="1" stop-color="{ORANGE}"/></linearGradient>'
        '<pattern id="scan" width="4" height="4" patternUnits="userSpaceOnUse">'
        '<rect width="4" height="1" fill="#000" opacity=".28"/></pattern>'
        '<radialGradient id="vig"><stop offset=".6" stop-opacity="0"/><stop offset="1" stop-opacity=".55"/></radialGradient>'
    )
    css = (f"@keyframes drift{{to{{transform:translateX(-{w}px)}}}}"
           ".fa{animation:blink 1s steps(1) infinite}.fb{animation:blink 1s steps(1) -.5s infinite}")
    return svg_doc(w, h, f"{NAME}, AI / Full-stack Engineer", body, css, defs)


def _lang_rows(langs: list, x: int, y: int) -> str:
    out, segs = [], 24
    for row, (name, pct) in enumerate(langs):
        ry, color = y + row * 26, (CYAN, PINK, YELLOW, GREEN)[row % 4]
        filled = max(1, round(pct / 100 * segs)) if pct > 0 else 0
        out.append(text(name[:10], x, ry, 2, INK))
        for i in range(segs):
            sx = x + 132 + i * 14
            if i < filled:
                out.append(f'<rect class="pop" style="animation-delay:{.4 + row * .25 + i * .04:.2f}s" '
                           f'x="{sx}" y="{ry}" width="12" height="14" fill="{color}"/>')
            else:
                out.append(f'<rect x="{sx}" y="{ry}" width="12" height="14" fill="#ffffff12"/>')
        out.append(text(f"{pct:.0f}%", x + 132 + segs * 14 + 16, ry, 2, DIM))
    return "".join(out)


def render_card(stats: dict, saved: str) -> str:
    w, h, x = 840, 300, 256
    level, into, span = stats["level"], stats["into"], stats["span"]
    bar = max(2, round(456 * into / span)) if into else 0
    eyes = "".join(f'<rect x="{56 + c * 12}" y="{64 + 4 * 12}" width="12" height="12" fill="{AVATAR_COLORS["s"]}"/>'
                   for c in (3, 8))
    body = (
        f'<rect x="1.5" y="1.5" width="{w - 3}" height="{h - 3}" rx="14" fill="{PANEL}" stroke="{CYAN}" stroke-width="3"/>'
        f'<rect x="10" y="10" width="{w - 20}" height="{h - 20}" rx="8" fill="none" stroke="{CYAN}" stroke-opacity=".25"/>'
        + text("PLAYER 1", 28, 24, 2, PINK) + text(f"SAVED {saved}", w - 28 - text_width(f"SAVED {saved}", 2), 24, 2, DIM)
        + f'<rect x="28" y="56" width="200" height="212" rx="6" fill="{BG}" stroke="{DIM}" stroke-opacity=".5"/>'
        + f'<g class="bob">{sprite(AVATAR, AVATAR_COLORS, 56, 64, 12)}<g class="eyes">{eyes}</g></g>'
        + centered(NAME, 200, 240, 3, INK, x0=28)
        + text("CLASS", x, 60, 2, DIM) + text(ROLE, x + 100, 60, 2, INK)
        + text(f"LV {level}", x, 92, 3, YELLOW)
        + f'<rect x="{x + 100}" y="94" width="456" height="16" fill="{BG}" stroke="{DIM}" stroke-opacity=".6"/>'
        + f'<rect class="grow" x="{x + 100}" y="94" width="{bar}" height="16" fill="{YELLOW}"/>'
        + text(f"{stats['xp']} XP THIS YEAR · NEXT LV IN {span - into}", x + 100, 118, 2, DIM)
        + _lang_rows(stats["langs"], x, 146)
        + text(f"♥ STREAK {stats['streak']}D", x, 258, 2, PINK)
        + text(f"★ QUESTS {stats['repos']}", x + 214, 258, 2, YELLOW)
        + text("▶ ONLINE", x + 404, 258, 2, GREEN, "blink")
    )
    css = ("@keyframes shut{0%,92%,100%{opacity:0}94%,98%{opacity:1}}"
           ".eyes{animation:shut 4s infinite}")
    label = (f"Player card: Level {level}, {stats['xp']} contributions in the last year, "
             f"{stats['streak']}-day streak")
    return svg_doc(w, h, label, body, css)


def render_project(p: dict, i: int) -> str:
    w, h, color = 440, 200, p["color"]
    lines = textwrap.wrap(p["tagline"].upper(), 33)[:3]
    body = (
        f'<g clip-path="url(#r{i})"><rect width="{w}" height="{h}" fill="{PANEL}"/>'
        f'<rect class="sweep" width="{w}" height="36" fill="url(#beam)"/></g>'
        f'<rect class="edge" x="1.5" y="1.5" width="{w - 3}" height="{h - 3}" rx="10" fill="none" '
        f'stroke="{color}" stroke-width="3" style="animation-delay:{i * .6}s"/>'
        + text(f"STAGE 0{i + 1}", 20, 20, 2, color)
        + text("♥♥♥", w - 20 - text_width("♥♥♥", 2), 20, 2, PINK)
        + text(p["name"], 20, 48, 3, INK)
        + "".join(text(line, 20, 86 + k * 22, 2, DIM) for k, line in enumerate(lines))
        + text(p["tech"], 20, 166, 2, color)
        + text("▶ PLAY", w - 20 - text_width("▶ PLAY", 2), 166, 2, YELLOW, "blink")
    )
    defs = (f'<clipPath id="r{i}"><rect width="{w}" height="{h}" rx="10"/></clipPath>'
            f'<linearGradient id="beam" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{color}" stop-opacity="0"/>'
            f'<stop offset=".5" stop-color="{color}" stop-opacity=".12"/><stop offset="1" stop-color="{color}" stop-opacity="0"/>'
            "</linearGradient>")
    css = (".edge{animation:glow 3s ease-in-out infinite}"
           f"@keyframes sweep{{from{{transform:translateY(-40px)}}to{{transform:translateY({h}px)}}}}"
           f".sweep{{animation:sweep 4s linear {i * .9:.1f}s infinite}}")
    return svg_doc(w, h, f"{p['name']}: {p['tagline']}", body, css, defs)


def render_button(b: dict) -> str:
    w, h, color = 220, 52, b["color"]
    body = (
        f'<g clip-path="url(#b)"><rect width="{w}" height="{h}" fill="{BG}"/>'
        f'<rect class="shine" x="0" y="-10" width="36" height="{h + 20}" fill="#fff" opacity=".18"/></g>'
        f'<rect x="1.5" y="1.5" width="{w - 3}" height="{h - 3}" rx="6" fill="none" stroke="{color}" stroke-width="3"/>'
        + centered(b["label"], w, 19, 2, color)
    )
    defs = f'<clipPath id="b"><rect width="{w}" height="{h}" rx="6"/></clipPath>'
    css = ("@keyframes shine{0%{transform:translateX(-60px) skewX(-20deg)}"
           "40%,100%{transform:translateX(260px) skewX(-20deg)}}"
           ".shine{animation:shine 3.5s ease-in-out infinite}")
    return svg_doc(w, h, b["label"].title(), body, css, defs)


# ---------- main ----------

def main(out: Path = ASSETS, fetch: Callable[[], dict] = fetch_stats) -> None:
    now = datetime.now(timezone.utc)
    cache = out / "stats.json"
    try:
        stats = parse_stats(fetch(), now.date())
    except Exception as err:  # an API hiccup must not cost the day's commit
        if not cache.exists():
            raise
        logging.warning("::warning::stats fetch failed (%s); rendering cached stats", err)
        stats = json.loads(cache.read_text())
    (out / "projects").mkdir(parents=True, exist_ok=True)
    files = {
        "header.svg": render_header(stats),
        "card.svg": render_card(stats, now.strftime("%d %b %H:%M UTC").upper()),
        **{f"projects/{p['slug']}.svg": render_project(p, i) for i, p in enumerate(PROJECTS)},
        **{f"btn-{b['slug']}.svg": render_button(b) for b in BUTTONS},
        "stats.json": json.dumps(stats, indent=2) + "\n",
    }
    for name, content in files.items():
        (out / name).write_text(content, encoding="utf-8")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")  # bare lines, so ::warning:: annotates
    main()
