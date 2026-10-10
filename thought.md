# Project: Smart Product Recognition & Weighing Station

Act as a senior Python AI engineer, computer vision researcher, full-stack developer, and test engineer.

Build a complete, runnable project called **Smart Product Station**. It must have a modern web interface that demonstrates live product recognition using a camera, colour analysis, physical weight measurement, and product verification.

Do not stop after writing a plan or generating mockups. Implement the project in the current workspace, run it, test it, fix errors, and document how to launch it.

## 1. Product objectives

The application must:

1. Display a live camera feed in a browser.
2. Detect products appearing in the camera frame.
3. Identify the product when its identity is supported by the available model.
4. Estimate the dominant visible product colour.
5. Obtain actual measured weight from a calibrated load-cell sensor, when available.
6. Compare measured weight with expected product specifications.
7. Display confidence, measurements, verification status, and warnings.
8. Store scan history in a database.
9. Provide a polished web dashboard suitable for a live demonstration.
10. Support demo mode when no camera, trained model, or weighing hardware is available.

## 2. Required technology stack

Backend:
- Python 3.11 or another compatible, supported Python version.
- FastAPI.
- Uvicorn.
- OpenCV.
- Ultralytics YOLO.
- NumPy and Pandas.
- Pydantic for validation.
- SQLAlchemy with SQLite.
- WebSockets for real-time result updates.
- PySerial for optional Arduino/ESP32 scale communication.

Frontend:
- React.
- TypeScript.
- Vite.
- A clean, responsive dashboard UI.
- Recharts for analytics.
- A consistent icon library and reusable UI components.

Testing:
- Pytest for backend tests.
- Appropriate frontend tests.
- Browser-based end-to-end testing if available in the environment.

Use stable compatible package versions. Record dependencies in requirements.txt and package.json.

## 3. Dataset sources

Document these public resources in DATASETS.md:

1. RPC retail product checkout dataset:
   https://rpc-dataset.github.io/
   https://www.kaggle.com/diyer22/retail-product-checkout-dataset

2. Products-10K:
   https://products-10k.github.io/
   https://products-10k.github.io/challenge.html

3. Freiburg Groceries:
   https://github.com/PhilJd/freiburg_groceries_dataset

Explain each dataset's intended task, download procedure, label format, licensing restrictions, and compatibility with the project's model.

Do not automatically download large datasets or launch expensive training jobs. Provide scripts and clear instructions for users to opt in to downloads.

Inspect real dataset directory structures and annotation formats before implementing converters. Do not fabricate annotations, product identities, dataset statistics, or training results.

Create a dataset preparation module that can:
- Inspect image files and labels.
- Detect missing or corrupt files.
- Summarize class counts.
- Convert supported detection annotations to YOLO format.
- Create reproducible train/validation/test splits without leakage.
- Generate a dataset configuration file.
- Report unsupported dataset formats clearly.

The project must run even if no external dataset has been downloaded.

## 4. Model strategy

Implement two explicit inference modes:

A. Baseline mode:
- Use a lightweight pretrained YOLO model supported by the installed Ultralytics package.
- Allow webcam detection of supported pretrained classes.
- Clearly label results as generic object detection rather than exact SKU recognition.

B. Custom product mode:
- Load a user-trained weights file from a configurable path.
- Read class names from the model or its verified configuration.
- Support product-level detection after custom training.
- If custom weights are missing, show an informative setup message and offer baseline or demo mode.

Create:
- src/vision/detector.py
- src/vision/model_manager.py
- scripts/train_model.py
- scripts/validate_model.py
- scripts/prepare_dataset.py

Training scripts must accept configurable dataset paths, model weights, epochs, image size, batch size, and output directory.

Do not start training automatically when the application starts. Do not claim that a model has been trained successfully unless a real training run completed.

Use confidence thresholds and return an unknown/uncertain result when evidence is insufficient. Do not equate a detector confidence score with a calibrated probability of correctness.

## 5. Camera and browser architecture

The browser must request camera permission using the browser's camera API.

Use a browser camera preview and send appropriately resized frames to the backend for inference through a WebSocket or another documented real-time transport.

Requirements:
- Start and stop camera processing through the interface.
- Handle camera permission denial.
- Handle missing cameras and disconnected connections.
- Avoid sending frames faster than the backend can process.
- Limit image dimensions and frame rate for reasonable CPU usage.
- Render annotated frames and detection metadata in the browser.
- Clean up streams and connections when the user stops the demo or leaves the page.
- Do not expose unnecessary camera frames or personal data in logs.

The default development environment should work on localhost. Explain HTTPS requirements for camera access when deployed to other origins.

Do not make the frontend depend on a physical camera being available at application startup.

## 6. Product colour analysis

Create src/vision/color_analyzer.py.

Implement:
- Product-region cropping from a detection box.
- Optional segmentation-mask support.
- Background exclusion where practical.
- HSV-based colour analysis.
- Optional CIELAB-based comparison.
- Dominant colour names and a colour distribution.
- Configurable handling of highlights, shadows, and very dark or bright pixels.
- Confidence/quality warnings for poor lighting or an unreliable region.

Return a structured result containing the estimated colour name, colour proportions, and a measurement-quality indicator.

Clearly state that camera-based colour is an estimate. Do not claim laboratory-grade colour accuracy.

Include test images or synthetic unit tests for the colour-analysis logic. Clearly distinguish tests from real camera validation.

## 7. Physical weight measurement

Create:
- src/sensors/weight_sensor.py
- firmware/scale_controller/README.md
- firmware/scale_controller/scale_controller.ino, if implementing Arduino firmware.

Support an HX711 load cell connected to an Arduino or ESP32 that sends readings over USB serial.

Implement:
- Tare.
- Calibration using a known reference weight.
- Configurable calibration factor.
- Stable-reading detection.
- Units in grams and kilograms.
- Connection status and sensor error handling.
- Configurable measurement timeout.
- A mock sensor for development and automated tests.

Do not assume the sensor is calibrated. Never silently use a simulated reading as a real hardware measurement.

Provide an appropriate CSV or configuration file for product specifications, including expected net weight, expected gross weight where known, units, and tolerance.

Explain that packaging weight, net contents, and gross weight are different measurements. Do not compare a gross measurement against a net-weight specification.

## 8. Product verification and multimodal novelty

Create src/verification/verifier.py.

Combine:
- Product recognition result.
- Detection confidence.
- Colour compatibility, where reference data exists.
- Stable physical weight reading.
- Product catalogue specifications.
- Optional barcode or OCR results as a future extension.

Possible results:
- VERIFIED
- REVIEW_REQUIRED
- UNKNOWN_PRODUCT
- WEIGHT_MISMATCH
- COLOUR_MISMATCH
- SENSOR_UNAVAILABLE
- INSUFFICIENT_EVIDENCE

Make thresholds configurable. Require stable measurements before weight verification.

Do not label a product as counterfeit or fraudulent merely because its weight or colour differs from expected specifications. Use neutral language such as “mismatch detected” and “manual review recommended.”

Provide an explanation for each verification decision.

Implement a comparison experiment that can evaluate vision-only versus multimodal verification using a labelled test set. Report relevant accuracy, precision, recall, false acceptance rate, and measurement errors where applicable. Do not invent experimental results.

## 9. Database and product catalogue

Use SQLite and SQLAlchemy.

Create database models for:
- Products.
- Product colour variants.
- Expected weight specifications.
- Scan records.
- Verification results.
- Optional sensor calibration metadata.

Each scan should include:
- Unique scan ID.
- Timestamp.
- Product identity, if known.
- Model confidence.
- Estimated colour.
- Measured weight and unit.
- Weight source: real sensor or simulated.
- Verification status.
- Explanation or warning.
- Inference mode.

Store image references only when necessary and configurable. Avoid saving every frame.

Provide CRUD functionality for the product catalogue and an option to export scan history to CSV.

Include database initialization and safe schema setup.

## 10. Web dashboard requirements

Build a polished, professional interface suitable for a university demonstration, portfolio presentation, and future commercial prototype.

Use a responsive design with a consistent visual theme.

Required pages or navigation sections:

A. Overview dashboard
- Total scans.
- Unique products detected.
- Successful verification count.
- Review and mismatch counts.
- Recent activity.
- A simple chart of scans over time.

B. Live scanner
- Large live camera preview.
- Start/stop controls.
- Annotated product bounding boxes.
- Detected product name and confidence.
- Dominant colour and colour distribution.
- Measured weight and expected weight.
- Verification status.
- Clear source labels for real and simulated measurements.
- FPS and connection status where available.

C. Product catalogue
- Product name, SKU, category, reference image, expected weights, tolerance, and colour variants.
- Search, filter, create, edit, and delete actions.
- Form validation and useful empty states.

D. Scan history
- Searchable table.
- Filters for product, date, and verification result.
- Scan detail view.
- CSV export.

E. Model and hardware status
- Current model name and inference mode.
- Model weights availability.
- Camera connection state.
- Sensor connection state.
- Sensor calibration state.
- Dataset preparation status.
- Helpful troubleshooting messages.

F. About / methodology
- Project architecture.
- Technology stack.
- Dataset citations and licensing.
- Known limitations.
- Research novelty hypothesis.
- Model evaluation methodology.

Use realistic-looking but explicitly simulated sample data for the dashboard preview. Never present invented values as real experimental results.

## 11. Demo mode

Demo mode is mandatory.

It must work without a camera, load-cell sensor, custom model weights, or external dataset download.

Include:
- A bundled, legally usable small sample image or a generated placeholder.
- A prerecorded sample video only if its source and usage rights are documented.
- Otherwise, use a deterministic synthetic demo sequence with clearly labelled simulated objects and measurements.
- Simulated detection events.
- Simulated colour estimates and weight readings.
- A visible “DEMO MODE — SIMULATED DATA” label.
- Controls to pause, resume, reset, and exit demo mode.

Never silently switch from a failed real sensor to simulated readings. Show an explicit mode change.

## 12. API design

Create documented endpoints such as:
- GET /api/health
- GET /api/status
- GET /api/products
- POST /api/products
- GET /api/scans
- GET /api/scans/{scan_id}
- GET /api/metrics
- POST /api/demo/start
- POST /api/demo/stop
- POST /api/sensor/tare
- POST /api/sensor/calibrate

Use WebSockets for live camera inference results and status updates.

Validate request data, handle exceptions, and return appropriate HTTP status codes.

Configure CORS narrowly for the local development frontend. Do not introduce unnecessary authentication secrets or expose arbitrary filesystem paths through the API.

## 13. Suggested repository structure

smart-product-station/
  backend/
    app/
      main.py
      api/
      core/
      db/
      schemas/
      vision/
      sensors/
      verification/
      services/
    tests/
    requirements.txt
  frontend/
    src/
      components/
      pages/
      hooks/
      services/
      types/
    package.json
  firmware/
    scale_controller/
  scripts/
    prepare_dataset.py
    train_model.py
    validate_model.py
  data/
    README.md
    sample/
  models/
    README.md
  docs/
    ARCHITECTURE.md
    DATASETS.md
    HARDWARE_SETUP.md
    MODEL_TRAINING.md
    TROUBLESHOOTING.md
  .env.example
  .gitignore
  README.md

Adapt this structure if needed, but keep model logic, API code, hardware integration, and frontend code separated.

Do not commit large datasets, private configuration, real camera recordings, or model weight files to Git.

## 14. Build phases and acceptance criteria

Phase 1: Scaffold and demo dashboard.
Acceptance: the frontend and backend start successfully, the dashboard loads in a browser, and demo mode displays simulated scan events.

Phase 2: Camera and baseline detector.
Acceptance: a user can grant camera permission, start scanning, see live frames, and receive real model detections.

Phase 3: Dataset tools and custom model support.
Acceptance: dataset inspection works, converters validate supported formats, and custom model loading gives clear errors when weights are absent.

Phase 4: Colour analysis.
Acceptance: the application displays a colour estimate from the detected product region and reports when the result is unreliable.

Phase 5: Weight integration.
Acceptance: mock sensor tests pass; hardware mode supports serial readings, tare, calibration, stability checks, and connection errors.

Phase 6: Verification and history.
Acceptance: verification rules produce explainable results, scans persist in SQLite, and CSV export works.

Phase 7: End-to-end polish.
Acceptance: the main workflows work, the UI is responsive, no essential navigation elements are inert, and documented commands launch the application from a clean setup.

## 15. Testing requirements

Create automated tests for:
- Product catalogue operations.
- Colour-analysis logic.
- Weight stability and unit conversion.
- Calibration and tare behaviour.
- Verification decision rules.
- Missing model weights.
- Invalid or unsupported dataset annotations.
- API validation.
- Demo mode.
- Database persistence.

Mock the camera and sensor in unit tests.

Run backend and frontend tests. Fix all failures caused by the implementation. If a test cannot be run because a dependency, browser, or hardware device is unavailable, report that limitation honestly.

Do not claim hardware tests passed when only mock tests ran.

## 16. Developer experience

Provide:
- A root README with exact Windows PowerShell setup instructions.
- Separate backend and frontend launch commands.
- An optional single-command development launcher if reliable.
- .env.example.
- requirements.txt and package-lock.json.
- Troubleshooting instructions for webcam permissions, serial ports, missing weights, and CORS.
- A documented method for training a custom model.
- A documented way to switch between demo, baseline, and custom product modes.

Use readable, typed, modular code. Avoid giant files, duplicated logic, hardcoded machine-specific paths, and placeholder implementations for essential features.

## 17. Final execution instructions

First inspect the current workspace and produce a concise implementation plan.

Then implement the application phase by phase. Do not stop after producing the plan.

After implementation:
1. Install or verify dependencies where possible.
2. Run the backend and frontend.
3. Run automated tests.
4. Open the web application in a browser if browser tooling is available.
5. Test the main demo workflow.
6. Fix errors and repeat relevant checks.
7. Document commands, limitations, and remaining work.

At completion, report:
- Files created.
- Features implemented.
- Exact commands to run the application.
- Local URL for the dashboard.
- Test results and any untested areas.
- How to activate demo mode.
- How to train and load custom product weights.
- How to connect and calibrate the real weighing hardware.

Prioritize a working, honest, demonstrable end-to-end application over unnecessary complexity.

Add this datasets :
## Animal Detection Datasets

1. **COCO 2017** — https://cocodataset.org/#download
2. **Open Images V7** — https://storage.googleapis.com/openimages/web/index.html
3. **Ultralytics COCO Dataset Guide** — https://docs.ultralytics.com/datasets/detect/coco
4. **Open Images V7 Dataset Guide** — https://docs.ultralytics.com/datasets/detect/open-images-v7/

## Hand Gesture Datasets

1. **HaGRID / HaGRIDv2** — https://github.com/hukenovs/hagrid
2. **HaGRID Small Subset** — https://github.com/hukenovs/hagrid
