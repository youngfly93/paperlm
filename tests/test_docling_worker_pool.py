"""Tests for service-side DoclingWorkerPool using a fake JSONL worker."""

from __future__ import annotations

import sys
import textwrap

from markitdown_paperlm.workers import DoclingWorkerPool, docling_pool

FAKE_WORKER = textwrap.dedent(
    r"""
    import json
    import sys
    import time

    for line in sys.stdin:
        req = json.loads(line)
        if req.get("cmd") == "shutdown":
            print(json.dumps({"id": req.get("id"), "status": "shutdown"}), flush=True)
            break
        pdf_path = req["pdf_path"]
        if pdf_path.endswith("sleep.pdf"):
            time.sleep(5)
        print(
            json.dumps(
                {
                    "id": req["id"],
                    "pdf_path": pdf_path,
                    "status": "ok",
                    "elapsed_s": 0.01,
                    "markdown": "# ok",
                    "engine_used": "fake",
                    "warnings": ["fake warning"],
                    "paperlm_dict": {"block_count": 1},
                    "paperlm_chunks_jsonl": "{\"text\":\"ok\"}\n",
                    "error": "",
                }
            ),
            flush=True,
        )
    """
)


def _fake_command() -> list[str]:
    return [sys.executable, "-u", "-c", FAKE_WORKER]


def test_pool_converts_with_fake_worker(tmp_path) -> None:
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")

    with DoclingWorkerPool(worker_command=_fake_command(), poll_interval_s=0.01) as pool:
        result = pool.convert(pdf)

    assert result.status == "ok"
    assert result.markdown == "# ok"
    assert result.engine_used == "fake"
    assert result.warnings == ["fake warning"]
    assert result.paperlm_dict == {"block_count": 1}
    assert result.paperlm_chunks_jsonl == '{"text":"ok"}\n'
    assert result.worker_index == 0


def test_pool_times_out_and_restarts_worker(tmp_path) -> None:
    slow_pdf = tmp_path / "sleep.pdf"
    slow_pdf.write_bytes(b"%PDF-1.4\n")
    fast_pdf = tmp_path / "fast.pdf"
    fast_pdf.write_bytes(b"%PDF-1.4\n")

    with DoclingWorkerPool(
        worker_command=_fake_command(),
        timeout_s=0.05,
        poll_interval_s=0.01,
    ) as pool:
        timed_out = pool.convert(slow_pdf)
        pool.timeout_s = 2.0
        recovered = pool.convert(fast_pdf)

    assert timed_out.status == "timeout"
    assert "timed out" in timed_out.error
    assert recovered.status == "ok"
    assert recovered.markdown == "# ok"


def test_pool_enforces_memory_limit_and_restarts(monkeypatch, tmp_path) -> None:
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    monkeypatch.setattr(docling_pool, "_rss_mb_tree", lambda _pid: 9999.0)

    with DoclingWorkerPool(
        worker_command=_fake_command(),
        max_rss_mb_hard=1,
        poll_interval_s=0.01,
    ) as pool:
        result = pool.convert(pdf)

    assert result.status == "memory_limit"
    assert result.peak_rss_mb == 9999.0
    assert "RSS hard limit" in result.error


def test_convert_many_preserves_order_and_uses_workers(tmp_path) -> None:
    pdfs = []
    for idx in range(4):
        pdf = tmp_path / f"paper_{idx}.pdf"
        pdf.write_bytes(b"%PDF-1.4\n")
        pdfs.append(pdf)

    with DoclingWorkerPool(
        num_workers=2,
        worker_command=_fake_command(),
        poll_interval_s=0.01,
    ) as pool:
        results = pool.convert_many(pdfs)

    assert [result.pdf_path for result in results] == [str(pdf) for pdf in pdfs]
    assert all(result.status == "ok" for result in results)
    assert {result.worker_index for result in results} == {0, 1}


def test_missing_pdf_returns_error_without_worker_start(tmp_path) -> None:
    missing = tmp_path / "missing.pdf"

    pool = DoclingWorkerPool(worker_command=_fake_command(), poll_interval_s=0.01)
    result = pool.convert(missing)

    assert result.status == "error"
    assert "PDF not found" in result.error
