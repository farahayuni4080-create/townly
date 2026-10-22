"""Domain rules for monthly solar generation claims.

The existing app's authoritative points balance lives in Supabase's points_ledger.
The SQL RPC applies the same 0.5-point-per-kWh rule atomically; this module keeps
UI validation and OCR interpretation consistent with that backend rule.
"""

import calendar
import re
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

POINTS_PER_KWH = Decimal("0.5")
FLAG_REVIEW_ABOVE_KWH = Decimal("50000")
MAX_READING_KWH = Decimal("9999999999.99")

_MONTHS = {name.lower(): number for number, name in enumerate(calendar.month_name) if name}
_MONTHS.update({name.lower(): number for number, name in enumerate(calendar.month_abbr) if name})
_LIFETIME_WORDS = re.compile(r"\b(?:lifetime|cumulative|all[ -]?time|since\s+installation)\b", re.I)
_MONTHLY_WORDS = re.compile(
    r"\b(?:monthly|this\s+month|current\s+month|month(?:ly)?\s+(?:generation|yield|production|total)|"
    r"generation\s+(?:for|this)\s+month|energy\s+(?:generated|produced)\s+this\s+month)\b",
    re.I,
)
_KWH_RE = re.compile(
    r"(?P<value>(?:\d{1,3}(?:,\d{3})+|\d+)(?:[.,]\d{1,3})?)\s*(?:k\s*w\s*h|kwh|kilowatt[- ]?hours?)\b",
    re.I,
)


def _number(raw):
    value = raw.strip().replace(" ", "")
    if "," in value and "." in value:
        value = value.replace(",", "")
    elif "," in value:
        before, after = value.rsplit(",", 1)
        value = before.replace(",", "") + ("." + after if len(after) <= 2 else after)
    try:
        amount = Decimal(value)
    except InvalidOperation:
        return None
    return amount if amount.is_finite() else None


def _report_period(text):
    normalized = re.sub(r"\s+", " ", text)
    named = re.search(
        r"\b(" + "|".join(sorted(_MONTHS, key=len, reverse=True)) + r")\s*[,./-]?\s*(20\d{2})\b",
        normalized,
        re.I,
    )
    if named:
        return _MONTHS[named.group(1).lower()], int(named.group(2))
    numeric = re.search(r"\b(20\d{2})[-/.](0?[1-9]|1[0-2])\b", normalized)
    if numeric:
        return int(numeric.group(2)), int(numeric.group(1))
    numeric = re.search(r"\b(0?[1-9]|1[0-2])[-/.](20\d{2})\b", normalized)
    if numeric:
        return int(numeric.group(1)), int(numeric.group(2))
    return None, None


def _pv_monthly_total(text, month, year):
    """Read the total from inverter dashboards with PV/consumption cards.

    For layouts like the supplied monthly analytics screenshot, the PV card
    shows total production plus self-consumption and grid-feed-in subtotals.
    Only the PV section is inspected; the lower Consumption card is excluded.
    """
    if not month or not year:
        return None
    heading = re.search(r"\bPV\s+production\b", text, re.I)
    if not heading:
        return None
    tail = text[heading.end():]
    end = re.search(r"\bConsumption\b", tail, re.I)
    section = tail[:end.start()] if end else tail
    if _LIFETIME_WORDS.search(section):
        return None
    section = re.sub(r"\s+", " ", section)
    readings = list(_KWH_RE.finditer(section))
    if not readings:
        return None

    def nearest_label_value(label_pattern):
        labels = list(re.finditer(label_pattern, section, re.I))
        if not labels:
            return None
        choices = []
        for label in labels:
            for reading in readings:
                distance = max(
                    reading.start() - label.end(),
                    label.start() - reading.end(),
                    0,
                )
                if distance <= 90:
                    choices.append((distance, _number(reading.group("value"))))
        choices = [(distance, value) for distance, value in choices if value is not None]
        return min(choices, default=(None, None), key=lambda item: item[0])[1]

    self_used = nearest_label_value(r"self[\s-]*consum\w*")
    grid_export = nearest_label_value(r"grid[\s-]*feed[\s-]*in")
    if self_used is not None and grid_export is not None and self_used != grid_export:
        component_total = self_used + grid_export
        reading_values = [_number(item.group("value")) for item in readings]
        matches_total = [
            value for value in reading_values
            if value is not None and abs(value - component_total) <= Decimal("0.03")
        ]
        return matches_total[0] if matches_total else component_total

    # In this specific dashboard card, the overall PV production is the
    # greatest kWh figure; consumption is outside this section and excluded.
    values = [_number(item.group("value")) for item in readings]
    values = [value for value in values if value is not None]
    return max(values) if values else None


def parse_solar_reading(ocr_text):
    """Return an explicitly monthly kWh value and report period from OCR text.

    A bare lifetime/cumulative reading is never treated as monthly production.
    The OCR result must contain kWh and either a monthly cue or one unambiguous
    kWh value paired with a report month/year.
    """
    if not isinstance(ocr_text, str) or not ocr_text.strip():
        return {"error": "No readable text was found in the report."}

    month, year = _report_period(ocr_text)

    # Some inverter monthly dashboards label the aggregate as "PV production"
    # rather than "monthly generation". Interpret only that card, and exclude
    # the separate Consumption card so its larger kWh total cannot be rewarded.
    pv_total = _pv_monthly_total(ocr_text, month, year)
    if pv_total is not None:
        return {"kwh": pv_total, "month": month, "year": year}

    matches = list(_KWH_RE.finditer(ocr_text))
    if not matches:
        return {"error": "No solar generation value with a kWh unit was found."}

    monthly_spans = [item.span() for item in _MONTHLY_WORDS.finditer(ocr_text)]
    lifetime_spans = [item.span() for item in _LIFETIME_WORDS.finditer(ocr_text)]

    def cue_distance(spans, start, end):
        if not spans:
            return None
        return min(max(start - cue_end, cue_start - end, 0) for cue_start, cue_end in spans)

    candidates = []
    for match in matches:
        monthly_distance = cue_distance(monthly_spans, match.start(), match.end())
        lifetime_distance = cue_distance(lifetime_spans, match.start(), match.end())
        is_monthly = monthly_distance is not None and monthly_distance <= 110
        if lifetime_distance is not None and (
            not is_monthly or lifetime_distance <= monthly_distance
        ):
            continue
        amount = _number(match.group("value"))
        if amount is not None:
            candidates.append((amount, is_monthly))

    monthly = [amount for amount, tagged in candidates if tagged]
    if len(monthly) == 1:
        amount = monthly[0]
    elif len(monthly) > 1:
        return {"error": "More than one monthly kWh reading was found. Use a clearer report."}
    elif len(candidates) == 1 and month and year and not _LIFETIME_WORDS.search(ocr_text):
        amount = candidates[0][0]
    elif _LIFETIME_WORDS.search(ocr_text):
        return {"error": "The report appears to show cumulative or lifetime energy, not a monthly reading."}
    else:
        return {"error": "Could not identify an explicitly monthly solar generation reading."}

    return {"kwh": amount, "month": month, "year": year}


def calculate_solar_points(kwh_value):
    """Adapter seam for the team's shared points calculator.

    No separately named Abel calculator exists in this app yet. The current
    adapter awards 0.5 point per kWh and rounds to the whole-point ledger
    precision; the authoritative equivalent is repeated in the SQL RPC.
    """
    amount = Decimal(str(kwh_value))
    if not amount.is_finite() or amount < 0:
        raise ValueError("Solar kWh must be a finite non-negative amount")
    return int((amount * POINTS_PER_KWH).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def validate_claim(kwh_value, month_value, year_value, today=None):
    """Validate a claim period and reading; return (amount, points, issue)."""
    today = today or date.today()
    try:
        amount = Decimal(str(kwh_value).strip())
    except (InvalidOperation, TypeError, ValueError, AttributeError):
        return None, None, "The extracted generation value is not a valid number."
    if not amount.is_finite() or amount <= 0:
        return None, None, "Solar generation must be a finite value greater than zero."
    if amount > MAX_READING_KWH:
        return None, None, "This reading is outside the supported range. Check the report units."

    try:
        month = int(month_value)
        year = int(year_value)
    except (TypeError, ValueError):
        return None, None, "Choose a valid claim month and year."
    if month < 1 or month > 12:
        return None, None, "Claim month must be between 1 and 12."
    if year < 2000 or (year, month) > (today.year, today.month):
        return None, None, "The claim period must be a valid month that has already started."

    return amount, calculate_solar_points(amount), None


def is_suspicious(kwh_value):
    """Flag unusually large household monthly totals rather than auto-awarding."""
    try:
        return Decimal(str(kwh_value)) > FLAG_REVIEW_ABOVE_KWH
    except (InvalidOperation, TypeError, ValueError):
        return False


def has_successful_claim(history, month, year):
    """Fast UI duplicate check; the database RPC remains authoritative."""
    return any(
        int(claim.get("claim_month", 0)) == int(month)
        and int(claim.get("claim_year", 0)) == int(year)
        and claim.get("claim_status") == "awarded"
        for claim in (history or [])
    )


def claim_period_key(month, year):
    return f"{int(year):04d}-{int(month):02d}"
