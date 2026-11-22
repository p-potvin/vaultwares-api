"""High-performance taxonomy classifier for Prom-King ingestion & backfills."""
from __future__ import annotations

from enum import Enum
import logging
import re
from typing import Dict, Optional, Set, Tuple

from .dictionaries import (
    CATEGORY_STEMS,
    CATEGORY_SYNONYMS,
    KNOWN_STUDIOS,
    clean_title_for_search,
    extract_categories_from_title,
)

logger = logging.getLogger(__name__)

_PORNSTAR_STOPWORDS: Set[str] = {
    "a", "an", "and", "are", "as", "at", "be", "been", "being", "but", "by",
    "can", "did", "do", "does", "done", "for", "from", "get", "gets", "getting",
    "got", "had", "has", "have", "having", "he", "her", "hers", "him", "his",
    "how", "i", "if", "in", "into", "is", "it", "its", "just", "like", "me",
    "more", "most", "my", "no", "not", "now", "of", "off", "on", "only", "or",
    "our", "out", "over", "own", "she", "so", "some", "such", "than", "that",
    "the", "their", "them", "then", "there", "these", "they", "this", "those",
    "through", "to", "too", "under", "up", "very", "was", "we", "were", "what",
    "when", "where", "which", "while", "who", "whom", "why", "will", "with",
    "you", "your", "yours",
    # Common non-performer tube/OF words that slip into title/tag heuristics
    "onlyfans", "fansly", "pornhub", "xvideos", "xhamster", "spankbang", "redtube",
    "tiktok", "twitter", "instagram", "snapchat", "reddit", "youtube", "patreon",
    "video", "videos", "clip", "clips", "scene", "scenes", "part", "full", "free",
    "leaked", "leak", "leaks", "new", "best", "real", "official", "premium",
    "private", "exclusive", "custom", "request", "content", "update", "post",
    "model", "models", "performer", "actor", "actress", "pornstar", "pornstars",
    "studio", "studios", "channel", "network", "unknown", "none", "null", "admin",
    "boy", "girl", "girls", "babe", "babes", "woman", "women", "man", "men",
    "guy", "guys", "couple", "solo", "lesbian", "gay", "bi", "trans",
    "amateur", "homemade", "verified", "raw", "uncensored", "hd", "4k", "60fps",
    "pov", "joi", "asmr", "pmv", "comp", "compilation", "tease", "preview",
    "trailer", "promo", "intro", "outro", "bonus", "extra", "special",
    "fuck", "fucking", "fucked", "suck", "sucking", "sucks", "ride", "riding",
    "rides", "cum", "cumming", "creampie", "blowjob", "handjob", "footjob",
    "titfuck", "titty", "tits", "ass", "pussy", "dick", "cock", "boobs", "boob",
    "hard", "wet", "deep", "anal", "oral", "hot", "sexy", "cute", "white",
    "black", "asian", "latina", "ebony", "blonde", "brunette", "redhead",
    "naked", "nude", "nudes", "dirty", "naughty", "horny", "sloppy", "huge",
    "big", "small", "tiny", "thick", "slim", "petite", "curvy", "tall",
    "tit", "dildo", "masturb", "masturbate", "masturbating", "masturbation",
    "live", "tryon", "try", "machine", "deutsch", "german", "french",
    "spanish", "russian", "italian", "cam", "cams", "beauty", "twitch",
    "patreon", "snap", "telegram", "discord", "vids", "vid", "sextape",
    "sex", "porn", "xxx", "nsfw", "ppv", "customs", "cloud", "original",
    "quality", "saved", "subscribe", "sub", "link", "links", "bio", "dm",
    "tribute", "cumshot", "orgasm", "squirt", "squirting", "doggystyle",
    "cowgirl", "missionary", "deepthroat", "gagging", "threesome", "orgy",
    "gangbang", "cuckold", "fetish", "bdsm", "lingerie", "costume",
    "cosplay", "twerk", "twerking", "flash", "flashing", "teasing", "strip",
    "stripping", "striptease", "bg", "gg", "bgg", "ffm", "mmf", "irl",
    "vlog", "stream", "livestream", "recording", "replay", "archive",
    "mega", "folder", "pack", "collection", "shower", "pool", "office",
    "car", "balcony", "work", "after", "vodka", "begs", "sleepy", "see",
    "through", "wonder", "bare", "onlyfansthreesome",
}

_NAME_LETTERS_RE = re.compile(r"[A-Za-z]")
_NOISE_PREFIX_RE = re.compile(r"^(?:https?://|www\.|#|@|\d+$)", re.IGNORECASE)
_LEADING_FILLER_WORDS: Set[str] = {
    "a", "an", "and", "after", "at", "big", "by", "for", "from", "full",
    "her", "his", "hot", "in", "into", "my", "naked", "nude", "of", "on",
    "or", "our", "over", "see", "sexy", "she", "solo", "anal", "that",
    "the", "their", "these", "this", "those", "to", "try", "under", "with",
    "your",
}


_EXTRA_SINGLE_WORD_STOPWORDS: Set[str] = {
    "baby", "bad", "bazooka", "blue", "bunny", "doll", "fox", "jo", "lo",
    "lucky", "pink", "rain", "red", "rivers", "rockelle", "rose", "sab", "star", "sweet",
}

def is_valid_pornstar_name(raw: str) -> bool:
    """Reject pronouns, filler stopwords, URLs, and multi-word sentence fragments."""
    clean = " ".join((raw or "").strip().split())
    if len(clean) < 3 or len(clean) > 48:
        return False
    if _NOISE_PREFIX_RE.match(clean):
        return False
    if len(_NAME_LETTERS_RE.findall(clean)) < 2:
        return False
    words = clean.split()
    if len(words) > 4:
        return False
    lowered_words = [re.sub(r"[^a-z0-9']", "", w.lower()) for w in words]
    if not any(lowered_words) or all((not w or w in _PORNSTAR_STOPWORDS) for w in lowered_words):
        return False
    if clean.lower() in _PORNSTAR_STOPWORDS or (len(words) == 1 and lowered_words[0] in _EXTRA_SINGLE_WORD_STOPWORDS):
        return False
    if len(words) == 1:
        sub_tokens = [re.sub(r"[^a-z0-9']", "", t.lower()) for t in re.split(r"[-_]+", clean) if t]
        if len(sub_tokens) > 1 and all((not t or t in _PORNSTAR_STOPWORDS) for t in sub_tokens):
            return False
        if lowered_words[0] in _PORNSTAR_STOPWORDS:
            return False
    else:
        # Reject title fragments starting with a single bare letter ("l b", "l video", "r dildo", "o f", "a h")
        # or starting with filler words ("the office", "in shower", "my pussy", "after work").
        if len(lowered_words[0]) <= 1 or lowered_words[0] in _LEADING_FILLER_WORDS:
            return False
        # Reject bare lowercase single-letter trailing word ("solo p", "anal p")
        if any(len(lw) == 1 and w == w.lower() for w, lw in zip(words[1:], lowered_words[1:])):
            return False
        # Reject all-lowercase multi-word descriptions containing any stopword/tag word
        if clean == clean.lower():
            all_parts = [re.sub(r"[^a-z0-9']", "", t) for t in re.split(r"[\s\-_]+", clean) if t]
            if any(p in _PORNSTAR_STOPWORDS for p in all_parts):
                return False
    return True


class TermKind(str, Enum):
    CATEGORY = "category"
    STUDIO = "studio"
    PORNSTAR = "pornstar"
    UNKNOWN = "unknown"


class TaxonomyClassifier:
    """Classifies scraped tags and titles into categories, studios, and pornstars.

    Prioritizes local DB tables and dictionaries offline to avoid unnecessary
    network requests. Isolates category keywords so they never leak into
    studios or performers.
    """

    def __init__(
        self,
        db_pornstars: Optional[Set[str]] = None,
        db_studios: Optional[Set[str]] = None,
        db_categories: Optional[Set[str]] = None,
    ):
        valid_pornstars = {p for p in (db_pornstars or set()) if is_valid_pornstar_name(p)}
        # Case-insensitive normalized sets from DB
        self.db_pornstars: Set[str] = {p.lower() for p in valid_pornstars}
        self.db_studios: Set[str] = {s.lower() for s in (db_studios or set())}
        self.db_categories: Set[str] = {c.lower() for c in (db_categories or set())}

        # Keep map of lower -> exact original DB casing
        self.pornstar_display: Dict[str, str] = {p.lower(): p for p in valid_pornstars}
        self.studio_display: Dict[str, str] = {s.lower(): s for s in (db_studios or set())}
        self.category_display: Dict[str, str] = {c.lower(): c for c in (db_categories or set())}

    @classmethod
    async def load_from_db(cls, conn) -> TaxonomyClassifier:
        """Load known taxonomies from the live Postgres connection."""
        p_rows = await conn.fetch("SELECT name FROM pornstars WHERE deleted_at IS NULL AND undesirable = false")
        s_rows = await conn.fetch("SELECT name FROM studios WHERE deleted_at IS NULL AND undesirable = false")
        c_rows = await conn.fetch("SELECT name FROM categories WHERE deleted_at IS NULL AND undesirable = false")

        return cls(
            db_pornstars={r["name"] for r in p_rows},
            db_studios={r["name"] for r in s_rows},
            db_categories={r["name"] for r in c_rows},
        )

    def is_category(self, raw_name: str) -> bool:
        """Check if term matches known category synonyms, DB categories, or category stems."""
        norm = raw_name.strip().lower()
        if not norm:
            return False
        if norm in CATEGORY_SYNONYMS or norm in self.db_categories or norm in CATEGORY_STEMS:
            return True

        # Check multi-word tokens: if entire term is composed of category stems (e.g. "big tits", "anal creampie")
        words = norm.split()
        if len(words) <= 3 and all(w in CATEGORY_STEMS for w in words):
            return True

        return False

    def get_canonical_category(self, raw_name: str) -> str:
        """Return canonical category name."""
        norm = raw_name.strip().lower()
        if norm in CATEGORY_SYNONYMS:
            return CATEGORY_SYNONYMS[norm]
        if norm in self.category_display:
            return self.category_display[norm]
        return raw_name.strip().title()

    def classify_term(
        self,
        name: str,
        hint: Optional[str] = None,
    ) -> Tuple[TermKind, str]:
        """Classify a single term into Category, Studio, or Pornstar.

        Guarantees:
        1. Category terms are NEVER assigned to studios or pornstars.
        2. Known pornstars are routed to Pornstar even if tagged as studio.
        3. Known studios are routed to Studio.
        """
        clean_name = name.strip()
        if not clean_name:
            return TermKind.UNKNOWN, ""

        norm = clean_name.lower()

        # 1. CATEGORY ISOLATION RULE:
        # If it matches any category pattern, it is 100% a Category.
        if self.is_category(clean_name):
            return TermKind.CATEGORY, self.get_canonical_category(clean_name)

        # 2. KNOWN PORNSTAR CHECK:
        # If the term matches a known performer in our DB, it IS a performer,
        # even if the tube card marked it as a studio (e.g. Angela White, Manuel Ferrara).
        # Never promote a single-word generic category/tag token (e.g. from /tags/ word lists)
        # into a performer unless it is multi-word or came from an explicit performer/studio field.
        if norm in self.db_pornstars and (hint != "category" or " " in norm):
            return TermKind.PORNSTAR, self.pornstar_display[norm]

        # 3. KNOWN STUDIO CHECK:
        if norm in KNOWN_STUDIOS:
            return TermKind.STUDIO, self.studio_display.get(norm, clean_name.title())
        if norm in self.db_studios:
            return TermKind.STUDIO, self.studio_display[norm]

        # 4. HINT EVALUATION FOR UNKNOWN TERMS:
        if hint == "pornstar":
            if not is_valid_pornstar_name(clean_name):
                return TermKind.UNKNOWN, clean_name
            return TermKind.PORNSTAR, clean_name
        if hint == "studio":
            return TermKind.STUDIO, clean_name
        if hint == "category":
            return TermKind.CATEGORY, self.get_canonical_category(clean_name)

        # If unknown and looks like a person's name (2-3 words, capitalized, no punctuation/digits)
        words = clean_name.split()
        if 2 <= len(words) <= 3 and all(w[0].isupper() and w.isalpha() for w in words):
            return TermKind.PORNSTAR, clean_name

        return TermKind.UNKNOWN, clean_name

    def classify_video_tags(
        self,
        title: str,
        categories: list[str],
        pornstars: list[str],
        studios: list[str],
    ) -> Tuple[list[str], list[str], list[str]]:
        """Sort and deduplicate all incoming raw terms into proper taxonomy buckets.

        Ensures category terms never leak into studios or performers, reclaims
        performers misfiled as studios, and falls back to title category mining
        if categories are empty.
        """
        out_categories: list[str] = []
        out_pornstars: list[str] = []
        out_studios: list[str] = []

        seen_cats: Set[str] = set()
        seen_porn: Set[str] = set()
        seen_stud: Set[str] = set()

        def add_category(cat: str):
            c_norm = cat.lower()
            if c_norm not in seen_cats:
                seen_cats.add(c_norm)
                out_categories.append(cat)

        def add_pornstar(star: str):
            p_norm = star.lower()
            if p_norm not in seen_porn:
                seen_porn.add(p_norm)
                out_pornstars.append(star)

        def add_studio(stud: str):
            s_norm = stud.lower()
            if s_norm not in seen_stud:
                seen_stud.add(s_norm)
                out_studios.append(stud)

        # Process categories
        for raw in categories:
            kind, val = self.classify_term(raw, hint="category")
            if kind == TermKind.CATEGORY:
                add_category(val)
            elif kind == TermKind.PORNSTAR:
                add_pornstar(val)
            elif kind == TermKind.STUDIO:
                add_studio(val)

        # Process studios (reclaim misfiled performers)
        for raw in studios:
            kind, val = self.classify_term(raw, hint="studio")
            if kind == TermKind.CATEGORY:
                add_category(val)
            elif kind == TermKind.PORNSTAR:
                add_pornstar(val)
            elif kind == TermKind.STUDIO:
                add_studio(val)

        # Process pornstars
        for raw in pornstars:
            kind, val = self.classify_term(raw, hint="pornstar")
            if kind == TermKind.CATEGORY:
                add_category(val)
            elif kind == TermKind.STUDIO:
                add_studio(val)
            elif kind == TermKind.PORNSTAR:
                add_pornstar(val)

        # Drop single-word performer tokens that are already covered by a full
        # multi-word performer name on the same video (e.g. ["Ella", "Ella Alexandra", "Alexandra"]).
        multi_word_parts: Set[str] = set()
        for star in out_pornstars:
            parts = [p.lower() for p in star.split() if len(p) >= 2]
            if len(parts) >= 2:
                multi_word_parts.update(parts)
        if multi_word_parts:
            out_pornstars = [
                star
                for star in out_pornstars
                if " " in star or star.strip().lower() not in multi_word_parts
            ]

        # Fallback: if categories are empty, mine directly from title!
        if not out_categories and title:
            for mined in extract_categories_from_title(title):
                add_category(mined)

        return out_categories, out_pornstars, out_studios
