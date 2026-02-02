import unicodedata


def normalize_text(s: str) -> str:
    if s is None:
        return ""
    # NFKC, trim, lower
    return unicodedata.normalize("NFKC", s).strip().lower()