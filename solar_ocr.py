"""Browser OCR adapter for solar-monitoring screenshots.

Uses the app's existing real Tesseract.js integration. The browser runtime is
bundled with the app; the WASM core and English OCR data are loaded from hosted
sources, so an internet connection is still required for OCR.
"""

from solar_claims import parse_solar_reading
from walking_ocr import recognize_in_browser


async def extract_solar_reading(image_bytes, mime_type):
    """Recognize an image in the browser, then accept only a monthly kWh read."""
    import base64

    encoded = base64.b64encode(image_bytes).decode("ascii")
    result = await recognize_in_browser(encoded, mime_type, mode="solar")
    if result.get("error"):
        return {"error": str(result["error"])}
    extracted = parse_solar_reading(str(result.get("text", "")))
    extracted["ocr_text"] = str(result.get("text", ""))
    return extracted
