"""High-performance taxonomy classifier for Prom-King ingestion & backfills."""
from __future__ import annotations

from enum import Enum
import logging
from typing import Dict, Optional, Set, Tuple

from .dictionaries import (
    CATEGORY_STEMS,
    CATEGORY_SYNONYMS,
    KNOWN_STUDIOS,
    clean_title_for_search,
    extract_categories_from_title,
)

logger = logging.getLogger(__name__)


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
        # Case-insensitive normalized sets from DB
        self.db_pornstars: Set[str] = {p.lower() for p in (db_pornstars or set())}
        self.db_studios: Set[str] = {s.lower() for s in (db_studios or set())}
        self.db_categories: Set[str] = {c.lower() for c in (db_categories or set())}

        # Keep map of lower -> exact original DB casing
        self.pornstar_display: Dict[str, str] = {p.lower(): p for p in (db_pornstars or set())}
        self.studio_display: Dict[str, str] = {s.lower(): s for s in (db_studios or set())}
        self.category_display: Dict[str, str] = {c.lower(): c for c in (db_categories or set())}

    @classmethod
    async def load_from_db(cls, conn) -> TaxonomyClassifier:
        """Load known taxonomies from the live Postgres connection."""
        p_rows = await conn.fetch("SELECT name FROM pornstars WHERE deleted_at IS NULL")
        s_rows = await conn.fetch("SELECT name FROM studios WHERE deleted_at IS NULL")
        c_rows = await conn.fetch("SELECT name FROM categories WHERE deleted_at IS NULL")

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
        if norm in self.db_pornstars:
            return TermKind.PORNSTAR, self.pornstar_display[norm]

        # 3. KNOWN STUDIO CHECK:
        if norm in KNOWN_STUDIOS:
            return TermKind.STUDIO, self.studio_display.get(norm, clean_name.title())
        if norm in self.db_studios:
            return TermKind.STUDIO, self.studio_display[norm]

        # 4. HINT EVALUATION FOR UNKNOWN TERMS:
        if hint == "pornstar":
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

        # Fallback: if categories are empty, mine directly from title!
        if not out_categories and title:
            for mined in extract_categories_from_title(title):
                add_category(mined)

        return out_categories, out_pornstars, out_studios
