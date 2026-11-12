"""Format and checksum checks for Indian GSTINs and EU VAT IDs."""
import re

_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

GST_STATES = {
    "01": "Jammu and Kashmir", "02": "Himachal Pradesh", "03": "Punjab", "04": "Chandigarh",
    "05": "Uttarakhand", "06": "Haryana", "07": "Delhi", "08": "Rajasthan", "09": "Uttar Pradesh",
    "10": "Bihar", "19": "West Bengal", "20": "Jharkhand", "21": "Odisha", "22": "Chhattisgarh",
    "23": "Madhya Pradesh", "24": "Gujarat", "27": "Maharashtra", "29": "Karnataka", "30": "Goa",
    "32": "Kerala", "33": "Tamil Nadu", "34": "Puducherry", "36": "Telangana", "37": "Andhra Pradesh",
}

GSTIN_RE = re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b")

EU_VAT_RE = {
    "DE": re.compile(r"^DE\d{9}$"),
    "NL": re.compile(r"^NL\d{9}B\d{2}$"),
    "FR": re.compile(r"^FR[0-9A-Z]{2}\d{9}$"),
    "IT": re.compile(r"^IT\d{11}$"),
    "ES": re.compile(r"^ES[0-9A-Z]\d{7}[0-9A-Z]$"),
}
EU_VAT_ANY = re.compile(r"\b(?:DE\d{9}|NL\d{9}B\d{2}|FR[0-9A-Z]{2}\d{9}|IT\d{11}|ES[0-9A-Z]\d{7}[0-9A-Z])\b")


def gstin_check_char(first14: str) -> str:
    """GSTN check digit: base-36 weighted sum with alternating factors 1 and 2."""
    total = 0
    for i, ch in enumerate(first14):
        product = _CHARS.index(ch) * (1 if i % 2 == 0 else 2)
        total += product // 36 + product % 36
    return _CHARS[(36 - total % 36) % 36]


def make_gstin(state: str, pan: str, entity: str = "1") -> str:
    body = f"{state}{pan}{entity}Z"
    return body + gstin_check_char(body)


def validate_gstin(gstin: str) -> list[str]:
    """Return a list of problems. Empty list means the GSTIN looks valid."""
    if not gstin:
        return ["GSTIN missing"]
    g = gstin.strip().upper()
    if len(g) != 15 or not re.fullmatch(r"\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]", g):
        return [f"GSTIN {g} does not match the 15-character format"]
    problems = []
    if g[:2] not in GST_STATES:
        problems.append(f"GSTIN {g} has unknown state code {g[:2]}")
    if gstin_check_char(g[:14]) != g[14]:
        problems.append(f"GSTIN {g} fails the checksum (last character should be {gstin_check_char(g[:14])})")
    return problems


def validate_eu_vat(vat_id: str) -> list[str]:
    if not vat_id:
        return ["VAT ID missing"]
    v = vat_id.replace(" ", "").upper()
    pattern = EU_VAT_RE.get(v[:2])
    if pattern is None:
        return [f"VAT ID {v}: country {v[:2]} not configured"]
    if not pattern.match(v):
        return [f"VAT ID {v} does not match the {v[:2]} format"]
    return []
