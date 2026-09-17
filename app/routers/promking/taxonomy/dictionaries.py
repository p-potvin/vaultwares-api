"""Curated adult taxonomies, synonym mappings, and text normalizers."""
from __future__ import annotations

import re
from typing import Dict, List, Set

# Canonical category mapping (lowercase synonym / alias -> Canonical Title Case)
CATEGORY_SYNONYMS: Dict[str, str] = {
    # Acts & Practices
    "anal": "Anal",
    "anal sex": "Anal",
    "anal creampie": "Anal Creampie",
    "ass to mouth": "Ass to Mouth",
    "atm": "Ass to Mouth",
    "blowjob": "Blowjob",
    "blowjobs": "Blowjob",
    "blow job": "Blowjob",
    "bj": "Blowjob",
    "deepthroat": "Deepthroat",
    "deep throat": "Deepthroat",
    "creampie": "Creampie",
    "creampies": "Creampie",
    "cream pie": "Creampie",
    "cumshot": "Cumshot",
    "cumshots": "Cumshot",
    "cum shot": "Cumshot",
    "facial": "Facial",
    "facials": "Facial",
    "masturbation": "Masturbation",
    "handjob": "Handjob",
    "handjobs": "Handjob",
    "hand job": "Handjob",
    "fingering": "Fingering",
    "squirt": "Squirting",
    "squirting": "Squirting",
    "pussy licking": "Pussy Licking",
    "cunnilingus": "Pussy Licking",
    "eating pussy": "Pussy Licking",
    "titfuck": "Titfuck",
    "tit fuck": "Titfuck",
    "paizuri": "Titfuck",
    "doggystyle": "Doggystyle",
    "doggy style": "Doggystyle",
    "doggy": "Doggystyle",
    "cowgirl": "Cowgirl",
    "reverse cowgirl": "Reverse Cowgirl",
    "missionary": "Missionary",
    "rough sex": "Rough Sex",
    "hardcore": "Hardcore",
    "softcore": "Softcore",
    "double penetration": "Double Penetration",
    "dp": "Double Penetration",
    "gangbang": "Gangbang",
    "gang bang": "Gangbang",
    "orgy": "Orgy",
    "threesome": "Threesome",
    "threesomes": "Threesome",
    "foursome": "Foursome",
    "group sex": "Group Sex",
    "group": "Group Sex",
    "swallow": "Swallowing",
    "swallowing": "Swallowing",
    "gloryhole": "Gloryhole",
    "glory hole": "Gloryhole",
    "pegging": "Pegging",
    "rimming": "Rimming",
    "facesitting": "Facesitting",
    "face sitting": "Facesitting",

    # Attributes & Types
    "amateur": "Amateur",
    "amateurs": "Amateur",
    "verified amateurs": "Amateur",
    "homemade": "Amateur",
    "big tits": "Big Tits",
    "big boobs": "Big Tits",
    "huge tits": "Big Tits",
    "huge boobs": "Big Tits",
    "busty": "Big Tits",
    "small tits": "Small Tits",
    "natural tits": "Natural Tits",
    "big ass": "Big Ass",
    "fat ass": "Big Ass",
    "big booty": "Big Ass",
    "milf": "MILF",
    "milfs": "MILF",
    "mature": "Mature",
    "granny": "Granny",
    "gilf": "Granny",
    "teen": "Teen (18+)",
    "teens": "Teen (18+)",
    "18+": "Teen (18+)",
    "college": "College",
    "petite": "Petite",
    "bbw": "BBW",
    "chubby": "Chubby",
    "blonde": "Blonde",
    "blondes": "Blonde",
    "brunette": "Brunette",
    "brunettes": "Brunette",
    "redhead": "Redhead",
    "redheads": "Redhead",
    "ebony": "Ebony",
    "asian": "Asian",
    "latina": "Latina",
    "latinas": "Latina",
    "indian": "Indian",
    "interracial": "Interracial",
    "tattoo": "Tattoo",
    "tattooed": "Tattoo",
    "piercing": "Piercing",
    "piercings": "Piercing",
    "pregnant": "Pregnant",
    "shaved": "Shaved",
    "hairy": "Hairy",
    "trans": "Transgender",
    "transgender": "Transgender",
    "shemale": "Transgender",
    "ts": "Transgender",
    "ladyboy": "Transgender",

    # Fetish & Themes
    "fetish": "Fetish",
    "bdsm": "BDSM",
    "bondage": "Bondage",
    "spanking": "Spanking",
    "femdom": "Femdom",
    "female domination": "Femdom",
    "foot fetish": "Foot Fetish",
    "feet": "Foot Fetish",
    "lingerie": "Lingerie",
    "stockings": "Stockings",
    "nylon": "Stockings",
    "high heels": "High Heels",
    "heels": "High Heels",
    "oil": "Oiled",
    "oiled": "Oiled",
    "massage": "Massage",
    "nuru": "Nuru Massage",
    "public": "Public",
    "public nudity": "Public",
    "outdoor": "Outdoor",
    "outdoors": "Outdoor",
    "voyeur": "Voyeur",
    "candid": "Voyeur",
    "hidden cam": "Hidden Cam",
    "pov": "POV",
    "p.o.v.": "POV",
    "vr": "VR Porn",
    "virtual reality": "VR Porn",
    "cosplay": "Cosplay",
    "striptease": "Striptease",
    "strip": "Striptease",
    "casting": "Casting",
    "audition": "Casting",
    "interview": "Interview",
    "first time": "First Time",
    "cheating": "Cheating",
    "cuckold": "Cuckold",
    "hotwife": "Hotwife",
    "wife": "Wife",
    "taboo": "Taboo",
    "stepmom": "Stepmom",
    "step mom": "Stepmom",
    "stepsister": "Stepsister",
    "step sister": "Stepsister",
    "stepdaughter": "Stepdaughter",
    "step daughter": "Stepdaughter",
    "stepson": "Stepson",
    "stepbrother": "Stepbrother",
    "stepdad": "Stepdad",
    "family": "Taboo",
    "lesbian": "Lesbian",
    "lesbians": "Lesbian",
    "solo": "Solo",
    "solo female": "Solo",
    "female orgasm": "Female Orgasm",
    "screaming orgasm": "Female Orgasm",
    "compilation": "Compilation",
    "behind the scenes": "Behind The Scenes",
    "bts": "Behind The Scenes",
    "parody": "Parody",
    "anime": "Hentai",
    "hentai": "Hentai",
}

# Fast lookup set of words/phrases that strictly belong to Categories.
# Any candidate term matching these can NEVER be treated as a studio or pornstar.
CATEGORY_STEMS: Set[str] = {k.lower() for k in CATEGORY_SYNONYMS.keys()} | {
    "sex", "cum", "pussy", "dick", "cock", "boobs", "tits", "ass", "butt",
    "fuck", "fucking", "screwing", "banging", "sucking", "licking",
    "oral", "anal", "vagina", "dildo", "strap-on", "toy", "toys",
    "milf", "granny", "teen", "teens", "18+", "blonde", "brunette",
    "redhead", "ebony", "asian", "latina", "creampie", "blowjob",
    "handjob", "footjob", "titfuck", "facial", "cumshot", "deepthroat",
    "gangbang", "threesome", "foursome", "orgy", "doggystyle", "cowgirl",
    "pov", "vr", "fetish", "bdsm", "bondage", "spanking", "femdom",
    "feet", "foot", "nylon", "stockings", "lingerie", "massage",
    "amateur", "homemade", "casting", "cheating", "cuckold", "hotwife",
    "stepmom", "stepsister", "stepdaughter", "lesbian", "solo", "squirt",
    "squirting", "hardcore", "softcore", "public", "outdoor"
}

# Major known adult studios & networks
KNOWN_STUDIOS: Set[str] = {
    "brazzers", "blacked", "blacked raw", "tushy", "tushy raw", "vixen",
    "deeper", "slay", "naughty america", "reality kings", "bangbros",
    "bang bros", "evil angel", "digital playground", "wicked pictures",
    "wicked", "hustler", "penthouse", "twistys", "moms teach sex",
    "teamske", "team ske", "mofos", "babes", "rk prime", "property sex",
    "milfed", "joymii", "atk", "atk girl", "atk girlfriends", "atk hairy",
    "atk galleria", "pure mature", "sweet sinner", "reality junkies",
    "nubiles", "nubiles porn", "nubiles-casting", "brattysis", "bratty sis",
    "pervmom", "perv mom", "family strokes", "step siblings caught",
    "shoplyfter", "mylf", "mylf labs", "pure taboo", "lubed", "throated",
    "pornstar platinum", "legal porno", "legalporno", "analvids",
    "metart", "met-art", "viv thomas", "private", "private black",
    "mariska", "eroticax", "erotica x", "passion hd", "fantasy hd",
    "fake hub", "fake taxi", "fake hospital", "fake hostel", "fake agent",
    "drilling girls", "cumlouder", "cum louder", "jays pov", "jayspov",
    "onlyfans", "manyvids", "pornfidelity", "teenfidelity", "kelly madison",
    "girlsway", "sweetsinner", "darex", "sexmex", "woodman casting x",
    "rocco siffredi", "roccosiffredi", "tony rubino", "bellesa",
    "colette", "dorcel", "marc dorcel", "suicidegirls", "suicide girls"
}

# Regex to strip video title noise before TPDB scene search
_RE_RESOLUTION = re.compile(r"\b(1080p|720p|480p|360p|2160p|4k|8k|uhd|fhd|hd|sd)\b", re.IGNORECASE)
_RE_BRACKETS = re.compile(r"\[.*?\]|\(.*?\)", re.IGNORECASE)
_RE_EXTENSIONS = re.compile(r"\.(mp4|m4v|mkv|wmv|avi|flv|webm|mov)$", re.IGNORECASE)
_RE_DOMAINS = re.compile(
    r"\b(pxp\.cool|pornxp(\.com|\.cool)?|1porn(\.tv)?|fullvideos(\.xxx)?|fullxxx(\.video)?)\b",
    re.IGNORECASE
)
_RE_NOISE_WORDS = re.compile(
    r"\b(full\s+video|free\s+porn|watch\s+online|streaming|download|xxx\s+video|new\s+video|x264|x265|hevc|aac)\b",
    re.IGNORECASE
)
_RE_LEADING_PREFIX = re.compile(r"^[a-zA-Z0-9.\-_]+\.(com|tv|cool|xxx|video|net|org)\s*[-:|]\s*", re.IGNORECASE)
_RE_MULTIPLE_SPACES = re.compile(r"\s+")


def clean_title_for_search(title: str) -> str:
    """Clean tube title to extract the core scene name for TPDB searching.

    Removes resolutions (1080p, 4K), format tags ([FullHD], (HD)), site
    prefixes (pornxp.cool - ), file extensions (.mp4), and noisy filler words.
    """
    if not title:
        return ""

    t = title.strip()
    t = _RE_EXTENSIONS.sub("", t)
    t = _RE_LEADING_PREFIX.sub("", t)
    t = _RE_BRACKETS.sub(" ", t)
    t = _RE_RESOLUTION.sub(" ", t)
    t = _RE_DOMAINS.sub(" ", t)
    t = _RE_NOISE_WORDS.sub(" ", t)
    # Strip standalone symbols and dashes
    t = re.sub(r"[-_/|:;,+]+", " ", t)
    t = _RE_MULTIPLE_SPACES.sub(" ", t).strip()
    return t


# Precompiled regex patterns for high-speed category mining from titles
_COMPILED_CATEGORY_PATTERNS: List[tuple[re.Pattern, str]] = [
    # Multi-word specific terms first
    (re.compile(r"\bbig\s+(?:tits?|boobs?|titties)\b", re.IGNORECASE), "Big Tits"),
    (re.compile(r"\bhuge\s+(?:tits?|boobs?)\b", re.IGNORECASE), "Big Tits"),
    (re.compile(r"\bbusty\b", re.IGNORECASE), "Big Tits"),
    (re.compile(r"\bsmall\s+(?:tits?|boobs?)\b", re.IGNORECASE), "Small Tits"),
    (re.compile(r"\bnatural\s+(?:tits?|boobs?)\b", re.IGNORECASE), "Natural Tits"),
    (re.compile(r"\bbig\s+(?:ass|booty|butt)\b", re.IGNORECASE), "Big Ass"),
    (re.compile(r"\bfat\s+ass\b", re.IGNORECASE), "Big Ass"),
    (re.compile(r"\banal\s+creampies?\b", re.IGNORECASE), "Anal Creampie"),
    (re.compile(r"\bass\s+to\s+mouth\b|\batm\b", re.IGNORECASE), "Ass to Mouth"),
    (re.compile(r"\bdeep\s*throats?\b|\bdeepthroating\b", re.IGNORECASE), "Deepthroat"),
    (re.compile(r"\bcream\s*pies?\b", re.IGNORECASE), "Creampie"),
    (re.compile(r"\bblow\s*jobs?\b|\bbj\b", re.IGNORECASE), "Blowjob"),
    (re.compile(r"\bhand\s*jobs?\b", re.IGNORECASE), "Handjob"),
    (re.compile(r"\btit\s*fucks?\b|\bpaizuri\b", re.IGNORECASE), "Titfuck"),
    (re.compile(r"\bpussy\s+licking\b|\bcunnilingus\b", re.IGNORECASE), "Pussy Licking"),
    (re.compile(r"\bdoggy\s*styles?\b", re.IGNORECASE), "Doggystyle"),
    (re.compile(r"\breverse\s+cowgirl\b", re.IGNORECASE), "Reverse Cowgirl"),
    (re.compile(r"\bcowgirl\b", re.IGNORECASE), "Cowgirl"),
    (re.compile(r"\bmissionary\b", re.IGNORECASE), "Missionary"),
    (re.compile(r"\bdouble\s+penetration\b|\bdp\b", re.IGNORECASE), "Double Penetration"),
    (re.compile(r"\bgang\s*bangs?\b", re.IGNORECASE), "Gangbang"),
    (re.compile(r"\bthreesomes?\b", re.IGNORECASE), "Threesome"),
    (re.compile(r"\bfoursomes?\b", re.IGNORECASE), "Foursome"),
    (re.compile(r"\borgy\b|\borgies\b", re.IGNORECASE), "Orgy"),
    (re.compile(r"\bfoot\s+fetish\b|\bfeet\b|\btoes\b", re.IGNORECASE), "Foot Fetish"),
    (re.compile(r"\bfoot\s*jobs?\b", re.IGNORECASE), "Footjob"),
    (re.compile(r"\bhigh\s+heels?\b", re.IGNORECASE), "High Heels"),
    (re.compile(r"\bstockings?\b|\bnylons?\b", re.IGNORECASE), "Stockings"),
    (re.compile(r"\blingerie\b", re.IGNORECASE), "Lingerie"),
    (re.compile(r"\bnuru(?:\s+massage)?\b", re.IGNORECASE), "Nuru Massage"),
    (re.compile(r"\bmassages?\b", re.IGNORECASE), "Massage"),
    (re.compile(r"\bstep\s*moms?\b|\bmother\s*in\s*law\b", re.IGNORECASE), "Stepmom"),
    (re.compile(r"\bstep\s*sisters?\b", re.IGNORECASE), "Stepsister"),
    (re.compile(r"\bstep\s*daughters?\b", re.IGNORECASE), "Stepdaughter"),
    (re.compile(r"\bcuckolds?\b|\bhotwife\b", re.IGNORECASE), "Cuckold"),
    (re.compile(r"\bcheating\b", re.IGNORECASE), "Cheating"),
    (re.compile(r"\bpublic\s+(?:sex|nudity|outdoor)\b|\boutdoors?\b", re.IGNORECASE), "Public"),
    (re.compile(r"\bglory\s*holes?\b", re.IGNORECASE), "Gloryhole"),
    (re.compile(r"\bstrip\s*teases?\b|\bstrip\b", re.IGNORECASE), "Striptease"),
    (re.compile(r"\bcastings?\b|\bauditions?\b", re.IGNORECASE), "Casting"),
    (re.compile(r"\bfirst\s+time\b", re.IGNORECASE), "First Time"),
    (re.compile(r"\brole\s*play\b|\bnurses?\b|\bdoctor\b|\bmaid\b", re.IGNORECASE), "Roleplay"),
    (re.compile(r"\bsex\s+toys?\b|\bdildos?\b|\bvibrators?\b", re.IGNORECASE), "Sex Toys"),
    (re.compile(r"\bstrap\s*on\b", re.IGNORECASE), "Strap-on"),
    (re.compile(r"\bbukkake\b", re.IGNORECASE), "Bukkake"),
    (re.compile(r"\bswallow(?:ing)?\b", re.IGNORECASE), "Swallowing"),
    (re.compile(r"\bcock\s+sucking\b|\bsuck(?:s|ing)?\s+cock\b|\bslobbers?\b", re.IGNORECASE), "Blowjob"),
    (re.compile(r"\bbehind\s+the\s+scenes\b|\bbts\b", re.IGNORECASE), "Behind the Scenes"),

    # Single-word core categories with strict word boundary
    (re.compile(r"\banal\b", re.IGNORECASE), "Anal"),
    (re.compile(r"\bmilfs?\b", re.IGNORECASE), "MILF"),
    (re.compile(r"\bmatures?\b", re.IGNORECASE), "Mature"),
    (re.compile(r"\bgrann(?:y|ies)\b|\bgilfs?\b", re.IGNORECASE), "Granny"),
    (re.compile(r"\bteens?\b|\b18\+\b", re.IGNORECASE), "Teen (18+)"),
    (re.compile(r"\bpetites?\b", re.IGNORECASE), "Petite"),
    (re.compile(r"\bbbw\b|\bchubby\b", re.IGNORECASE), "BBW"),
    (re.compile(r"\bamateurs?\b|\bhomemade\b", re.IGNORECASE), "Amateur"),
    (re.compile(r"\bblondes?\b", re.IGNORECASE), "Blonde"),
    (re.compile(r"\bbrunettes?\b", re.IGNORECASE), "Brunette"),
    (re.compile(r"\bredheads?\b", re.IGNORECASE), "Redhead"),
    (re.compile(r"\bebon(?:y|ies)\b", re.IGNORECASE), "Ebony"),
    (re.compile(r"\basians?\b", re.IGNORECASE), "Asian"),
    (re.compile(r"\blatinas?\b", re.IGNORECASE), "Latina"),
    (re.compile(r"\bindians?\b", re.IGNORECASE), "Indian"),
    (re.compile(r"\binterracial\b", re.IGNORECASE), "Interracial"),
    (re.compile(r"\blesbians?\b|\btribbing\b|\bscissoring\b", re.IGNORECASE), "Lesbian"),
    (re.compile(r"\bsolo\b", re.IGNORECASE), "Solo"),
    (re.compile(r"\bsquirt(?:s|ing)?\b", re.IGNORECASE), "Squirting"),
    (re.compile(r"\bfacials?\b", re.IGNORECASE), "Facial"),
    (re.compile(r"\bcumshots?\b", re.IGNORECASE), "Cumshot"),
    (re.compile(r"\bmasturbat(?:e|ing|ion)\b", re.IGNORECASE), "Masturbation"),
    (re.compile(r"\bfingering\b", re.IGNORECASE), "Fingering"),
    (re.compile(r"\bpov\b", re.IGNORECASE), "POV"),
    (re.compile(r"\bhardcore\b", re.IGNORECASE), "Hardcore"),
    (re.compile(r"\btrans(?:gender)?\b|\bshemale\b", re.IGNORECASE), "Transgender"),
    (re.compile(r"\bpregnant\b", re.IGNORECASE), "Pregnant"),
    (re.compile(r"\bshaved\b", re.IGNORECASE), "Shaved"),
    (re.compile(r"\bhairy\b", re.IGNORECASE), "Hairy"),
    (re.compile(r"\btattoos?\b|\btattooed\b", re.IGNORECASE), "Tattoo"),
    (re.compile(r"\bpiercings?\b", re.IGNORECASE), "Piercing"),
    (re.compile(r"\bfetish\b", re.IGNORECASE), "Fetish"),
    (re.compile(r"\bbdsm\b|\bbondage\b", re.IGNORECASE), "BDSM"),
    (re.compile(r"\bspanking\b", re.IGNORECASE), "Spanking"),
    (re.compile(r"\bfemdom\b", re.IGNORECASE), "Femdom"),
    (re.compile(r"\boil(?:ed)?\b", re.IGNORECASE), "Oiled"),
    (re.compile(r"\bvoyeur\b|\bcandid\b", re.IGNORECASE), "Voyeur"),
    (re.compile(r"\bcosplay\b", re.IGNORECASE), "Cosplay"),
    (re.compile(r"\bhentai\b|\banime\b", re.IGNORECASE), "Hentai"),
    (re.compile(r"\bparod(?:y|ies)\b", re.IGNORECASE), "Parody"),
    (re.compile(r"\bcompilation\b", re.IGNORECASE), "Compilation"),
]


def extract_categories_from_title(title: str) -> List[str]:
    """Scan video title using precompiled regexes to extract matching categories.

    Returns a deduplicated list of canonical category names.
    """
    if not title:
        return []

    found: List[str] = []
    seen: Set[str] = set()

    for pattern, canonical in _COMPILED_CATEGORY_PATTERNS:
        if canonical not in seen and pattern.search(title):
            seen.add(canonical)
            found.append(canonical)

    return found
