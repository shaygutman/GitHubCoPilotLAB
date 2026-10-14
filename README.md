# Regulatory Radar

A small web service for a Regulatory Affairs team. It answers two questions:

- **What is happening in the regulatory world?** Short summaries of FDA and EU
  updates, plus live or saved data from [openFDA](https://open.fda.gov/) on
  510(k) clearances and device recalls.
- **What does it mean for OUR products?** A portfolio of six products of the
  fictional company *Acme MedTech*, ready to be matched against those updates.



## 2. Set up a virtual environment

A virtual environment is a private folder with this project's Python packages,
so nothing you install here affects the rest of your computer.

Open a terminal **in the project folder** (the one containing this README), then:

**macOS / Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

**Windows (PowerShell)**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

If PowerShell refuses to run the activation script, run this once and try again:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

You will know it worked when your prompt starts with `(.venv)`. Repeat the
`activate` step every time you open a new terminal.

## 3. Install the dependencies

```bash
pip install -r requirements.txt
```

## 4. Configure (optional)

Settings live in a file called `.env` in the project folder. If you do not
have one, copy the example:

```bash
cp .env.example .env        # macOS / Linux
copy .env.example .env      # Windows
```

The default mode is `fixture`, which uses sample openFDA data saved in
`data/fixtures` and works without internet access. Switch to `live` to query
api.fda.gov for real.

## 5. Run the server

```bash
python -m uvicorn app.main:app --reload
```

Leave this running. `--reload` restarts the server automatically whenever you
edit a file. Stop it with `Ctrl+C`.

## 6. Try it

**In your browser**

- <http://127.0.0.1:8000/health>
- <http://127.0.0.1:8000/products>
- <http://127.0.0.1:8000/products/heartlink-app>
- <http://127.0.0.1:8000/updates?jurisdiction=EU&tag=ai>
- <http://127.0.0.1:8000/clearances?query=pacemaker>
- <http://127.0.0.1:8000/recalls?query=ablation&since=2023-01-01>

**Interactive docs (Swagger UI)**

Open <http://127.0.0.1:8000/docs>. Every endpoint is listed with its
parameters. Click one, press **Try it out**, fill in values and press
**Execute** to see the request and the response.

**From the terminal with curl**

```bash
curl "http://127.0.0.1:8000/health"
curl "http://127.0.0.1:8000/products"
curl "http://127.0.0.1:8000/products/orbit-surgical"
curl "http://127.0.0.1:8000/updates?jurisdiction=FDA&since=2025-01-01"
curl "http://127.0.0.1:8000/clearances?query=ablation%20catheter&limit=5"
curl "http://127.0.0.1:8000/recalls?query=defibrillator&since=2023-01-01&limit=5"
```

(On Windows PowerShell, `curl` is an alias for `Invoke-WebRequest`; use
`curl.exe` instead, or just use the browser.)

## 7. Endpoints

| Endpoint | What it returns |
| --- | --- |
| `GET /version` | `{"version": "1.1.0"}` |
| `GET /health` | `{"status": "ok", "mode": "fixture"}` |
| `GET /health/detailed` | Overall status, data mode and per-component status/count for products, updates and the 510k, recall and classification fixtures |
| `GET /products` | All products from `data/portfolio.yaml` |
| `GET /products/{id}` | One product, or 404 |
| `GET /updates?jurisdiction=&tag=&since=YYYY-MM-DD` | Regulatory updates from `data/updates/*.md`, newest first, filtered |
| `GET /clearances?query=&limit=10` | 510(k) clearances whose device name contains every word in `query` |
| `GET /recalls?query=&since=YYYY-MM-DD&limit=10` | Recalls whose product description contains every word in `query`, initiated on or after `since` |

The `since` filter includes records dated exactly on the requested date.
Update front-matter dates use year-month-day order (`YYYY-MM-DD` or `YYYYMMDD`),
never year-day-month. An unreadable update date produces HTTP 500 when filtered;
an invalid `since` query parameter produces HTTP 422.

The detailed health check returns HTTP 200 when all local datasets load successfully
and contain records, or HTTP 503 with an error detail for each failing component.
All components are checked even if one fails. It never calls openFDA, including
in `live` mode; it checks local fixtures rather than external service availability.
The existing `/health` endpoint remains a lightweight liveness check.

## 8. Run the tests

```bash
python -m pytest -q
```

The tests use local data and the saved fixtures only, so they pass without
internet access.

GitHub Actions runs `python -m pytest` with Python 3.12 after installing
`requirements.txt`. The `tests` job runs only for pull requests targeting `main`
when opened, reopened, or updated with new commits; pushes alone do not trigger it.

## 9. Environment variables

| Variable | Default | Meaning |
| --- | --- | --- |
| `OPENFDA_MODE` | `fixture` | `fixture` reads `data/fixtures/*.json`; `live` calls api.fda.gov |
| `OPENFDA_API_KEY` | *(empty)* | Optional openFDA API key; raises the rate limit in live mode |
| `OPENFDA_BASE_URL` | `https://api.fda.gov` | Base URL for live mode |
| `OPENFDA_TIMEOUT_SECONDS` | `10` | How long to wait for openFDA before giving up |

Values are read from your shell environment first, then from `.env`.

Tip: in `live` mode, leave `OPENFDA_API_KEY` empty unless you have a real key.
openFDA answers `403` to a wrong key, and the service then reports that error.

## 10. Project structure

```
.
├── app/
│   ├── main.py        FastAPI app and the routes
│   ├── models.py      pydantic models for what the API returns
│   ├── config.py      settings from environment variables / .env
│   ├── portfolio.py   loads data/portfolio.yaml and data/updates/*.md
│   └── openfda.py     the only module that fetches FDA data (live or fixtures)
├── data/
│   ├── portfolio.yaml six Acme MedTech products
│   ├── updates/       eight regulatory updates as markdown with front matter
│   ├── fixtures/      real openFDA sample responses: 510k, recall, classification
│   └── archive/       one large synthetic news file (not used by the app)
├── scripts/
│   └── generate_archive.py   regenerates data/archive/news_dump.jsonl
├── tests/             pytest tests (local data and fixtures only, no network)
├── requirements.txt
├── .env.example       template for your .env
└── README.md
```

## About the data

Acme MedTech and its products are fictional. The regulatory updates are
training summaries written in general terms; always verify against the linked
official source. openFDA is a public API from the U.S. FDA and its own
disclaimer applies: the data is not validated and must not be used to make
decisions about medical care. The saved fixtures are real responses captured
in September 2026, lightly trimmed to keep the files small.
