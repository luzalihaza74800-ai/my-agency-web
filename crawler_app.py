#!/usr/bin/env python3
"""
Firecrawl 網站爬取 Web 應用

功能：
- 透過網頁介面操控爬取任務
- 支援斷點續傳（暫停後可繼續）
- 即時顯示爬取進度與結果
- 結果可下載為 JSON
- 支援 fast_mode（略過 JS 渲染，適合重型網頁）
"""

import json
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template, request, send_file

load_dotenv()

app = Flask(__name__, template_folder="templates", static_folder="static")

DATA_DIR = Path("crawl_data")
DATA_DIR.mkdir(exist_ok=True)

API_KEY = os.getenv("FIRECRAWL_API_KEY", "")

SCRAPE_TIMEOUT = 60000


class CrawlJob:
    """管理單一爬取任務的狀態，支援暫停 / 續傳"""

    STATEFILE_SUFFIX = "_state.json"

    def __init__(self, job_id: str, url: str, max_depth: int = 2,
                 limit: int = 50, fast_mode: bool = False):
        self.job_id = job_id
        self.url = url
        self.max_depth = max_depth
        self.limit = limit
        self.fast_mode = fast_mode
        self.status = "pending"
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.updated_at = self.created_at

        self.discovered_urls: list[str] = []
        self.scraped_urls: list[str] = []
        self.failed_urls: list[str] = []
        self.results: list[dict] = []
        self.logs: list[str] = []
        self.error: str | None = None

        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._generation = 0

    # -- persistence --

    @property
    def _state_path(self) -> Path:
        return DATA_DIR / f"{self.job_id}{self.STATEFILE_SUFFIX}"

    def save(self):
        with self._lock:
            payload = {
                "job_id": self.job_id,
                "url": self.url,
                "max_depth": self.max_depth,
                "limit": self.limit,
                "fast_mode": self.fast_mode,
                "status": self.status,
                "created_at": self.created_at,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "discovered_urls": self.discovered_urls,
                "scraped_urls": self.scraped_urls,
                "failed_urls": self.failed_urls,
                "logs": self.logs[-300:],
                "error": self.error,
            }
            with open(self._state_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            self._save_results()

    def _save_results(self):
        p = DATA_DIR / f"{self.job_id}_results.json"
        with open(p, "w", encoding="utf-8") as f:
            json.dump(self.results, f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, job_id: str) -> "CrawlJob":
        p = DATA_DIR / f"{job_id}{cls.STATEFILE_SUFFIX}"
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        job = cls(data["job_id"], data["url"], data["max_depth"],
                  data["limit"], data.get("fast_mode", False))
        job.status = data["status"]
        job.created_at = data["created_at"]
        job.updated_at = data.get("updated_at", job.created_at)
        job.discovered_urls = data.get("discovered_urls", [])
        job.scraped_urls = data.get("scraped_urls", [])
        job.failed_urls = data.get("failed_urls", [])
        job.logs = data.get("logs", [])
        job.error = data.get("error")
        rp = DATA_DIR / f"{job_id}_results.json"
        if rp.exists():
            with open(rp, encoding="utf-8") as f:
                job.results = json.load(f)
        if job.status == "running":
            job.status = "paused"
        return job

    def _log(self, msg: str):
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        self.logs.append(f"[{ts}] {msg}")

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "url": self.url,
            "max_depth": self.max_depth,
            "limit": self.limit,
            "fast_mode": self.fast_mode,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "total_discovered": len(self.discovered_urls),
            "total_scraped": len(self.scraped_urls),
            "total_failed": len(self.failed_urls),
            "logs": self.logs[-50:],
            "error": self.error,
        }

    # -- crawl control --

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._generation += 1
        self._stop_event.clear()
        self.status = "running"
        self.save()
        gen = self._generation
        self._thread = threading.Thread(target=self._run, args=(gen,), daemon=True)
        self._thread.start()

    def pause(self):
        self._stop_event.set()
        self.status = "paused"
        self._log("使用者暫停任務")
        self.save()

    def force_resume(self):
        self._stop_event.set()
        time.sleep(0.2)
        self._generation += 1
        self._stop_event.clear()
        self.status = "running"
        self.save()
        gen = self._generation
        self._thread = threading.Thread(target=self._run, args=(gen,), daemon=True)
        self._thread.start()

    # -- crawl logic --

    def _run(self, my_gen: int):
        from firecrawl import FirecrawlApp
        fc = FirecrawlApp(api_key=API_KEY)

        def stale():
            return self._generation != my_gen

        try:
            # Phase 1: discover URLs via map API
            if not self.discovered_urls:
                self._log(f"正在探索網站地圖：{self.url}")
                self.save()
                try:
                    map_result = fc.map(self.url, limit=self.limit)
                    if hasattr(map_result, "links") and map_result.links:
                        urls = []
                        seen = set()
                        for link in map_result.links:
                            u = link.url if hasattr(link, "url") else str(link)
                            if u not in seen:
                                urls.append(u)
                                seen.add(u)
                        self.discovered_urls = urls
                    elif isinstance(map_result, list):
                        self.discovered_urls = list(
                            dict.fromkeys(str(u) for u in map_result)
                        )
                except Exception as exc:
                    self._log(f"Map 失敗（{exc}），使用原始 URL")
                    self.discovered_urls = [self.url]

                if not self.discovered_urls:
                    self.discovered_urls = [self.url]

                if self.limit and len(self.discovered_urls) > self.limit:
                    self.discovered_urls = self.discovered_urls[: self.limit]

                self._log(f"發現 {len(self.discovered_urls)} 個頁面")
                self.save()

            if stale():
                return

            # Phase 2: scrape each URL
            already = set(self.scraped_urls) | set(self.failed_urls)
            pending = [u for u in self.discovered_urls if u not in already]
            self._log(f"待爬取 {len(pending)} 頁（已完成 {len(already)}）")

            for url in pending:
                if self._stop_event.is_set() or stale():
                    if not stale():
                        self._log("偵測到暫停信號，中斷爬取")
                    break

                self._log(f"正在抓取：{url}")
                try:
                    scrape_kwargs: dict = {
                        "formats": ["markdown"],
                        "timeout": SCRAPE_TIMEOUT,
                    }
                    if self.fast_mode:
                        scrape_kwargs["fast_mode"] = True

                    doc = fc.scrape(url, **scrape_kwargs)

                    if stale():
                        break

                    data = (
                        doc.model_dump()
                        if hasattr(doc, "model_dump")
                        else (
                            doc.__dict__
                            if hasattr(doc, "__dict__")
                            else {"raw": str(doc)}
                        )
                    )
                    md = data.get("markdown", "")
                    if url not in set(self.scraped_urls):
                        self.results.append(
                            {
                                "url": url,
                                "markdown": md,
                                "metadata": data.get("metadata", {}),
                                "scraped_at": datetime.now(timezone.utc).isoformat(),
                            }
                        )
                        self.scraped_urls.append(url)
                    preview = (
                        (md[:60] + "...") if md and len(md) > 60 else (md or "(空)")
                    )
                    self._log(f"✓ 成功：{preview}")
                except Exception as exc:
                    if stale():
                        break
                    err = str(exc)
                    if url not in set(self.failed_urls):
                        self.results.append(
                            {
                                "url": url,
                                "markdown": None,
                                "metadata": {},
                                "error": err,
                                "scraped_at": datetime.now(timezone.utc).isoformat(),
                            }
                        )
                        self.failed_urls.append(url)
                    short_err = err[:120] + "..." if len(err) > 120 else err
                    self._log(f"✗ 失敗：{short_err}")

                if not stale():
                    self.save()
                time.sleep(0.3)

            if not self._stop_event.is_set() and not stale():
                self.status = "completed"
                self._log(
                    f"爬取完成！成功 {len(self.scraped_urls)}，失敗 {len(self.failed_urls)}"
                )
                self.save()
        except Exception as exc:
            if not stale():
                self.error = str(exc)
                self.status = "failed"
                self._log(f"嚴重錯誤：{exc}")
                self.save()


# ---------------------------------------------------------------------------
# In-memory job registry
# ---------------------------------------------------------------------------

jobs: dict[str, CrawlJob] = {}


def _load_existing_jobs():
    for p in DATA_DIR.glob(f"*{CrawlJob.STATEFILE_SUFFIX}"):
        jid = p.name.replace(CrawlJob.STATEFILE_SUFFIX, "")
        try:
            jobs[jid] = CrawlJob.load(jid)
        except Exception:
            pass


_load_existing_jobs()


# ---------------------------------------------------------------------------
# Flask Routes
# ---------------------------------------------------------------------------


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/jobs", methods=["GET"])
def list_jobs():
    return jsonify([j.to_dict() for j in jobs.values()])


@app.route("/api/jobs", methods=["POST"])
def create_job():
    data = request.json or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "url is required"}), 400
    max_depth = int(data.get("max_depth", 2))
    limit = int(data.get("limit", 50))
    fast_mode = bool(data.get("fast_mode", False))
    job_id = str(uuid.uuid4())[:8]
    job = CrawlJob(job_id, url, max_depth, limit, fast_mode)
    jobs[job_id] = job
    job.start()
    return jsonify(job.to_dict()), 201


@app.route("/api/jobs/<job_id>", methods=["GET"])
def get_job(job_id: str):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "job not found"}), 404
    return jsonify(job.to_dict())


@app.route("/api/jobs/<job_id>/pause", methods=["POST"])
def pause_job(job_id: str):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "job not found"}), 404
    job.pause()
    return jsonify(job.to_dict())


@app.route("/api/jobs/<job_id>/resume", methods=["POST"])
def resume_job(job_id: str):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "job not found"}), 404
    if job.status not in ("paused", "failed"):
        return jsonify({"error": f"cannot resume from status '{job.status}'"}), 400
    job.force_resume()
    return jsonify(job.to_dict())


@app.route("/api/jobs/<job_id>/retry-failed", methods=["POST"])
def retry_failed(job_id: str):
    """將失敗的 URL 重新排入待爬取清單"""
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "job not found"}), 404
    if job.status == "running":
        return jsonify({"error": "job is still running"}), 400
    if not job.failed_urls:
        return jsonify({"error": "no failed URLs to retry"}), 400
    job.results = [r for r in job.results if r.get("url") not in set(job.failed_urls)]
    job.failed_urls.clear()
    job.force_resume()
    return jsonify(job.to_dict())


@app.route("/api/jobs/<job_id>/results", methods=["GET"])
def get_results(job_id: str):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "job not found"}), 404
    return jsonify(job.results)


@app.route("/api/jobs/<job_id>/results/<int:idx>", methods=["GET"])
def get_result_item(job_id: str, idx: int):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "job not found"}), 404
    if idx < 0 or idx >= len(job.results):
        return jsonify({"error": "index out of range"}), 404
    return jsonify(job.results[idx])


@app.route("/api/jobs/<job_id>/download", methods=["GET"])
def download_results(job_id: str):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "job not found"}), 404
    p = DATA_DIR / f"{job_id}_results.json"
    if not p.exists():
        return jsonify({"error": "no results yet"}), 404
    return send_file(p, as_attachment=True, download_name=f"crawl_{job_id}.json")


@app.route("/api/jobs/<job_id>/stream")
def stream_job(job_id: str):
    """SSE endpoint: push progress updates"""
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "job not found"}), 404

    def generate():
        last_count = -1
        while True:
            cur = len(job.scraped_urls) + len(job.failed_urls)
            status = job.status
            if cur != last_count or status in ("completed", "failed", "paused"):
                payload = json.dumps(job.to_dict(), ensure_ascii=False)
                yield f"data: {payload}\n\n"
                last_count = cur
            if status in ("completed", "failed", "paused"):
                break
            time.sleep(1)

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/api/jobs/<job_id>", methods=["DELETE"])
def delete_job(job_id: str):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "job not found"}), 404
    if job.status == "running":
        job.pause()
    for suffix in (CrawlJob.STATEFILE_SUFFIX, "_results.json"):
        p = DATA_DIR / f"{job_id}{suffix}"
        p.unlink(missing_ok=True)
    del jobs[job_id]
    return jsonify({"ok": True})


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    print(f"啟動爬取管理介面：http://0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
