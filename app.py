import os
import json
import time
import uuid
import threading
from datetime import datetime

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from firecrawl import Firecrawl
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__, static_folder="static")
CORS(app)

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crawl_data")
os.makedirs(DATA_DIR, exist_ok=True)

crawl_jobs = {}
crawl_lock = threading.Lock()


def get_firecrawl_client():
    api_key = os.environ.get("FIRECRAWL_API_KEY", "")
    if not api_key:
        raise ValueError("FIRECRAWL_API_KEY is not set")
    return Firecrawl(api_key=api_key)


def save_job_state(job_id):
    """Persist job state to disk for resume capability."""
    with crawl_lock:
        if job_id not in crawl_jobs:
            return
        job = crawl_jobs[job_id]

    state_file = os.path.join(DATA_DIR, f"{job_id}.json")
    serializable = {
        "job_id": job["job_id"],
        "url": job["url"],
        "status": job["status"],
        "firecrawl_id": job.get("firecrawl_id"),
        "created_at": job["created_at"],
        "updated_at": job.get("updated_at", ""),
        "completed": job.get("completed", 0),
        "total": job.get("total", 0),
        "error": job.get("error"),
        "pages": job.get("pages", []),
        "crawl_options": job.get("crawl_options", {}),
    }
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(serializable, f, ensure_ascii=False, indent=2)


def load_all_jobs():
    """Load all persisted jobs from disk on startup."""
    for fname in os.listdir(DATA_DIR):
        if fname.endswith(".json"):
            fpath = os.path.join(DATA_DIR, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                job_id = data["job_id"]
                crawl_jobs[job_id] = data
            except Exception:
                pass


def poll_crawl_status(job_id):
    """Background thread to poll Firecrawl crawl status."""
    try:
        client = get_firecrawl_client()
    except Exception as e:
        with crawl_lock:
            if job_id in crawl_jobs:
                crawl_jobs[job_id]["status"] = "failed"
                crawl_jobs[job_id]["error"] = str(e)
                crawl_jobs[job_id]["updated_at"] = datetime.now().isoformat()
        save_job_state(job_id)
        return

    while True:
        with crawl_lock:
            job = crawl_jobs.get(job_id)
            if not job:
                return
            if job["status"] in ("completed", "failed", "cancelled"):
                return
            firecrawl_id = job.get("firecrawl_id")

        if not firecrawl_id:
            time.sleep(2)
            continue

        try:
            from firecrawl.v2.types import PaginationConfig
            status = client.get_crawl_status(
                firecrawl_id,
                pagination_config=PaginationConfig(auto_paginate=False)
            )

            with crawl_lock:
                job = crawl_jobs.get(job_id)
                if not job:
                    return

                job["updated_at"] = datetime.now().isoformat()

                crawl_status = getattr(status, "status", None)
                completed_count = getattr(status, "completed", 0) or 0
                total_count = getattr(status, "total", 0) or 0
                data = getattr(status, "data", []) or []

                job["completed"] = completed_count
                job["total"] = total_count

                existing_urls = {p["url"] for p in job.get("pages", [])}
                for doc in data:
                    md = getattr(doc, "markdown", "") or ""
                    html_content = getattr(doc, "html", "") or ""
                    meta = getattr(doc, "metadata", None)
                    source_url = ""
                    title = ""
                    if meta:
                        source_url = getattr(meta, "source_url", "") or getattr(meta, "sourceURL", "") or ""
                        title = getattr(meta, "title", "") or getattr(meta, "og_title", "") or ""

                    if source_url and source_url not in existing_urls:
                        page_data = {
                            "url": source_url,
                            "title": title,
                            "markdown": md,
                            "html": html_content,
                            "scraped_at": datetime.now().isoformat(),
                        }
                        job["pages"].append(page_data)
                        existing_urls.add(source_url)

                if crawl_status == "completed":
                    next_url = getattr(status, "next", None)
                    if next_url:
                        job["status"] = "scraping"
                        threading.Thread(
                            target=fetch_remaining_pages,
                            args=(job_id, client, next_url),
                            daemon=True
                        ).start()
                        save_job_state(job_id)
                        return
                    else:
                        job["status"] = "completed"
                elif crawl_status == "failed":
                    job["status"] = "failed"
                    job["error"] = "Crawl failed on Firecrawl side"
                elif crawl_status == "cancelled":
                    job["status"] = "cancelled"
                else:
                    job["status"] = "crawling"

            save_job_state(job_id)

            if crawl_status in ("completed", "failed", "cancelled"):
                return

        except Exception as e:
            with crawl_lock:
                job = crawl_jobs.get(job_id)
                if job:
                    job["error"] = f"Poll error: {str(e)}"
                    job["updated_at"] = datetime.now().isoformat()
            save_job_state(job_id)

        time.sleep(3)


def fetch_remaining_pages(job_id, client, next_url):
    """Fetch remaining pages using pagination."""
    try:
        while next_url:
            status = client.get_crawl_status_page(next_url)
            data = getattr(status, "data", []) or []

            with crawl_lock:
                job = crawl_jobs.get(job_id)
                if not job:
                    return

                existing_urls = {p["url"] for p in job.get("pages", [])}
                for doc in data:
                    md = getattr(doc, "markdown", "") or ""
                    html_content = getattr(doc, "html", "") or ""
                    meta = getattr(doc, "metadata", None)
                    source_url = ""
                    title = ""
                    if meta:
                        source_url = getattr(meta, "source_url", "") or getattr(meta, "sourceURL", "") or ""
                        title = getattr(meta, "title", "") or getattr(meta, "og_title", "") or ""

                    if source_url and source_url not in existing_urls:
                        page_data = {
                            "url": source_url,
                            "title": title,
                            "markdown": md,
                            "html": html_content,
                            "scraped_at": datetime.now().isoformat(),
                        }
                        job["pages"].append(page_data)
                        existing_urls.add(source_url)

                job["updated_at"] = datetime.now().isoformat()

            next_url = getattr(status, "next", None)
            save_job_state(job_id)
            time.sleep(1)

        with crawl_lock:
            job = crawl_jobs.get(job_id)
            if job:
                job["status"] = "completed"
                job["updated_at"] = datetime.now().isoformat()
        save_job_state(job_id)

    except Exception as e:
        with crawl_lock:
            job = crawl_jobs.get(job_id)
            if job:
                job["status"] = "failed"
                job["error"] = f"Pagination error: {str(e)}"
                job["updated_at"] = datetime.now().isoformat()
        save_job_state(job_id)


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/crawl", methods=["POST"])
def start_crawl():
    """Start a new crawl job."""
    data = request.get_json() or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "URL is required"}), 400

    limit = data.get("limit", 100)
    scrape_formats = data.get("formats", ["markdown", "html"])

    job_id = str(uuid.uuid4())[:8]
    now = datetime.now().isoformat()

    job = {
        "job_id": job_id,
        "url": url,
        "status": "starting",
        "firecrawl_id": None,
        "created_at": now,
        "updated_at": now,
        "completed": 0,
        "total": 0,
        "error": None,
        "pages": [],
        "crawl_options": {
            "limit": limit,
            "formats": scrape_formats,
        },
    }

    with crawl_lock:
        crawl_jobs[job_id] = job

    save_job_state(job_id)
    threading.Thread(target=_start_crawl_async, args=(job_id,), daemon=True).start()

    return jsonify({"job_id": job_id, "status": "starting"})


def _start_crawl_async(job_id):
    """Actually start the crawl in a background thread."""
    with crawl_lock:
        job = crawl_jobs.get(job_id)
        if not job:
            return
        url = job["url"]
        options = job["crawl_options"]

    try:
        client = get_firecrawl_client()
        started = client.start_crawl(
            url=url,
            limit=options.get("limit", 100),
            scrape_options={"formats": options.get("formats", ["markdown", "html"])},
        )

        firecrawl_id = getattr(started, "id", None) or (started if isinstance(started, str) else None)
        if hasattr(started, "id"):
            firecrawl_id = started.id

        with crawl_lock:
            job = crawl_jobs.get(job_id)
            if job:
                job["firecrawl_id"] = firecrawl_id
                job["status"] = "crawling"
                job["updated_at"] = datetime.now().isoformat()

        save_job_state(job_id)
        poll_crawl_status(job_id)

    except Exception as e:
        with crawl_lock:
            job = crawl_jobs.get(job_id)
            if job:
                job["status"] = "failed"
                job["error"] = str(e)
                job["updated_at"] = datetime.now().isoformat()
        save_job_state(job_id)


@app.route("/api/crawl/<job_id>", methods=["GET"])
def get_crawl_status_api(job_id):
    """Get the status of a crawl job."""
    with crawl_lock:
        job = crawl_jobs.get(job_id)

    if not job:
        return jsonify({"error": "Job not found"}), 404

    return jsonify({
        "job_id": job["job_id"],
        "url": job["url"],
        "status": job["status"],
        "created_at": job["created_at"],
        "updated_at": job.get("updated_at", ""),
        "completed": job.get("completed", 0),
        "total": job.get("total", 0),
        "error": job.get("error"),
        "page_count": len(job.get("pages", [])),
    })


@app.route("/api/crawl/<job_id>/pages", methods=["GET"])
def get_crawl_pages(job_id):
    """Get the crawled pages of a job."""
    with crawl_lock:
        job = crawl_jobs.get(job_id)

    if not job:
        return jsonify({"error": "Job not found"}), 404

    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    pages = job.get("pages", [])
    start = (page - 1) * per_page
    end = start + per_page

    return jsonify({
        "total": len(pages),
        "page": page,
        "per_page": per_page,
        "pages": pages[start:end],
    })


@app.route("/api/crawl/<job_id>/page/<int:page_idx>", methods=["GET"])
def get_single_page(job_id, page_idx):
    """Get a single crawled page by index."""
    with crawl_lock:
        job = crawl_jobs.get(job_id)

    if not job:
        return jsonify({"error": "Job not found"}), 404

    pages = job.get("pages", [])
    if page_idx < 0 or page_idx >= len(pages):
        return jsonify({"error": "Page not found"}), 404

    return jsonify(pages[page_idx])


@app.route("/api/jobs", methods=["GET"])
def list_jobs():
    """List all crawl jobs."""
    with crawl_lock:
        jobs = []
        for job in crawl_jobs.values():
            jobs.append({
                "job_id": job["job_id"],
                "url": job["url"],
                "status": job["status"],
                "created_at": job["created_at"],
                "updated_at": job.get("updated_at", ""),
                "completed": job.get("completed", 0),
                "total": job.get("total", 0),
                "page_count": len(job.get("pages", [])),
                "error": job.get("error"),
            })

    jobs.sort(key=lambda x: x["created_at"], reverse=True)
    return jsonify({"jobs": jobs})


@app.route("/api/crawl/<job_id>/resume", methods=["POST"])
def resume_crawl(job_id):
    """Resume a failed or cancelled crawl by re-crawling missing pages."""
    with crawl_lock:
        job = crawl_jobs.get(job_id)

    if not job:
        return jsonify({"error": "Job not found"}), 404

    if job["status"] not in ("failed", "cancelled", "completed"):
        return jsonify({"error": "Job is still running"}), 400

    existing_pages = job.get("pages", [])
    existing_urls = {p["url"] for p in existing_pages}

    new_job_id = str(uuid.uuid4())[:8]
    now = datetime.now().isoformat()

    new_job = {
        "job_id": new_job_id,
        "url": job["url"],
        "status": "starting",
        "firecrawl_id": None,
        "created_at": now,
        "updated_at": now,
        "completed": 0,
        "total": 0,
        "error": None,
        "pages": list(existing_pages),
        "crawl_options": job.get("crawl_options", {}),
        "resumed_from": job_id,
    }

    with crawl_lock:
        crawl_jobs[new_job_id] = new_job

    save_job_state(new_job_id)
    threading.Thread(target=_start_crawl_async, args=(new_job_id,), daemon=True).start()

    return jsonify({
        "job_id": new_job_id,
        "resumed_from": job_id,
        "existing_pages": len(existing_pages),
        "status": "starting",
    })


@app.route("/api/crawl/<job_id>/cancel", methods=["POST"])
def cancel_crawl(job_id):
    """Cancel a running crawl job."""
    with crawl_lock:
        job = crawl_jobs.get(job_id)

    if not job:
        return jsonify({"error": "Job not found"}), 404

    if job["status"] in ("completed", "failed", "cancelled"):
        return jsonify({"error": "Job already finished"}), 400

    firecrawl_id = job.get("firecrawl_id")
    if firecrawl_id:
        try:
            client = get_firecrawl_client()
            client.cancel_crawl(firecrawl_id)
        except Exception:
            pass

    with crawl_lock:
        job["status"] = "cancelled"
        job["updated_at"] = datetime.now().isoformat()

    save_job_state(job_id)
    return jsonify({"status": "cancelled"})


@app.route("/api/crawl/<job_id>/export", methods=["GET"])
def export_crawl(job_id):
    """Export crawled data as JSON."""
    with crawl_lock:
        job = crawl_jobs.get(job_id)

    if not job:
        return jsonify({"error": "Job not found"}), 404

    export_data = {
        "job_id": job["job_id"],
        "url": job["url"],
        "status": job["status"],
        "created_at": job["created_at"],
        "page_count": len(job.get("pages", [])),
        "pages": job.get("pages", []),
    }

    return jsonify(export_data)


@app.route("/api/config", methods=["GET"])
def get_config():
    """Check if API key is configured."""
    api_key = os.environ.get("FIRECRAWL_API_KEY", "")
    return jsonify({
        "api_key_set": bool(api_key),
        "api_key_preview": f"{api_key[:8]}..." if len(api_key) > 8 else "",
    })


@app.route("/api/config", methods=["POST"])
def set_config():
    """Set the API key at runtime."""
    data = request.get_json() or {}
    api_key = data.get("api_key", "").strip()
    if not api_key:
        return jsonify({"error": "API key is required"}), 400

    os.environ["FIRECRAWL_API_KEY"] = api_key
    return jsonify({"status": "ok", "api_key_preview": f"{api_key[:8]}..."})


load_all_jobs()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
