# Bulk Certificate Generator Backend

A small REST API that creates PDF certificates for multiple recipients in one request. It uses FastAPI, SQLite (Python's built-in `sqlite3` module), and ReportLab.

## Features

- One bulk request creates a generation job for multiple recipients.
- Validates the event name, issue date, recipient name, and email.
- Generates one PDF per valid recipient from a single predefined template.
- Stores job and recipient status in a relational SQLite database.
- Records individual failures without stopping the rest of the batch.
- Exposes job progress/results and individual certificate download endpoints.
- Includes automated API tests.

## Requirements

- Python 3.10 or newer
- pip

## Setup

From this directory, create and activate a virtual environment:

```bash
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
# macOS/Linux
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

## Run the application

```bash
python run.py
```

The API runs at `http://127.0.0.1:5000`. Interactive API documentation is available at `http://127.0.0.1:5000/docs`. The SQLite database is created automatically as `certificates.db`; generated PDFs are stored under `generated_certificates/`.

Health check:

```bash
curl http://127.0.0.1:5000/health
```

## Create a bulk generation job

Send one POST request to `/api/jobs`:

```bash
curl -X POST http://127.0.0.1:5000/api/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "event_name": "Python Bootcamp",
    "issue_date": "2026-10-10",
    "recipients": [
      {"name": "Asha Kumar", "email": "asha@example.com"},
      {"name": "Bala Raj", "email": "bala@example.com"}
    ]
  }'
```

`issue_date` is optional and defaults to the current date. Each recipient needs a non-empty name (up to 150 characters) and a valid email address. The default maximum is 1,000 recipients per request.

A successful request returns HTTP `201`, a `job_id`, counts, each recipient's result, and a `status_url`. The job is processed synchronously, so its final status is usually available in the response.

## Check job status

```bash
curl http://127.0.0.1:5000/api/jobs/<job_id>
```

Job statuses:

- `processing`: work is in progress.
- `completed`: all certificates were generated.
- `completed_with_errors`: at least one succeeded and at least one failed.
- `failed`: no certificate succeeded.

Recipient statuses are `pending`, `success`, or `failed`. Failed recipients include an error message. Successful recipients include a download URL in the status response.

## Download a certificate

```bash
curl -OJ http://127.0.0.1:5000/api/jobs/<job_id>/certificates/<recipient_id>
```

The endpoint returns a PDF attachment. A recipient must belong to the specified job and have a successfully generated certificate.

## Run tests

```bash
pytest -q
```

Tests cover job creation, input validation, PDF generation, status/progress, isolated generation failure, certificate retrieval, and unknown jobs.

## Design decisions and limitations

- **FastAPI:** a readable framework for REST endpoints with automatic OpenAPI documentation.
- **SQLite:** a relational database with no separate database server required. The schema separates jobs from recipients and links recipients to jobs using a foreign key.
- **ReportLab:** generates PDFs in Python without an external office application.
- **Synchronous processing:** selected to keep this assignment easy to run and test. The API call remains open until all recipients are processed, so a large batch can take time. For production-scale workloads, use a background queue/worker and return `202 Accepted` with a job ID immediately.
- **Per-recipient isolation:** validation and generation failures are recorded against that recipient; processing continues for the rest of the batch.
- **One fixed template:** intentionally no template editor or multiple designs, as requested.
- **Storage:** PDFs are saved locally and the database stores their paths. A production deployment would use durable shared/object storage and appropriate retention/access controls.
- **Authentication and rate limiting:** not included because they are outside the assignment's stated minimum requirements.
