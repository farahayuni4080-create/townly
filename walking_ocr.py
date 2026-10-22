"""Separate OCR pipelines for running screenshots and solar reports."""

import json
import re


# Strava's share cards place Time and Distance values in stable lower-screen
# bands. Read those value bands independently from the route map, then also
# read the complete lower stats area as a fallback. The color/soft variants
# make this work with both bright and dimmed share-card overlays.
_OCR_PIPELINE = r"""
async function makeCrops(imageUrl) {
  if (typeof createImageBitmap !== "function" || typeof OffscreenCanvas === "undefined") return null;
  const response = await fetch(imageUrl);
  if (!response.ok) throw new Error("Could not decode the selected screenshot.");
  const bitmap = await createImageBitmap(await response.blob());
  const width = bitmap.width;
  const height = bitmap.height;

  async function crop(x, y, w, h, scale, binary) {
    const canvas = typeof OffscreenCanvas !== "undefined"
      ? new OffscreenCanvas(Math.round(w * scale), Math.round(h * scale))
      : document.createElement("canvas");
    canvas.width = Math.round(w * scale);
    canvas.height = Math.round(h * scale);
    const context = canvas.getContext("2d", { willReadFrequently: true });
    context.filter = "grayscale(1) contrast(1.65) brightness(1.12)";
    context.drawImage(bitmap, x, y, w, h, 0, 0, canvas.width, canvas.height);
    context.filter = "none";
    if (binary) {
      const imageData = context.getImageData(0, 0, canvas.width, canvas.height);
      const pixels = imageData.data;
      for (let index = 0; index < pixels.length; index += 4) {
        const gray = pixels[index] * 0.299 + pixels[index + 1] * 0.587 + pixels[index + 2] * 0.114;
        const value = gray > 160 ? 0 : 255;
        pixels[index] = value;
        pixels[index + 1] = value;
        pixels[index + 2] = value;
        pixels[index + 3] = 255;
      }
      context.putImageData(imageData, 0, 0);
    }
    if (typeof canvas.convertToBlob === "function") {
      return canvas.convertToBlob({ type: "image/png" });
    }
    return new Promise((resolve, reject) => {
      canvas.toBlob(blob => blob ? resolve(blob) : reject(new Error("Could not prepare the screenshot for OCR.")), "image/png");
    });
  }

  // The stats in both provided Strava references occupy these same bands:
  // Time value around 72-78% image height, Distance value around 83-90%.
  const time = [
    await crop(Math.floor(width * 0.07), Math.floor(height * 0.70), Math.floor(width * 0.58), Math.floor(height * 0.085), 4, true),
    await crop(Math.floor(width * 0.07), Math.floor(height * 0.70), Math.floor(width * 0.58), Math.floor(height * 0.085), 4, false)
  ];
  const distance = [
    await crop(Math.floor(width * 0.07), Math.floor(height * 0.815), Math.floor(width * 0.65), Math.floor(height * 0.095), 4, true),
    await crop(Math.floor(width * 0.07), Math.floor(height * 0.815), Math.floor(width * 0.65), Math.floor(height * 0.095), 4, false)
  ];
  const stats = await crop(0, Math.floor(height * 0.62), Math.floor(width * 0.88), Math.floor(height * 0.34), 3, true);
  bitmap.close();
  return { time, distance, stats };
}

async function recognizeSolarReport(imageUrl, worker) {
  const recognize = async (image, pageMode) => {
    await worker.setParameters({
      tessedit_pageseg_mode: String(pageMode),
      tessedit_char_whitelist: ""
    });
    const result = await worker.recognize(image);
    return (result && result.data && result.data.text) || "";
  };

  // Monitoring apps often render their monthly value as small text inside a
  // large phone screenshot. OCR the period and the PV card separately at a
  // larger scale so tiny labels and decimal values aren't lost in the full
  // screen pass. Coordinates cover the month selector and PV card in common
  // inverter-analysis layouts, including the attached Mr. Sim report.
  try {
    const response = await fetch(imageUrl);
    if (!response.ok) throw new Error("Could not decode the selected screenshot.");
    const bitmap = await createImageBitmap(await response.blob());
    const width = bitmap.width;
    const height = bitmap.height;
    const crop = async (x, y, w, h, scale) => {
      const canvas = typeof OffscreenCanvas !== "undefined"
        ? new OffscreenCanvas(Math.round(w * scale), Math.round(h * scale))
        : document.createElement("canvas");
      canvas.width = Math.round(w * scale);
      canvas.height = Math.round(h * scale);
      const context = canvas.getContext("2d", { willReadFrequently: true });
      context.filter = "grayscale(1) contrast(1.45) brightness(1.08)";
      context.drawImage(bitmap, x, y, w, h, 0, 0, canvas.width, canvas.height);
      context.filter = "none";
      if (typeof canvas.convertToBlob === "function") {
        return canvas.convertToBlob({ type: "image/png" });
      }
      return new Promise((resolve, reject) => {
        canvas.toBlob(blob => blob ? resolve(blob) : reject(new Error("Could not prepare report for OCR.")), "image/png");
      });
    };

    const periodCrop = await crop(
      Math.floor(width * 0.18), Math.floor(height * 0.17),
      Math.floor(width * 0.64), Math.floor(height * 0.09), 4
    );
    const pvCrop = await crop(
      Math.floor(width * 0.025), Math.floor(height * 0.18),
      Math.floor(width * 0.95), Math.floor(height * 0.34), 3
    );
    bitmap.close();

    const periodText = await recognize(periodCrop, 7);
    const pvText = await recognize(pvCrop, 6);
    const targetedText = [periodText, pvText].filter(Boolean).join("\n");
    // Retain full-page text as a fallback for report layouts outside the
    // targeted dashboard regions; the parser scopes PV values before use.
    const fullText = await recognize(imageUrl, 3);
    return { text: [targetedText, fullText].filter(Boolean).join("\n") };
  } catch (_) {
    // Some embedded browser versions lack bitmap/canvas crop support. Keep the
    // original full-image OCR fallback rather than failing the upload.
    return { text: await recognize(imageUrl, 3) };
  }
}

async function recognizeRunStats(imageUrl, tesseract, worker) {
  const crops = await makeCrops(imageUrl).catch(() => null);
  const read = async (image, whitelist, pageMode) => {
    try {
      await worker.setParameters({
        tessedit_pageseg_mode: String(pageMode),
        tessedit_char_whitelist: whitelist
      });
      const result = await worker.recognize(image);
      return (result && result.data && result.data.text) || "";
    } catch (_) {
      return "";
    }
  };

  let timeText = "";
  let distanceText = "";
  let statsText = "";
  if (crops) {
    const timeWhitelist = "0123456789hHmMsS: .";
    const distanceWhitelist = "0123456789.,kmKM ";
    for (const image of crops.time) {
      timeText += "\n" + await read(image, timeWhitelist, 7);
    }
    for (const image of crops.distance) {
      distanceText += "\n" + await read(image, distanceWhitelist, 7);
    }
    statsText = await read(crops.stats, "", 6);
  }
  // Full-image recognition is a last-resort fallback for non-standard layouts.
  const full = await read(imageUrl, "", 3);
  return {
    text: [timeText, distanceText, statsText, full].join("\n"),
    time_text: timeText,
    distance_text: distanceText
  };
}
"""


OCR_HTML = r"""<!doctype html>
<html>
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <script src="https://cdn.jsdelivr.net/npm/tesseract.js@5.1.1/dist/tesseract.min.js"></script>
</head>
<body>
<script>
let workerPromise = null;
let ocrQueue = Promise.resolve();

function reportResult(payload, mode, requestId) {
  console.log("FGR_OCR_RESULT:" + encodeURIComponent(JSON.stringify({ ...payload, mode, request_id: requestId })));
}

window.addEventListener("load", function() {
  if (window.Tesseract) {
    console.log("FGR_OCR_READY");
  } else {
    console.log("FGR_OCR_INIT_ERROR:" + encodeURIComponent("OCR engine script did not load"));
  }
});

""" + _OCR_PIPELINE + r"""
window.processRunImage = function(base64Image, mimeType, mode, requestId) {
  const process = async function() {
    try {
      if (!window.Tesseract) throw new Error("The OCR engine did not load. Check your internet connection and try again.");
      if (!workerPromise) {
        workerPromise = Tesseract.createWorker("eng", 1, {
          workerPath: "https://cdn.jsdelivr.net/npm/tesseract.js@5.1.1/dist/worker.min.js",
          corePath: "https://cdn.jsdelivr.net/npm/tesseract.js-core@5.1.1/tesseract-core.wasm.js",
          langPath: "https://tessdata.projectnaptha.com/4.0.0",
          logger: function() {}
        });
      }
      const worker = await workerPromise;
      const imageUrl = `data:${mimeType};base64,${base64Image}`;
      const result = mode === "solar"
        ? await recognizeSolarReport(imageUrl, worker)
        : await recognizeRunStats(imageUrl, Tesseract, worker);
      reportResult(result, mode, requestId);
    } catch (error) {
      workerPromise = null;
      reportResult({ error: String(error && error.message ? error.message : error) }, mode, requestId);
    }
  };
  // Tesseract workers are stateful; serialize requests so solar and running
  // jobs cannot overwrite each other's character whitelist or page mode.
  ocrQueue = ocrQueue.then(process, process);
  return ocrQueue;
};
</script>
</body>
</html>"""


def _parse_distance(text, allow_bare_value=False):
    if not isinstance(text, str):
        return None
    normalized = re.sub(r"\s+", " ", text).strip()
    normalized = re.sub(r"\bk\s*m\b", "km", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\s*([.,])\s*", r"\1", normalized)
    match = re.search(
        r"\b(\d{1,4}(?:[.,]\d{1,3})?)\s*(?:km\b|kilomet\s*(?:er|re)s?\b|kms\b)",
        normalized,
        re.IGNORECASE,
    )
    if not match and allow_bare_value:
        # The targeted OCR crop contains only the Distance value, so a bare
        # decimal is safe to accept even if Tesseract misses the small 'km'.
        match = re.search(r"(?<!\d)(\d{1,4}[.,]\d{1,3})(?!\d)", normalized)
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", "."))
    except ValueError:
        return None


def parse_running_stats(text, distance_text="", time_text=""):
    """Extract distance in km and run duration from OCR text/targeted crops."""
    if not isinstance(text, str):
        text = ""
    normalized = re.sub(r"\s+", " ", text).strip()

    # Prefer the tightly cropped values, which avoid route/map labels and
    # elevation numbers; fall back to labeled text from the stats/full-image pass.
    distance = _parse_distance(distance_text, allow_bare_value=True)
    if distance is None:
        distance = _parse_distance(normalized)

    duration = _parse_duration(time_text) if time_text else None
    if duration is None:
        time_label = re.search(r"\btime\b\s*[:\-]?\s*", normalized, re.IGNORECASE)
        if time_label:
            value_region = normalized[time_label.end():]
            next_metric = re.search(
                r"\b(?:elev(?:ation)?(?:\s+gain)?|distance|pace|speed|calories?|"
                r"heart\s*rate|cadence|splits?)\b",
                value_region,
                re.IGNORECASE,
            )
            if next_metric:
                value_region = value_region[:next_metric.start()]
            duration = _parse_duration(value_region[:80])

    if duration is None:
        # Strava time formats such as 50m 55s and 1h 1m are unambiguous.
        duration = _parse_duration(normalized, allow_minutes_only=False)
    return {"distance_km": distance, "duration": duration}


def _parse_duration(text, allow_minutes_only=True):
    compact = re.sub(r"\s+", " ", text).strip()
    # Repair common Tesseract confusions of the numeral 1 / 0 with I, l, | / O.
    compact = re.sub(
        r"(?<![A-Za-z0-9])[Il|](?=\s*(?:h|hr|hrs|hour|hours|m|min|mins|minute|minutes|s|sec|secs|second|seconds)\b)",
        "1",
        compact,
        flags=re.IGNORECASE,
    )
    compact = re.sub(
        r"(?<![A-Za-z0-9])O(?=\s*(?:h|m|s)\b)", "0", compact, flags=re.IGNORECASE
    )
    hour = r"h(?:r|rs|ours?)?"
    minute = r"m(?:in(?:ute)?s?|ins?)?"
    second = r"s(?:ec(?:ond)?s?)?"

    patterns = [
        (rf"\b(\d+)\s*{hour}\s*(\d+)\s*{minute}\s*(\d+)\s*{second}\b", "hms"),
        (rf"\b(\d+)\s*{hour}\s*(\d+)\s*{minute}\b", "hm"),
        (rf"\b(\d+)\s*{hour}\b", "h"),
        (rf"\b(\d+)\s*{minute}\s*(\d+)\s*{second}\b", "ms"),
        (r"\b(\d{1,2}):([0-5]\d):([0-5]\d)\b", "clock_hms"),
        (r"\b(\d{1,3}):([0-5]\d)\b", "clock_ms"),
    ]
    if allow_minutes_only:
        patterns.insert(4, (rf"\b(\d+)\s*{minute}\b", "m"))

    for pattern, kind in patterns:
        match = re.search(pattern, compact, re.IGNORECASE)
        if not match:
            continue
        values = match.groups()
        if kind in {"hms", "clock_hms"}:
            return f"{int(values[0])}h {int(values[1])}m {int(values[2])}s"
        if kind == "hm":
            return f"{int(values[0])}h {int(values[1])}m"
        if kind == "h":
            return f"{int(values[0])}h"
        if kind in {"ms", "clock_ms"}:
            return f"{int(values[0])}m {int(values[1])}s"
        if kind == "m":
            return f"{int(values[0])}m"
    return None


def make_recognition_script(image_base64, mime_type, mode="running", request_id=None):
    if mode not in {"running", "solar"}:
        raise ValueError("OCR mode must be 'running' or 'solar'.")
    return (
        "window.processRunImage("
        f"{json.dumps(image_base64)}, {json.dumps(mime_type)}, "
        f"{json.dumps(mode)}, {json.dumps(request_id)}"
        ");"
    )


async def recognize_in_browser(image_base64, mime_type, mode="running"):
    """Run the workflow-specific Tesseract.js OCR pipeline in a browser.

    The app-bundled Tesseract and worker scripts are used locally. The matching
    WASM core and English traineddata are still fetched from their hosted
    sources because those binary/data assets are not included in the app.
    """
    if mode not in {"running", "solar"}:
        raise ValueError("OCR mode must be 'running' or 'solar'.")
    import js

    image_url = f"data:{mime_type};base64,{image_base64}"
    script = r"""
    (async () => {
      try {
        const loadTesseract = async () => {
          if (globalThis.Tesseract) return globalThis.Tesseract;
          // Flet Studio serves app assets through its asset transport, which
          // is not a module-loadable URL in the Pyodide worker. Load the
          // version-pinned UMD bundle from jsDelivr instead.
          await import("https://cdn.jsdelivr.net/npm/tesseract.js@5.1.1/dist/tesseract.min.js");
          if (!globalThis.Tesseract) {
            throw new Error("The bundled Tesseract.js runtime did not initialize.");
          }
          return globalThis.Tesseract;
        };
        const tesseract = await loadTesseract();
        const worker = await tesseract.createWorker("eng", 1, {
          workerPath: "https://cdn.jsdelivr.net/npm/tesseract.js@5.1.1/dist/worker.min.js",
          corePath: "https://cdn.jsdelivr.net/npm/tesseract.js-core@5.1.1/tesseract-core.wasm.js",
          langPath: "https://tessdata.projectnaptha.com/4.0.0",
          workerBlobURL: true,
          logger: () => {}
        });
        try {
          const imageUrl = __IMAGE_URL__;
          const mode = __OCR_MODE__;
          const result = mode === "solar"
            ? await recognizeSolarReport(imageUrl, worker)
            : await recognizeRunStats(imageUrl, tesseract, worker);
          return JSON.stringify(result);
        } finally {
          await worker.terminate();
        }
      } catch (error) {
        return JSON.stringify({error: String(error && error.message ? error.message : error)});
      }
    })()
    """
    script = script.replace("__IMAGE_URL__", json.dumps(image_url))
    script = script.replace("__OCR_MODE__", json.dumps(mode))
    script = script.replace("(async () => {", "(async () => {\n" + _OCR_PIPELINE)
    # In Flet's Pyodide preview this executes in a module worker, not a window;
    # the script uses worker-safe APIs and never depends on document/window.
    raw_result = await js.self.eval(script)
    return json.loads(str(raw_result))
