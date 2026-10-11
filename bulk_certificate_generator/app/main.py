"""FastAPI backend for bulk certificate generation using SQLite."""
from __future__ import annotations

import re
import sqlite3
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse

from app.certificates import generate_certificate

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DATABASE = BASE_DIR / "certificates.db"
DEFAULT_OUTPUT_DIR = BASE_DIR / "generated_certificates"
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect_db(database_path: str) -> sqlite3.Connection:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db(database_path: str) -> None:
    Path(database_path).parent.mkdir(parents=True, exist_ok=True)
    with connect_db(database_path) as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, event_name TEXT NOT NULL, issue_date TEXT NOT NULL,
                status TEXT NOT NULL, total_count INTEGER NOT NULL,
                success_count INTEGER NOT NULL DEFAULT 0, failure_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL, completed_at TEXT
            );
            CREATE TABLE IF NOT EXISTS recipients (
                id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
                name TEXT, email TEXT, status TEXT NOT NULL, certificate_path TEXT,
                error_message TEXT, created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_recipients_job_id ON recipients(job_id);
        """)


def validate_recipient(item: object) -> tuple[bool, str | None]:
    if not isinstance(item, dict):
        return False, "Recipient must be a JSON object."
    name, email = item.get("name"), item.get("email")
    if not isinstance(name, str) or not name.strip():
        return False, "Name is required and must be a non-empty string."
    if len(name.strip()) > 150:
        return False, "Name must be 150 characters or fewer."
    if not isinstance(email, str) or not EMAIL_RE.fullmatch(email.strip()):
        return False, "A valid email address is required."
    if len(email.strip()) > 254:
        return False, "Email must be 254 characters or fewer."
    return True, None


def create_app(test_config: dict | None = None) -> FastAPI:
    config = {"DATABASE": str(DEFAULT_DATABASE), "OUTPUT_DIR": str(DEFAULT_OUTPUT_DIR), "MAX_RECIPIENTS": 1000}
    if test_config:
        config.update(test_config)
    init_db(config["DATABASE"])
    Path(config["OUTPUT_DIR"]).mkdir(parents=True, exist_ok=True)
    api = FastAPI(title="Bulk Certificate Generator", version="1.0.0")

    def get_job(job_id: str):
        with connect_db(config["DATABASE"]) as db:
            job = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if not job:
                return None, []
            recipients = db.execute("SELECT * FROM recipients WHERE job_id = ? ORDER BY rowid", (job_id,)).fetchall()
            return dict(job), [dict(row) for row in recipients]

    @api.get("/health")
    def health():
        return {"status": "ok"}

    @api.post("/api/jobs", status_code=201)
    async def create_job(
        payload: dict = Body(
            ...,
            openapi_examples={
                "bulk_job_example": {
                    "summary": "Generate certificates for multiple recipients",
                    "value": {
                        "event_name": "Python Workshop",
                        "issue_date": "2026-10-11",
                        "recipients": [
                            {"name": "Arun Kumar", "email": "arun@example.com"},
                            {"name": "Priya S", "email": "priya@example.com"},
                        ],
                    },
                }
            },
        )
    ):
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="Request body must be a JSON object.")
        event_name, recipients = payload.get("event_name"), payload.get("recipients")
        issue_date = payload.get("issue_date", date.today().isoformat())
        if not isinstance(event_name, str) or not event_name.strip():
            raise HTTPException(status_code=400, detail="event_name is required.")
        if len(event_name.strip()) > 200:
            raise HTTPException(status_code=400, detail="event_name must be 200 characters or fewer.")
        if not isinstance(recipients, list) or not recipients:
            raise HTTPException(status_code=400, detail="recipients must be a non-empty list.")
        if len(recipients) > config["MAX_RECIPIENTS"]:
            raise HTTPException(status_code=400, detail=f"A maximum of {config['MAX_RECIPIENTS']} recipients is allowed per job.")
        try:
            datetime.strptime(issue_date, "%Y-%m-%d")
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="issue_date must use YYYY-MM-DD format.")

        job_id, created_at = str(uuid.uuid4()), utc_now()
        with connect_db(config["DATABASE"]) as db:
            db.execute("INSERT INTO jobs (id,event_name,issue_date,status,total_count,created_at) VALUES (?,?,?,'processing',?,?)",
                       (job_id, event_name.strip(), issue_date, len(recipients), created_at))
            for item in recipients:
                recipient_id = str(uuid.uuid4())
                valid, error = validate_recipient(item)
                name = item.get("name") if isinstance(item, dict) and isinstance(item.get("name"), str) else None
                email = item.get("email") if isinstance(item, dict) and isinstance(item.get("email"), str) else None
                db.execute("INSERT INTO recipients (id,job_id,name,email,status,error_message,created_at) VALUES (?,?,?,?,?,?,?)",
                           (recipient_id, job_id, name.strip() if name else None, email.strip() if email else None,
                            "pending" if valid else "failed", None if valid else error, created_at))

        # Synchronous by design. Each recipient is isolated so one failure does not stop the batch.
        job, saved_recipients = get_job(job_id)
        successes = failures = 0
        for recipient in saved_recipients:
            if recipient["status"] == "failed":
                failures += 1
                continue
            output_path = Path(config["OUTPUT_DIR"]) / job_id / f"{recipient['id']}.pdf"
            try:
                generate_certificate(output_path, recipient["name"], job["event_name"], job["issue_date"], recipient["id"])
                with connect_db(config["DATABASE"]) as db:
                    db.execute("UPDATE recipients SET status='success',certificate_path=?,error_message=NULL WHERE id=?",
                               (str(output_path.resolve()), recipient["id"]))
                successes += 1
            except Exception as exc:
                output_path.unlink(missing_ok=True)
                with connect_db(config["DATABASE"]) as db:
                    db.execute("UPDATE recipients SET status='failed',error_message=? WHERE id=?",
                               (f"Certificate generation failed: {type(exc).__name__}", recipient["id"]))
                failures += 1

        status = "completed" if failures == 0 else ("failed" if successes == 0 else "completed_with_errors")
        with connect_db(config["DATABASE"]) as db:
            db.execute("UPDATE jobs SET status=?,success_count=?,failure_count=?,completed_at=? WHERE id=?",
                       (status, successes, failures, utc_now(), job_id))
        job, saved_recipients = get_job(job_id)
        return {"job_id": job_id, "status": job["status"], "total_count": job["total_count"],
                "success_count": job["success_count"], "failure_count": job["failure_count"],
                "status_url": f"/api/jobs/{job_id}",
                "recipients": [{"recipient_id": r["id"], "name": r["name"], "email": r["email"],
                                "status": r["status"], "error": r["error_message"]} for r in saved_recipients]}

    @api.get("/api/jobs/{job_id}")
    def job_status(job_id: str):
        job, recipients = get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found.")
        return {"job_id": job["id"], "event_name": job["event_name"], "issue_date": job["issue_date"],
                "status": job["status"], "total_count": job["total_count"], "success_count": job["success_count"],
                "failure_count": job["failure_count"], "created_at": job["created_at"], "completed_at": job["completed_at"],
                "recipients": [{"recipient_id": r["id"], "name": r["name"], "email": r["email"],
                                "status": r["status"], "error": r["error_message"],
                                "download_url": f"/api/jobs/{job_id}/certificates/{r['id']}" if r["status"] == "success" else None}
                               for r in recipients]}

    @api.get("/api/jobs/{job_id}/certificates/{recipient_id}")
    def download_certificate(job_id: str, recipient_id: str):
        with connect_db(config["DATABASE"]) as db:
            row = db.execute("SELECT status,certificate_path FROM recipients WHERE id=? AND job_id=?",
                             (recipient_id, job_id)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Recipient certificate not found for this job.")
        if row["status"] != "success" or not row["certificate_path"]:
            raise HTTPException(status_code=409, detail="Certificate is not available because generation did not succeed.")
        path = Path(row["certificate_path"])
        if not path.is_file():
            raise HTTPException(status_code=410, detail="Certificate file is missing from storage.")
        return FileResponse(path, media_type="application/pdf", filename=f"certificate-{recipient_id}.pdf")

    return api


app = create_app()
