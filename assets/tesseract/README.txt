Tesseract.js 5.1.1 runtime assets

Bundled local copies (the Flet Studio preview loads the version-pinned runtime and worker from jsDelivr because its asset transport does not provide module-loadable URLs):
  tesseract.min.js
  worker.min.js

Core JavaScript wrappers supplied with the app:
  core/tesseract-core.js
  core/tesseract-core-lstm.js
  core/tesseract-core-simd.js
  core/tesseract-core-simd-lstm.js

The matching .wasm binaries and lang/eng.traineddata.gz are not present, so
these core wrappers are not selected by the current worker. OCR currently
loads the Tesseract WASM core and English traineddata from their hosted
sources. Android WebView continues to load the Tesseract runtime from the
CDN because app-bundled assets are not directly addressable from its HTML.

For an entirely offline flow, include the four matching WASM files and
eng.traineddata.gz, then update workerPath/corePath/langPath in walking_ocr.py
and the equivalent paths in OCR_HTML in that file.
