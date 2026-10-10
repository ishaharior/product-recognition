export default function AboutPage() {
  return (
    <div>
      <div className="page-head">
        <div>
          <h1 className="page-title">About</h1>
          <p className="page-sub">Project overview, architecture, stack, datasets, limitations and methodology.</p>
        </div>
      </div>

      <div className="prose">
        <h2>Project</h2>
        <p>
          Smart Product Station is a demonstration stack combining browser camera capture, YOLO object detection,
          HSV/CIELAB colour estimation, HX711 weight measurement and rule-based multimodal verification with a
          SQLite-backed dashboard. When the camera, custom model weights or weighing hardware are unavailable the
          system runs a deterministic demo mode — all demo data is simulated and is always labelled as such in the
          interface.
        </p>

        <h2>Architecture</h2>
        <ul>
          <li>
            Browser (<code>getUserMedia</code> → <code>&lt;canvas&gt;</code> → JPEG base64 over WebSocket) sends frames
            to FastAPI <code>/ws/scan</code>.
          </li>
          <li>YOLO detector runs in baseline (generic COCO) or custom (product classes) mode.</li>
          <li>
            Colour analyser crops the product region, builds an HSV histogram and compares Lab colours (ΔE) against
            the product&rsquo;s accepted variants.
          </li>
          <li>Weight sensor reads the HX711 over serial (or a clearly-labelled mock when no hardware is present).</li>
          <li>Verifier applies explainable rules across vision + colour + weight and returns an evidence-based status.</li>
          <li>Results are persisted to SQLite and returned with an annotated frame rendered back in the UI.</li>
        </ul>
        <p>
          Backend modules live under <code>backend/app/*</code> (API routes, runtime, services, schemas, DB layer) with
          the shared vision, sensor and verification code in <code>src/</code>:
        </p>
        <pre>{`distance-mapping/
├── backend/app/     FastAPI: api/, core/, db/, schemas/, services/
├── src/             shared Python: vision/, sensors/, verification/, datasets/
├── frontend/        React + TypeScript dashboard (this app)
├── data/            product specs, sample assets, prepared datasets
├── docs/            DATASETS.md, MODEL_TRAINING.md and friends
├── firmware/        microcontroller sketch for the load-cell scale
├── models/          YOLO weights
└── scripts/         evaluation helpers (e.g. compare_verification.py)`}</pre>

        <h2>Technology stack</h2>
        <ul>
          <li>
            <strong>Backend:</strong> Python 3.11+, FastAPI, Uvicorn, OpenCV, Ultralytics YOLO, SQLAlchemy/SQLite,
            Pydantic, pyserial.
          </li>
          <li>
            <strong>Frontend:</strong> React 18, TypeScript, Vite, Recharts, lucide-react.
          </li>
          <li>
            <strong>Tests:</strong> pytest (backend), vitest + Testing Library (frontend).
          </li>
        </ul>

        <h2>Datasets &amp; citations</h2>
        <ul>
          <li>
            <strong>RPC (Retail Products Checkout)</strong> — grocery checkout images for product recognition:{' '}
            <a href="https://rpc-dataset.github.io/" target="_blank" rel="noreferrer">
              rpc-dataset.github.io
            </a>
          </li>
          <li>
            <strong>Products-10K</strong> — large-scale product images with category/product labels:{' '}
            <a href="https://products-10k.github.io/" target="_blank" rel="noreferrer">
              products-10k.github.io
            </a>
          </li>
          <li>
            <strong>Freiburg Groceries</strong> — grocery shelf images for fine-grained food recognition:{' '}
            <a href="https://github.com/PhilJd/freiburg_groceries_dataset" target="_blank" rel="noreferrer">
              github.com/PhilJd/freiburg_groceries_dataset
            </a>
          </li>
        </ul>
        <p>
          <strong>
            Review each project&rsquo;s licence before downloading or redistributing data; no dataset is bundled with
            this repository.
          </strong>{' '}
          See <code>docs/DATASETS.md</code> for preparation steps.
        </p>

        <h2>Known limitations</h2>
        <ul>
          <li>Camera colour is an estimate — lighting, white balance and JPEG compression all shift the result.</li>
          <li>Baseline COCO detection gives generic object labels, not SKU identity.</li>
          <li>Model confidence is not a calibrated probability.</li>
          <li>Weight readings require taring and calibration against a known reference mass.</li>
          <li>The configured weight spec (gross vs net) must match what is placed on the scale.</li>
          <li>Demo mode data is simulated and labelled as such everywhere it appears.</li>
          <li>No counterfeit-detection claims are made — this is a verification aid, not an authenticity oracle.</li>
        </ul>

        <h2>Research hypothesis</h2>
        <p>
          Combining vision, colour and weight (multimodal verification) reduces false acceptances compared with
          vision-only checks on labelled product data. The comparison can be measured with{' '}
          <code>scripts/compare_verification.py</code> (accuracy, precision, recall, false-acceptance rate).{' '}
          <strong>No results are claimed here — none have been run.</strong>
        </p>

        <h2>Evaluation methodology</h2>
        <ul>
          <li>
            Assemble a labelled test set of scans with ground truth (product identity, colour variant, expected
            weight).
          </li>
          <li>Run each scan through the vision-only baseline and through the full multimodal rule set.</li>
          <li>Report accuracy, precision, recall and false-acceptance rate for both configurations.</li>
          <li>
            Be explicit about data provenance: readings from real hardware are tagged REAL, while demo/mock values are
            tagged SIMULATED — the two must not be mixed in a single reported figure without saying so.
          </li>
        </ul>
      </div>
    </div>
  );
}
