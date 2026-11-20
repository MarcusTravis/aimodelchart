#!/usr/bin/env python3
"""Build data/latest.json from OpenRouter rankings, Epoch ECI and LMArena.

Each source is fetched independently. If one fails, the last-good copy stored
in data/sources_cache.json is reused. Scores are never invented: unmatched
cells are null (rendered as an em dash by the page).
"""
import datetime as dt
import io
import json
import os
import re
import sys
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
LATEST = DATA / "latest.json"
CACHE = DATA / "sources_cache.json"
HISTORY = DATA / "history.json"
ALIASES = json.loads((ROOT / "aliases.json").read_text())

OR_URL = "https://openrouter.ai/api/v1/datasets/rankings-daily"
ECI_URL = "https://epoch.ai/data/eci_scores.csv"
ARENA_URL = ("https://huggingface.co/datasets/lmarena-ai/leaderboard-dataset/resolve/main/"
             "text_style_control/latest-00000-of-00001.parquet")
OR_TOP = 50
EXTRA_ECI = 20
EXTRA_ARENA = 20
MAX_ROWS = 60
HISTORY_DAYS = 14


def log(msg):
    print(f"[update_data] {msg}", flush=True)


# ---------- name normalisation ----------
NOISE = {"preview", "latest", "exp", "experimental", "free", "thinking", "instruct", "chat"}


def norm_tokens(name):
    s = name.lower()
    s = s.split("/", 1)[-1]                      # drop provider prefix
    s = re.sub(r":[a-z]+$", "", s)               # :free / :thinking
    s = re.sub(r"\(.*?\)", " ", s)               # arena variant suffix
    s = re.sub(r"(?<!\d)(20\d{2})[-_]?(\d{2})[-_]?(\d{2})(?!\d)", " ", s)  # dates
    s = re.sub(r"(?<=\d)[.\-_](?=\d)", "_", s)    # 4.6 / 4-6 -> 4_6
    s = s.replace("_", " ")
    toks = [t for t in re.split(r"[^a-z0-9]+", s) if t]
    return toks


def key_of(name):
    toks = [t for t in norm_tokens(name) if t not in NOISE]
    k = " ".join(toks)
    return ALIASES["key_aliases"].get(k, k)


def order_free(k):
    return " ".join(sorted(k.split()))


# ---------- fetchers ----------
def fetch_openrouter(today):
    token = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not token:
        raise RuntimeError("OPENROUTER_API_KEY not set")
    last = today - dt.timedelta(days=1)      # yesterday, complete UTC day
    prev = last - dt.timedelta(days=1)
    r = requests.get(OR_URL, params={"start_date": prev.isoformat(), "end_date": last.isoformat()},
                     headers={"Authorization": f"Bearer {token}"}, timeout=60)
    r.raise_for_status()
    j = r.json()
    rows = j.get("data", j) if isinstance(j, dict) else j
    meta = j.get("meta", {}) if isinstance(j, dict) else {}
    per_day = {}
    for row in rows:
        day = str(row.get("date") or row.get("day") or last.isoformat())[:10]
        name = (row.get("model_permaslug") or row.get("permaslug") or row.get("model")
                or row.get("slug") or row.get("model_slug") or "")
        if not name:
            continue
        tok = row.get("total_tokens", row.get("tokens"))
        if tok is None:
            tok = (row.get("prompt_tokens") or 0) + (row.get("completion_tokens") or 0) \
                  + (row.get("reasoning_tokens") or 0)
        d = per_day.setdefault(day, {})
        d[name] = d.get(name, 0) + float(tok or 0)

    def ranked(day):
        d = per_day.get(day, {})
        other = sum(v for k, v in d.items() if k.lower() == "other")
        items = sorted(((k, v) for k, v in d.items() if k.lower() != "other"), key=lambda x: -x[1])
        total = sum(v for _, v in items) + other
        return items, total

    cur, total = ranked(last.isoformat())
    if not cur:
        raise RuntimeError("OpenRouter returned no rows for " + last.isoformat())
    prv, _ = ranked(prev.isoformat())
    prev_rank = {k: i + 1 for i, (k, _) in enumerate(prv)}
    out = []
    for i, (name, tok) in enumerate(cur[:OR_TOP]):
        out.append({"slug": name, "rank": i + 1, "tokens": int(tok),
                    "share": round(tok / total, 5) if total else None,
                    "prev_rank": prev_rank.get(name)})
    return {"as_of": str(meta.get("as_of") or last.isoformat()), "day": last.isoformat(), "rows": out}


def fetch_eci():
    r = requests.get(ECI_URL, timeout=60)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text))
    rows = []
    for _, x in df.iterrows():
        if pd.isna(x.get("eci")):
            continue
        rows.append({"name": x["Display name"], "org": None if pd.isna(x["Organization"]) else x["Organization"],
                     "eci": round(float(x["eci"]), 1),
                     "access": None if pd.isna(x.get("Accessibility group")) else x["Accessibility group"],
                     "released": None if pd.isna(x.get("date")) else str(x["date"])[:10]})
    return {"as_of": dt.date.today().isoformat(), "rows": rows}


def fetch_arena():
    r = requests.get(ARENA_URL, timeout=120)
    r.raise_for_status()
    df = pd.read_parquet(io.BytesIO(r.content))
    df = df[df["category"] == "overall"].sort_values("rank")
    rows = [{"name": x.model_name, "org": x.organization, "license": x.license,
             "rating": round(float(x.rating), 1), "rank": int(x["rank"])}
            for _, x in df.iterrows()]
    as_of = str(df["leaderboard_publish_date"].max())[:10]
    return {"as_of": as_of, "rows": rows}


# ---------- merge ----------
def pretty_from_slug(slug):
    s = slug.split("/", 1)[-1]
    s = re.sub(r":.*$", "", s)
    s = re.sub(r"-?20\d{2}-?\d{2}-?\d{2}$", "", s)
    return " ".join(w if re.search(r"\d", w) else w.capitalize() for w in re.split(r"[-_]", s))


def build(cache):
    orr, eci, arena = cache.get("openrouter"), cache.get("eci"), cache.get("arena")
    index = {}   # order-free key -> entity

    def ent(name):
        k = order_free(key_of(name))
        return index.setdefault(k, {"k": k})

    for r in (eci or {}).get("rows", []):
        e = ent(r["name"])
        if "eci" not in e or r["eci"] > e["eci"]:
            e.update(eci=r["eci"], eci_name=r["name"], org=r["org"], access=r["access"], released=r["released"])
    # Arena: prefer the plain (no variant suffix) entry, otherwise the best-rated variant
    best = {}
    for r in (arena or {}).get("rows", []):
        e = ent(r["name"])
        plain = "(" not in r["name"]
        cur = best.get(e["k"])
        if cur is None or (plain and not cur[0]) or (plain == cur[0] and r["rating"] > cur[1]["rating"]):
            best[e["k"]] = (plain, r)
    for k, (_, r) in best.items():
        e = index[k]
        e.update(arena=r["rating"], arena_rank=r["rank"], arena_name=r["name"], arena_org=r["org"],
                 arena_license=r["license"])
    for r in (orr or {}).get("rows", []):
        e = ent(r["slug"])
        # Dated OpenRouter variants often collapse to one key; keep best rank and sum usage.
        if "or_rank" in e:
            e["tokens"] = int(e.get("tokens") or 0) + int(r["tokens"] or 0)
            e["share"] = round((e.get("share") or 0) + (r.get("share") or 0), 5)
            if r["rank"] < e["or_rank"]:
                e["or_rank"] = r["rank"]
                e["prev_rank"] = r.get("prev_rank")
                e["slug"] = r["slug"]
            continue
        e.update(or_rank=r["rank"], tokens=r["tokens"], share=r["share"], prev_rank=r["prev_rank"],
                 slug=r["slug"])

    ents = list(index.values())
    chosen = {e["k"] for e in ents if "or_rank" in e}
    by_eci = sorted((e for e in ents if "eci" in e), key=lambda e: -e["eci"])
    by_arena = sorted((e for e in ents if "arena" in e), key=lambda e: e["arena_rank"])
    for lst, n in ((by_eci, EXTRA_ECI), (by_arena, EXTRA_ARENA)):
        added = 0
        for e in lst:
            if len(chosen) >= MAX_ROWS or added >= n:
                break
            if e["k"] not in chosen:
                chosen.add(e["k"])
                added += 1
    models = []
    for e in ents:
        if e["k"] not in chosen:
            continue
        slug = e.get("slug")
        name = e.get("eci_name") or (re.sub(r"\s*\(.*?\)\s*$", "", e["arena_name"]) if e.get("arena_name")
                                      else pretty_from_slug(slug))
        org = e.get("org")
        if not org:
            ao = (e.get("arena_org") or "").lower()
            org = ALIASES["maker_display"].get(ao) or (ao.capitalize() if ao else None)
        if not org and slug and "/" in slug:
            pre = slug.split("/")[0]
            org = ALIASES["maker_by_slug_prefix"].get(pre, pre.capitalize())
        acc = e.get("access")
        if acc in ("Closed weights", "Open weights"):
            openness = "Open" if acc.startswith("Open") else "Closed"
        elif e.get("arena_license"):
            openness = "Closed" if e["arena_license"].lower().startswith("propriet") else "Open"
        else:
            openness = None
        models.append({"name": name, "maker": org, "access": openness,
                       "pop_rank": e.get("or_rank"), "tokens": e.get("tokens"), "share": e.get("share"),
                       "rank_change": (e["prev_rank"] - e["or_rank"]) if e.get("prev_rank") and e.get("or_rank") else None,
                       "new_entry": bool(e.get("or_rank") and not e.get("prev_rank") and orr and
                                         any(r["prev_rank"] for r in orr["rows"])),
                       "eci": e.get("eci"), "arena": e.get("arena"), "arena_rank": e.get("arena_rank")})
    models.sort(key=lambda m: (m["pop_rank"] is None, m["pop_rank"] or 0,
                               -(m["eci"] or 0), m["arena_rank"] or 9999))
    sources = {
        "openrouter": {"as_of": (orr or {}).get("as_of"), "available": bool(orr),
                       "credit": f"Source: OpenRouter (openrouter.ai/rankings), as of {(orr or {}).get('as_of')}. Licensed under CC BY 4.0."
                       if orr else "Source: OpenRouter (openrouter.ai/rankings). Licensed under CC BY 4.0. Popularity data currently unavailable."},
        "eci": {"as_of": (eci or {}).get("as_of"), "available": bool(eci),
                "credit": 'Epoch AI, "Epoch Capabilities Index" (epoch.ai/eci). Licensed under CC BY 4.0.'},
        "arena": {"as_of": (arena or {}).get("as_of"), "available": bool(arena),
                  "credit": "LMArena text leaderboard, overall with style control, Arena Score "
                            "(huggingface.co/datasets/lmarena-ai/leaderboard-dataset). Licensed under CC BY 4.0."},
    }
    return {"sources": sources, "models": models}


def main():
    DATA.mkdir(exist_ok=True)
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    today = dt.datetime.now(dt.timezone.utc).date()
    for name, fn in (("openrouter", lambda: fetch_openrouter(today)), ("eci", fetch_eci), ("arena", fetch_arena)):
        try:
            cache[name] = fn()
            log(f"{name}: OK ({len(cache[name]['rows'])} rows, as_of {cache[name]['as_of']})")
        except Exception as e:  # noqa: BLE001
            have = "keeping previous data" if cache.get(name) else "no previous data, columns will be empty"
            log(f"{name}: FAILED ({e}); {have}")
    out = build(cache)
    old = json.loads(LATEST.read_text()) if LATEST.exists() else {}
    changed = {k: v for k, v in old.items() if k != "generated_at"} != out
    out["generated_at"] = (dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                           if changed else old.get("generated_at"))
    if changed:
        LATEST.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
        log(f"wrote {LATEST.name} with {len(out['models'])} models")
    else:
        log("no content change")
    CACHE.write_text(json.dumps(cache, separators=(",", ":"), ensure_ascii=False) + "\n")
    # short history of OpenRouter ranks
    hist = json.loads(HISTORY.read_text()) if HISTORY.exists() else {}
    orr = cache.get("openrouter")
    if orr:
        hist[orr["day"]] = {r["slug"]: r["rank"] for r in orr["rows"][:20]}
        for d in sorted(hist)[:-HISTORY_DAYS]:
            del hist[d]
    HISTORY.write_text(json.dumps(hist, indent=1) + "\n")


if __name__ == "__main__":
    sys.exit(main())
