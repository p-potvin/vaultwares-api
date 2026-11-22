"""Fuzzy duplicate detection for single-video taxonomy entries (replace queue)."""
from __future__ import annotations

from collections import defaultdict
import re
import unicodedata
from typing import Any, Mapping, Sequence

TIER_PRIORITY: dict[str, int] = {"2b": 0, "3": 1, "4a": 2, "4b": 3}

NOISE_TOKENS: frozenset[str] = frozenset({
    "onlyfans", "official", "vip", "real", "xxx", "free", "tv", "xo", "xoxo",
    "model", "fans", "of", "the", "im", "its", "miss", "ms", "mrs",
    "leaked", "leaks", "leak", "videos", "video", "cam", "live", "hub",
    "pornhub", "chaturbate", "camsoda", "xvideos", "xhamster", "twitter", "ig",
    "insta", "instagram", "tiktok", "snap", "snapchat", "patreon", "manyvids",
    "fansly", "fancentro", "loyalfans", "admireme", "justforfans",
})

NOISE_SUFFIX_RE = re.compile(
    r"(onlyfans|official|manyvids|chaturbate|pornhub|xvideos|fansly|loyalfans|"
    r"fancentro|justforfans|vip|xxx|xoxo|xo|tv|real|free|model|fans|leaked|"
    r"leaks|cam|live)$"
)


def strip_accents(value: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", value) if not unicodedata.combining(ch)
    )


def norm_strict(name: str) -> str:
    """Lowercase, strip accents, possessive 's, leading @, and non-alphanumeric chars."""
    s = strip_accents(name).lower().strip()
    s = re.sub(r"['’]s\b", "", s)
    s = s.lstrip("@")
    return re.sub(r"[^a-z0-9]", "", s)


def strip_parens_and_digits(name: str) -> str:
    """Strip parentheticals/brackets, possessive 's, @, digits, and punctuation."""
    s = strip_accents(name).lower().strip()
    s = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", s)
    s = re.sub(r"['’]s\b", "", s)
    s = s.lstrip("@")
    s = re.sub(r"\d+", "", s)
    return re.sub(r"[^a-z]", "", s)


def strip_noise_and_digits(name: str) -> str:
    """Strip parentheticals, digits, noise tokens, and trailing handle suffixes."""
    s = strip_accents(name).lower().strip()
    s = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", s)
    s = re.sub(r"['’]s\b", "", s)
    tokens = re.findall(r"[a-z]+", s)
    filtered = [t for t in tokens if t not in NOISE_TOKENS]
    joined = "".join(filtered) if filtered else "".join(tokens)
    changed = True
    while changed and len(joined) > 6:
        m = NOISE_SUFFIX_RE.search(joined)
        if m and len(joined) - len(m.group(0)) >= 4:
            joined = joined[: m.start()]
        else:
            changed = False
    return joined


def sorted_tokens_key(name: str) -> str:
    """Return sorted alpha tokens (len >= 2) when at least 2 words exist."""
    s = strip_accents(name).lower().strip()
    s = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", s)
    s = re.sub(r"['’]s\b", "", s)
    tokens = [t for t in re.findall(r"[a-z]+", s) if len(t) >= 2]
    if len(tokens) < 2:
        return ""
    return " ".join(sorted(tokens))


def damerau_levenshtein(a: str, b: str, max_dist: int = 2) -> int:
    """Bounded optimal string alignment distance; returns max_dist + 1 when exceeded."""
    if abs(len(a) - len(b)) > max_dist:
        return max_dist + 1
    la, lb = len(a), len(b)
    prev2: list[int] | None = None
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        curr = [i] + [0] * lb
        ai = a[i - 1]
        row_min = i
        for j in range(1, lb + 1):
            cost = 0 if ai == b[j - 1] else 1
            val = min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost)
            if i > 1 and j > 1 and ai == b[j - 2] and a[i - 2] == b[j - 1]:
                val = min(val, prev2[j - 2] + 1)  # type: ignore[index]
            curr[j] = val
            if val < row_min:
                row_min = val
        if row_min > max_dist:
            return max_dist + 1
        prev2 = prev
        prev = curr
    return prev[lb]


def gender_compatible(g1: str | None, g2: str | None) -> bool:
    n1 = (g1 or "unknown").lower()
    n2 = (g2 or "unknown").lower()
    if n1 in ("unknown", "other", "") or n2 in ("unknown", "other", ""):
        return True
    return n1 == n2


def _to_candidate_dict(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "slug": row["slug"],
        "gender": row["gender"],
        "image_url": row["image_url"],
        "video_count": row["vc"],
        "disabled": row["disabled"],
        "undesirable": row["undesirable"],
    }


def _pick_best_target(
    src: dict[str, Any],
    candidates: Sequence[dict[str, Any]],
    *,
    gender_compatible_only: bool,
    multi_video_targets_only: bool,
) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    best_key: tuple[int, int, int, int] | None = None
    src_id = src["id"]
    for c in candidates:
        cid = c["id"]
        if cid == src_id or c["disabled"] or c["undesirable"]:
            continue
        if multi_video_targets_only and c["vc"] < 2:
            continue
        if c["vc"] == 1 and cid > src_id:
            continue
        compat = gender_compatible(src["gender"], c["gender"])
        if gender_compatible_only and not compat:
            continue
        key = (1 if c["vc"] >= 2 else 0, 1 if compat else 0, c["vc"], -cid)
        if best_key is None or key > best_key:
            best_key = key
            best = c
    return best


def compute_fuzzy_replace_queue(
    raw_rows: Sequence[Mapping[str, Any]],
    *,
    tier: str = "all",
    gender_compatible_only: bool = True,
    multi_video_targets_only: bool = False,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """
    Compute candidate replacement pairs across single-video entries for tiers:
      - 2b: noise tokens/handle suffixes stripped
      - 3:  word-order swap (same alpha words reordered)
      - 4a: Damerau-Levenshtein == 1 (len >= 6)
      - 4b: Damerau-Levenshtein == 2 (len >= 9, similarity >= 0.80)
    """
    rows: list[dict[str, Any]] = []
    for r in raw_rows:
        name = str(r["name"])
        rows.append({
            "id": int(r["id"]),
            "name": name,
            "slug": str(r["slug"]),
            "gender": r.get("gender"),
            "image_url": r.get("image_url"),
            "disabled": bool(r.get("disabled", False)),
            "undesirable": bool(r.get("undesirable", False)),
            "vc": int(r.get("video_count", 0)),
            "nodigit": strip_parens_and_digits(name),
            "nonoise": strip_noise_and_digits(name),
            "sorted_tok": sorted_tokens_key(name),
        })

    singles = [r for r in rows if r["vc"] == 1 and not r["undesirable"]]

    idx_nodigit: dict[str, list[dict[str, Any]]] = defaultdict(list)
    idx_nonoise: dict[str, list[dict[str, Any]]] = defaultdict(list)
    idx_sorted_tok: dict[str, list[dict[str, Any]]] = defaultdict(list)
    idx_del1: dict[str, list[dict[str, Any]]] = defaultdict(list)
    idx_exact_nd6: dict[str, list[dict[str, Any]]] = defaultdict(list)
    idx_tri: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for r in rows:
        if r["disabled"] or r["undesirable"] or r["vc"] < 1:
            continue
        nd = r["nodigit"]
        if len(nd) >= 4:
            idx_nodigit[nd].append(r)
        nn = r["nonoise"]
        if len(nn) >= 4:
            idx_nonoise[nn].append(r)
        if r["sorted_tok"]:
            idx_sorted_tok[r["sorted_tok"]].append(r)
        if len(nd) >= 6:
            idx_exact_nd6[nd].append(r)
            for i in range(len(nd)):
                idx_del1[nd[:i] + nd[i + 1 :]].append(r)
        if len(nd) >= 9:
            seen_g: set[str] = set()
            for i in range(len(nd) - 2):
                g = nd[i : i + 3]
                if g not in seen_g:
                    seen_g.add(g)
                    idx_tri[g].append(r)

    q_lower = search.strip().lower() if search and search.strip() else None
    all_items: list[dict[str, Any]] = []
    counts_by_tier: dict[str, int] = {"2b": 0, "3": 0, "4a": 0, "4b": 0}
    filter_kwargs = {
        "gender_compatible_only": gender_compatible_only,
        "multi_video_targets_only": multi_video_targets_only,
    }

    for src in singles:
        sid = src["id"]
        nd = src["nodigit"]
        nn = src["nonoise"]
        matched_tier: str | None = None
        target: dict[str, Any] | None = None
        reason = ""
        similarity = 1.0

        # Tier 2b: noise tokens/suffixes stripped (excluding identical clean nodigit pairs)
        if len(nn) >= 4:
            cands_2b = [
                c for c in (idx_nonoise.get(nn, []) + idx_nodigit.get(nn, []))
                if c["nodigit"] != nd or nn != nd
            ]
            # Avoid duplicating clean Tier 2a pairs where both names have identical alpha-only strings
            # and neither contains noise tokens/suffixes.
            cands_2b = [c for c in cands_2b if c["nonoise"] != c["nodigit"] or nn != nd]
            t = _pick_best_target(src, cands_2b, **filter_kwargs)
            if t is not None:
                matched_tier = "2b"
                target = t
                reason = "Noise / handle suffix match"
                similarity = 1.0

        # Tier 3: word-order swap
        if target is None and src["sorted_tok"]:
            cands_3 = [
                c for c in idx_sorted_tok.get(src["sorted_tok"], ())
                if c["nodigit"] != nd
            ]
            t = _pick_best_target(src, cands_3, **filter_kwargs)
            if t is not None:
                matched_tier = "3"
                target = t
                reason = "Word-order swap"
                similarity = 1.0

        # Tier 4a: Damerau-Levenshtein == 1 (len >= 6)
        if target is None and len(nd) >= 6:
            cm: dict[int, dict[str, Any]] = {}
            for c in idx_del1.get(nd, ()):
                cm[c["id"]] = c
            for i in range(len(nd)):
                d1 = nd[:i] + nd[i + 1 :]
                for c in idx_exact_nd6.get(d1, ()):
                    cm[c["id"]] = c
                for c in idx_del1.get(d1, ()):
                    cm[c["id"]] = c
            valid_4a = [
                c for c in cm.values()
                if c["id"] != sid
                and c["nodigit"] != nd
                and damerau_levenshtein(nd, c["nodigit"], 1) == 1
            ]
            t = _pick_best_target(src, valid_4a, **filter_kwargs)
            if t is not None:
                max_l = max(len(nd), len(t["nodigit"]))
                matched_tier = "4a"
                target = t
                similarity = round((max_l - 1) / max_l, 3)
                reason = f"1-char difference ({int(round(similarity * 100))}% match)"

        # Tier 4b: Damerau-Levenshtein == 2 (len >= 9, similarity >= 0.80)
        if target is None and len(nd) >= 9:
            L = len(nd)
            chunks = (nd[:3], nd[L // 3 : L // 3 + 3], nd[2 * L // 3 : 2 * L // 3 + 3])
            cm = {}
            for ch in chunks:
                for c in idx_tri.get(ch, ()):
                    if abs(len(c["nodigit"]) - L) <= 2:
                        cm[c["id"]] = c
            valid_4b: list[dict[str, Any]] = []
            for c in cm.values():
                if c["id"] == sid or c["nodigit"] == nd:
                    continue
                d = damerau_levenshtein(nd, c["nodigit"], 2)
                if d == 2:
                    max_l = max(L, len(c["nodigit"]))
                    if (max_l - d) / max_l >= 0.80:
                        valid_4b.append(c)
            t = _pick_best_target(src, valid_4b, **filter_kwargs)
            if t is not None:
                max_l = max(L, len(t["nodigit"]))
                matched_tier = "4b"
                target = t
                similarity = round((max_l - 2) / max_l, 3)
                reason = f"2-char difference ({int(round(similarity * 100))}% match)"

        if target is None or matched_tier is None:
            continue

        if q_lower:
            hay = f"{src['name']} {src['slug']} {target['name']} {target['slug']}".lower()
            if q_lower not in hay:
                continue

        counts_by_tier[matched_tier] += 1
        if tier != "all" and matched_tier != tier:
            continue

        all_items.append({
            "source": _to_candidate_dict(src),
            "target": _to_candidate_dict(target),
            "tier": matched_tier,
            "reason": reason,
            "similarity": similarity,
            "gender_compatible": gender_compatible(src["gender"], target["gender"]),
        })

    all_items.sort(
        key=lambda item: (
            TIER_PRIORITY.get(item["tier"], 99),
            -item["target"]["video_count"],
            item["source"]["name"].lower(),
            item["source"]["id"],
        )
    )

    total = len(all_items)
    sliced = all_items[offset : offset + limit]
    return {
        "total": total,
        "counts_by_tier": counts_by_tier,
        "items": sliced,
    }
