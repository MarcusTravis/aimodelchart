#!/usr/bin/env python3
"""Bake data/latest.json into static files for search engines and AI crawlers.

Rewrites, from data/latest.json only (no network):
  - index.html: the table rows, the "Last updated" line and the JSON-LD block,
    between <!-- X:START --> / <!-- X:END --> markers. app.js still re-renders
    the table in the browser, so visitors see no difference.
  - llms.txt: a plain-text summary of today's data for AI assistants.
  - sitemap.xml: <lastmod> set to the data date.
Output only changes when the data changes, so the daily workflow stays quiet.
"""
import datetime as dt
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://aimodelchart.pages.dev/"
DASH = "—"
TITLE = "AI Model Chart — popularity and intelligence of top AI models"
DESC = ("Which AI models are most used, and how smart are they? OpenRouter popularity next to "
        "Epoch ECI and LMArena Arena Score, updated daily.")

GSC_META = '<meta name="google-site-verification" content="DBsd4dRo6CszvxQNH2xXlYTnwq2I4v30uIsV_nwwEc8" />'


def pct(v):
    return f"{v * 100:.1f}%"


def faq_items(models, pretty, eci_day):
    """Visible FAQ card and FAQPage JSON-LD are both built from this list, so they always match."""
    pop = sorted((m for m in models if m.get("pop_rank")), key=lambda m: m["pop_rank"])
    eci = sorted((m for m in models if m.get("eci") is not None), key=lambda m: -m["eci"])
    if pop:
        m = pop[0]
        by = f" from {m['maker']}" if m.get("maker") else ""
        share = f", handling {pct(m['share'])} of all tokens there" if m.get("share") is not None else ""
        a1 = (f"{m['name']}{by}. It was the most-used model on OpenRouter on the latest full day of data"
              f"{share}. Popular means most used, not smartest. Checked {pretty}.")
    else:
        a1 = "Popularity data is temporarily unavailable. Check back after the next daily update."
    if eci:
        m = eci[0]
        by = f" from {m['maker']}" if m.get("maker") else ""
        a2 = (f"{m['name']}{by}, with an ECI of {m['eci']:.1f}, the highest of the models on this page"
              + (f" as of {eci_day}" if eci_day else "") + ". Arena Score can rank a different model first, "
              "because it measures which answers people prefer, not test results.")
    else:
        a2 = "ECI data is temporarily unavailable. Check back after the next daily update."
    return [
        ("What is the most popular AI model right now?", a1),
        ("What is the smartest AI model by ECI right now?", a2),
        ("What is a token?",
         "A token is how AI usage gets counted. It is a small piece of text, about three-quarters of a word, "
         "so 1,000 tokens is roughly 750 words. Both your question and the AI's answer count."),
        ("What's the difference between ECI and Arena Score?",
         "ECI, from the nonprofit Epoch AI, is a test score: models take hard tests in math, coding, science "
         "and reasoning, and the results become one number. Arena Score, from LMArena, is a people score: "
         "real people compare two unnamed answers and vote for the better one. A model can do well on one "
         "and less well on the other, so this page shows both and never blends them."),
        ("Does this show prices?",
         "No. This page only shows how much each model is used and how capable it is. It has nothing to do "
         "with price."),
        ("How often is it updated?",
         "Once a day, automatically. The date at the top of the page shows the last update."),
        ("Where does the data come from?",
         "Usage comes from OpenRouter, a service that lets apps use hundreds of AI models in one place. "
         "Intelligence scores come from Epoch AI (ECI) and LMArena (Arena Score). All three share their data "
         "under the CC BY 4.0 license."),
        ("Is it free?",
         "Yes. The site is free, has no ads, and needs no sign-up."),
    ]



def e(v):
    return html.escape(str(v), quote=True)


def num(v, d=0):
    return DASH if v is None else f"{v:,.{d}f}"


def td(cls, text):
    c = f' class="{cls}"' if cls else ""
    return f"<td{c}>{text}</td>"


def row(m):
    out = [td("" if m.get("pop_rank") else "muted", e(m.get("pop_rank") or DASH))]
    name = e(m["name"]) + (f"<small>{e(m['access'])}</small>" if m.get("access") else "")
    out.append(td("name left", name))
    out.append(td("left muted hide-sm", e(m.get("maker") or DASH)))
    s = m.get("share")
    out.append(td("", f'<span class="share"><span>{s * 100:.1f}%</span></span>') if s is not None
               else td("muted", DASH))
    rc = m.get("rank_change")
    if m.get("new_entry"):
        out.append(td("hide-sm muted", "new"))
    elif rc is None:
        out.append(td("hide-sm muted", DASH))
    elif rc > 0:
        out.append(td("hide-sm up", f"▲ {rc}"))
    elif rc < 0:
        out.append(td("hide-sm down", f"▼ {abs(rc)}"))
    else:
        out.append(td("hide-sm muted", "="))
    out.append(td("muted" if m.get("eci") is None else "", num(m.get("eci"), 1)))
    out.append(td("muted" if m.get("arena") is None else "", num(m.get("arena"))))
    ar = m.get("arena_rank")
    out.append(td("hide-sm " + ("muted" if ar is None else ""), DASH if ar is None else ar))
    return "<tr>" + "".join(out) + "</tr>"


def sort_rows(models):
    if any(m.get("pop_rank") for m in models):
        return sorted(models, key=lambda m: (m.get("pop_rank") is None, m.get("pop_rank") or 0))
    return sorted(models, key=lambda m: (m.get("eci") is None, -(m.get("eci") or 0)))


def top(models, key, n=10, reverse=True):
    have = [m for m in models if m.get(key) is not None]
    return sorted(have, key=lambda m: m[key], reverse=reverse)[:n]


def put(text, marker, body):
    pat = re.compile(rf"(<!-- {marker}:START -->).*?(<!-- {marker}:END -->)", re.S)
    if not pat.search(text):
        raise SystemExit(f"marker {marker} missing in index.html")
    return pat.sub(lambda mo: mo.group(1) + body + mo.group(2), text)


def write_if_changed(path, text):
    if not path.exists() or path.read_text() != text:
        path.write_text(text)
        print(f"[prerender] wrote {path.name}")


def main():
    d = json.loads((ROOT / "data/latest.json").read_text())
    models = d.get("models") or []
    src = d.get("sources") or {}
    gen = d.get("generated_at")
    when = dt.datetime.strptime(gen, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc) if gen else None
    day = when.date().isoformat() if when else None
    pretty = f"{when:%B} {when.day}, {when.year}" if when else None

    pop = top(models, "pop_rank", reverse=False)
    eci_as_of = (src.get("eci") or {}).get("as_of")
    try:
        ed = dt.date.fromisoformat(eci_as_of)
        eci_as_of = f"{ed:%B} {ed.day}, {ed.year}"
    except (TypeError, ValueError):
        pass
    faq = faq_items(models, pretty, eci_as_of)
    eci = top(models, "eci")
    arena = top(models, "arena")

    summary = DESC
    if pop:
        summary = (f"Most-used AI models on OpenRouter as of {pretty}: "
                   + ", ".join(m["name"] for m in pop[:5])
                   + (f". Highest Epoch ECI: {eci[0]['name']} ({eci[0]['eci']:.1f})." if eci else ".")
                   + (f" Top LMArena Arena Score: {arena[0]['name']} ({arena[0]['arena']:.0f})." if arena else ""))

    author = {"@type": "Person", "name": "Marcus Travis"}
    based = [
        {"@type": "Dataset", "name": "OpenRouter daily rankings", "url": "https://openrouter.ai/rankings",
         "license": "https://creativecommons.org/licenses/by/4.0/"},
        {"@type": "Dataset", "name": "Epoch Capabilities Index", "url": "https://epoch.ai/eci",
         "creator": {"@type": "Organization", "name": "Epoch AI"},
         "license": "https://creativecommons.org/licenses/by/4.0/"},
        {"@type": "Dataset", "name": "LMArena text leaderboard",
         "url": "https://huggingface.co/datasets/lmarena-ai/leaderboard-dataset",
         "creator": {"@type": "Organization", "name": "LMArena"},
         "license": "https://creativecommons.org/licenses/by/4.0/"},
    ]
    graph = [
        {"@type": "WebSite", "@id": SITE + "#website", "url": SITE, "name": "AI Model Chart",
         "description": DESC, "inLanguage": "en", "author": author},
        {"@type": "WebPage", "@id": SITE + "#webpage", "url": SITE, "name": TITLE, "description": summary,
         "isPartOf": {"@id": SITE + "#website"}, "about": {"@id": SITE + "#dataset"},
         "primaryImageOfPage": SITE + "og-image.png", "inLanguage": "en",
         **({"dateModified": gen} if gen else {})},
        {"@type": "Dataset", "@id": SITE + "#dataset", "name": "AI Model Chart: AI model popularity and intelligence",
         "description": ("Daily table of the most-used AI models (OpenRouter token share and rank) alongside "
                         "Epoch Capabilities Index (ECI) and LMArena Arena Score. Sources are shown separately "
                         "and never combined. " + (summary if pop else "")).strip(),
         "url": SITE, "creator": author, "isAccessibleForFree": True, "isBasedOn": based,
         "keywords": ["AI models", "LLM leaderboard", "AI model popularity", "OpenRouter rankings",
                      "Epoch Capabilities Index", "LMArena", "Arena Score", "tokens"],
         "variableMeasured": ["Popularity rank", "Token share", "Rank change", "ECI", "Arena Score", "Arena rank"],
         "distribution": [{"@type": "DataDownload", "encodingFormat": "application/json",
                           "contentUrl": SITE + "data/latest.json"}],
         **({"dateModified": gen, "temporalCoverage": day} if gen else {})},
        {"@type": "FAQPage", "@id": SITE + "#faq", "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]},
    ]
    ld = json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False, indent=1)
    ld = ld.replace("</", "<\\/")

    p = ROOT / "index.html"
    s = p.read_text()
    if GSC_META not in s:   # keep the Google Search Console verification tag
        s = s.replace('<link rel="canonical"', GSC_META + "\n" + '<link rel="canonical"', 1)
    s = put(s, "FAQ", "\n" + "\n".join(f"      <dt>{html.escape(q, quote=False)}</dt>\n      <dd>{html.escape(a, quote=False)}</dd>" for q, a in faq) + "\n    ")
    s = put(s, "JSONLD", f'\n<script type="application/ld+json">\n{ld}\n</script>\n')
    s = put(s, "UPDATED", f"Last updated {pretty} UTC" if pretty else "")
    s = put(s, "ROWS", "\n" + "\n".join(row(m) for m in sort_rows(models)) + "\n" if models else "")
    write_if_changed(p, s)

    def lines(ms, fmt):
        return "\n".join(f"{i}. {fmt(m)}" for i, m in enumerate(ms, 1)) or "(no data today)"

    def tag(m):
        bits = [m.get("maker"), m.get("access") and m["access"] + " weights"]
        return " (" + ", ".join(b for b in bits if b) + ")" if any(bits) else ""

    txt = f"""# AI Model Chart

> Free, ad-free daily tracker of the most-used AI models and how smart they are. Popularity (OpenRouter token share) is shown next to two separate intelligence scores: Epoch Capabilities Index (ECI) and LMArena Arena Score. Scores are never blended into one number.

Last updated: {pretty + " (UTC)" if pretty else "unknown"}

## Pages and data

- [AI Model Chart]({SITE}): the chart and full sortable table
- [latest.json]({SITE}data/latest.json): all rows on the chart as JSON, updated daily

## How to read it

- Popularity rank and token share: how much each model was used on OpenRouter in the latest full UTC day. A token is about three-quarters of a word; both the question and the answer count.
- ECI (Epoch Capabilities Index): Epoch AI's combined benchmark score across math, coding, science and reasoning. Higher means more capable.
- Arena Score: LMArena's Bradley-Terry rating from people voting between two anonymous models' answers (text, overall, style control). Higher means people preferred it more often. Not Elo.
- A dash means that source has no matching entry. The chart does not cover prices.

## Most used (OpenRouter, by token share)

{chr(10).join(f"#{m['pop_rank']} {m['name']}{tag(m)}: {m['share'] * 100:.1f}% of tokens" if m.get('share') is not None else f"#{m['pop_rank']} {m['name']}" for m in pop) or "(no data today)"}

## Highest Epoch Capabilities Index (among models on the chart)

{lines(eci, lambda m: f"{m['name']}{tag(m)}: ECI {m['eci']:.1f}")}

## Highest LMArena Arena Score (among models on the chart)

{lines(arena, lambda m: f"{m['name']}{tag(m)}: {m['arena']:.0f}")}

## Sources (each CC BY 4.0)

- [OpenRouter rankings](https://openrouter.ai/rankings), [Epoch Capabilities Index](https://epoch.ai/eci), [LMArena leaderboard dataset](https://huggingface.co/datasets/lmarena-ai/leaderboard-dataset)
- {src.get('openrouter', {}).get('credit', 'OpenRouter rankings (openrouter.ai/rankings).')}
- {src.get('eci', {}).get('credit', 'Epoch AI, Epoch Capabilities Index (epoch.ai/eci).')}
- {src.get('arena', {}).get('credit', 'LMArena text leaderboard.')}
"""
    write_if_changed(ROOT / "llms.txt", txt)

    lm = f"<lastmod>{day}</lastmod>" if day else ""
    sm = ('<?xml version="1.0" encoding="UTF-8"?>\n'
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
          f"  <url><loc>{SITE}</loc>{lm}</url>\n</urlset>\n")
    write_if_changed(ROOT / "sitemap.xml", sm)


if __name__ == "__main__":
    main()
