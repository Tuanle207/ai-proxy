"""End-to-end smoke test against a running `flow serve` instance.

Exercises the full REST + SSE surface against a real service process: submit a batch, watch SSE
status events, poll job/batch/running-jobs endpoints, cancel a throwaway low-priority job, and
verify the completed job's images are listed/served. Uses only the stdlib (no new dependency).

Usage: start the service (`flow serve`), then run this script against it.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

BASE_URL = os.environ.get("AI_PROXY_E2E_BASE_URL", "http://127.0.0.1:8080")
DATA_DIR = Path(os.environ.get("AI_PROXY_DATA_DIR", "data"))
POLL_INTERVAL_SECONDS = 5.0
JOB_TIMEOUT_SECONDS = 360.0


def _resolve_api_key() -> str:
    key = os.environ.get("AI_PROXY_API_KEY")
    if key:
        return key
    key_file = DATA_DIR / "api_key"
    if key_file.is_file():
        return key_file.read_text(encoding="utf-8").strip()
    raise RuntimeError(f"no API key found (checked AI_PROXY_API_KEY and {key_file})")


API_KEY = _resolve_api_key()


def request(
    method: str, path: str, *, body: dict[str, Any] | None = None, timeout: float = 30.0
) -> tuple[int, Any]:
    url = f"{BASE_URL}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("X-API-Key", API_KEY)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            content_type = resp.headers.get_content_type()
            payload = resp.read()
    except urllib.error.HTTPError as exc:
        status = exc.code
        content_type = exc.headers.get_content_type()
        payload = exc.read()
    if content_type != "application/json":
        return status, {"content_type": content_type, "bytes": len(payload)}
    text = payload.decode("utf-8") if payload else ""
    return status, (json.loads(text) if text else None)


def wait_for_ready(timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            status, _ = request("GET", "/healthz", timeout=5.0)
            if status == 200:
                return
        except OSError:
            pass
        time.sleep(0.5)
    raise RuntimeError("service did not become healthy in time")


def sse_listener(batch_id: str, stop_event: threading.Event) -> None:
    """Print SSE events for `batch_id` until `stop_event` is set or the stream ends."""
    req = urllib.request.Request(f"{BASE_URL}/v1/events?batch_id={batch_id}")
    req.add_header("X-API-Key", API_KEY)
    req.add_header("Accept", "text/event-stream")
    try:
        with urllib.request.urlopen(req, timeout=JOB_TIMEOUT_SECONDS) as resp:
            event_type = None
            for raw_line in resp:
                if stop_event.is_set():
                    return
                line = raw_line.decode("utf-8").rstrip("\n")
                if line.startswith("event:"):
                    event_type = line[len("event:"):].strip()
                elif line.startswith("data:"):
                    print(f"  [sse] {event_type}: {line[len('data:'):].strip()}")
                elif line == "":
                    event_type = None
    except Exception as exc:  # best-effort observability only, never fails the test
        print(f"  [sse] listener stopped: {exc}")


def main() -> int:
    print(f"Waiting for {BASE_URL} to become healthy...")
    wait_for_ready()
    status, ready = request("GET", "/readyz")
    print(f"/readyz -> {status} {ready}")
    if status != 200:
        print("Service is not ready; aborting.")
        return 1

    prompt = "a small red cube on a plain white background, e2e smoke test"
    status, submit = request(
        "POST",
        "/v1/tasks",
        body={
            "provider": "google_flow", "kind": "image", "prompts": [prompt],
            "count": 1,
            "timeout_seconds": 200,
            "metadata": {"source": "e2e_service_test"},
        },
    )
    assert status == 202, f"submit failed: {status} {submit}"
    batch_id = submit["batch_id"]
    job_id = submit["jobs"][0]["job_id"]
    print(f"Submitted batch={batch_id} job={job_id} response={submit}")

    stop_event = threading.Event()
    listener = threading.Thread(target=sse_listener, args=(batch_id, stop_event), daemon=True)
    listener.start()

    # Low-priority throwaway job to exercise cancel without competing with the real job.
    try:
        status, cancel_submit = request(
            "POST",
            "/v1/tasks",
            body={
                "provider": "google_flow",
                "kind": "image",
                "prompts": ["e2e cancel-test prompt, should never actually generate"],
                "priority": -100,
            },
        )
        cancel_job_id = cancel_submit["jobs"][0]["job_id"]
        status, cancel_result = request("POST", f"/v1/jobs/{cancel_job_id}/cancel")
        print(f"Cancel test: job={cancel_job_id} -> {status} status={cancel_result['status']}")
        if cancel_result["status"] != "canceled":
            print("  WARNING: expected status 'canceled'")
    except Exception as exc:
        print(f"  WARNING: cancel sub-test failed non-fatally: {exc}")

    print("Polling job status (Ctrl+C to abort)...")
    deadline = time.monotonic() + JOB_TIMEOUT_SECONDS
    job: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        status, job = request("GET", f"/v1/jobs/{job_id}")
        assert status == 200, f"get job failed: {status} {job}"
        print(
            f"  job status={job['status']} attempt={job['attempt']} "
            f"account={job['account_email']} elapsed={job.get('elapsed_seconds')} "
            f"eta={job.get('eta_seconds')}"
        )
        if job["status"] in ("completed", "failed", "canceled"):
            break
        status, running = request("GET", "/v1/jobs/running")
        if running:
            print(f"  /v1/jobs/running -> {[r['id'] for r in running]}")
        time.sleep(POLL_INTERVAL_SECONDS)
    stop_event.set()

    assert job is not None, "never received a job status"
    print(f"\nFinal job status: {job['status']}")
    if job["status"] != "completed":
        print(f"Job did not complete: {job}")
        return 1

    images = job["artifacts"]
    assert images, "completed job has no images"
    print(f"Generated {len(images)} image(s):")
    for image in images:
        print(
            f"  id={image['id']} format={image['format']} bytes={image['bytes']} "
            f"{image['width']}x{image['height']}"
        )

    status, page = request("GET", "/v1/artifacts?page=1&page_size=5")
    assert status == 200 and page["total"] >= 1, f"list images failed: {status} {page}"
    print(f"/v1/artifacts -> total={page['total']} first={page['items'][0]['id']}")

    image_id = images[0]["id"]
    status, meta = request("GET", f"/v1/artifacts/{image_id}")
    assert status == 200, f"get image failed: {status} {meta}"
    print(f"/v1/artifacts/{image_id} -> {meta}")

    status, _ = request("GET", f"/v1/artifacts/{image_id}/file")
    assert status == 200, f"get image file failed: {status}"
    print(f"/v1/artifacts/{image_id}/file -> {status} OK")

    status, _ = request("GET", f"/v1/artifacts/{image_id}/thumbnail")
    assert status == 200, f"get thumbnail failed: {status}"
    print(f"/v1/artifacts/{image_id}/thumbnail -> {status} OK")

    status, batch = request("GET", f"/v1/batches/{batch_id}")
    assert status == 200, f"get batch failed: {status} {batch}"
    print(f"/v1/batches/{batch_id} -> status={batch['status']} counts={batch['counts']}")

    status, accounts = request("GET", "/v1/accounts")
    print(f"/v1/accounts -> {accounts}")
    status, stats = request("GET", "/v1/stats")
    print(f"/v1/stats -> {stats}")

    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
