import re

ARABIC_DIACRITICS = re.compile(r"[\u0617-\u061A\u064B-\u0652]")


def normalize_arabic(text: str | None) -> str:
    if not text:
        return ""
    text = text.strip()
    text = re.sub(ARABIC_DIACRITICS, "", text)
    text = re.sub("[إأآا]", "ا", text)
    text = re.sub("ة", "ه", text)
    text = re.sub("ى", "ي", text)
    text = re.sub("ك", "ك", text)
    return text.lower()
