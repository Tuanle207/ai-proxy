"""End-to-end smoke test against a running `aip serve` instance, for the Perplexity provider.

Submits a multi-line prompt shaped like the ai-proxy `ideas-generate` template (blank lines
between sections) to guard against the newline/Enter-submit fragmentation regression in
`core/browser/humanize.py::human_type` (typing a raw `\\n` submits early on composers that treat
bare Enter as "send", splitting one prompt into several thread messages). Watches SSE status
events, polls job/batch status, verifies exactly one text artifact came back, then resumes the
same thread (`workspace_ref`) with a short follow-up prompt to exercise multi-turn continuation.

Requires a running service (`aip serve`) with at least one logged-in, active Perplexity account
(`aip accounts --provider perplexity add`, then `aip accounts --provider perplexity login`).

Usage: start the service, then run this script against it.
    .venv\\Scripts\\python scripts\\e2e_perplexity_test.py
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
POLL_INTERVAL_SECONDS = 3.0
JOB_TIMEOUT_SECONDS = 240.0

PROMPT = """Generate 5-7 short talking points for an English learning podcast episode on the topic:

Everyday small talk at a coffee shop

Some pre-provided initial talking points (optional):

N/A

Output Format (Markdown - no other header, footer, or description text):
1. Title: Focus
2. Title: Focus
...
"""

FOLLOW_UP_PROMPT = "Make talking point #1 a bit more specific."


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


def submit_and_wait(prompt: str, *, workspace_ref: str | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {
        "provider": "perplexity",
        "kind": "text",
        "prompts": [prompt],
        "timeout_seconds": 180,
        "metadata": {"source": "e2e_perplexity_test"},
    }
    if workspace_ref:
        body["workspace_ref"] = workspace_ref
    status, submit = request("POST", "/v1/tasks", body=body)
    assert status == 202, f"submit failed: {status} {submit}"
    batch_id = submit["batch_id"]
    job_id = submit["jobs"][0]["job_id"]
    print(f"Submitted batch={batch_id} job={job_id} workspace_ref={workspace_ref}")

    stop_event = threading.Event()
    listener = threading.Thread(target=sse_listener, args=(batch_id, stop_event), daemon=True)
    listener.start()

    print("Polling job status (Ctrl+C to abort)...")
    deadline = time.monotonic() + JOB_TIMEOUT_SECONDS
    job: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        status, job = request("GET", f"/v1/jobs/{job_id}")
        assert status == 200, f"get job failed: {status} {job}"
        print(
            f"  job status={job['status']} attempt={job['attempt']} "
            f"account={job['account_email']} workspace_ref={job.get('workspace_ref')}"
        )
        if job["status"] in ("completed", "failed", "canceled"):
            break
        time.sleep(POLL_INTERVAL_SECONDS)
    stop_event.set()

    assert job is not None, "never received a job status"
    if job["status"] != "completed":
        raise AssertionError(f"job did not complete: {job}")
    return job


def main() -> int:
    print(f"Waiting for {BASE_URL} to become healthy...")
    wait_for_ready()
    status, ready = request("GET", "/readyz")
    print(f"/readyz -> {status} {ready}")
    if status != 200:
        print("Service is not ready; aborting.")
        return 1

    print("\n--- Step 1: fresh thread, multi-line prompt ---")
    job = submit_and_wait(PROMPT)
    artifacts = job["artifacts"]
    assert len(artifacts) == 1, f"expected exactly 1 text artifact, got {len(artifacts)}"
    artifact = artifacts[0]
    assert artifact["kind"] == "text", f"expected a text artifact, got {artifact}"
    text = artifact["text"] or ""
    assert len(text) > 40, f"answer looks too short to be a real response: {text!r}"
    print(f"Answer ({len(text)} chars):\n{text}\n")

    workspace_ref = job.get("workspace_ref")
    assert workspace_ref, "expected a workspace_ref (thread URL) to be captured"
    print(f"Captured workspace_ref={workspace_ref}")

    status, artifact_meta = request("GET", f"/v1/artifacts/{artifact['id']}")
    assert status == 200, f"get artifact failed: {status} {artifact_meta}"
    status, _ = request("GET", f"/v1/artifacts/{artifact['id']}/file")
    assert status == 200, f"get artifact file failed: {status}"
    print(f"/v1/artifacts/{artifact['id']}/file -> {status} OK")

    print("\n--- Step 2: resume the same thread with a follow-up prompt ---")
    job2 = submit_and_wait(FOLLOW_UP_PROMPT, workspace_ref=workspace_ref)
    artifacts2 = job2["artifacts"]
    assert len(artifacts2) == 1, f"expected exactly 1 text artifact, got {len(artifacts2)}"
    text2 = artifacts2[0]["text"] or ""
    assert len(text2) > 10, f"follow-up answer looks too short: {text2!r}"
    print(f"Follow-up answer ({len(text2)} chars):\n{text2}\n")
    assert job2.get("workspace_ref") == workspace_ref, (
        f"expected the follow-up to stay in the same thread, got {job2.get('workspace_ref')!r}"
    )

    status, batch = request("GET", f"/v1/batches/{job['batch_id']}")
    assert status == 200, f"get batch failed: {status} {batch}"
    print(f"/v1/batches/{job['batch_id']} -> status={batch['status']} counts={batch['counts']}")

    status, accounts = request("GET", "/v1/accounts")
    print(f"/v1/accounts -> {accounts}")
    status, stats = request("GET", "/v1/stats")
    print(f"/v1/stats -> {stats}")

    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
