"""Tests for the paperlm-tools CLI using a fake worker."""

from __future__ import annotations

import json
import shlex
import sys
import textwrap

import pytest

from markitdown_paperlm.cli import tools

FAKE_WORKER = textwrap.dedent(
    r"""
    import json
    import sys
    from pathlib import Path

    engine_used = sys.argv[1]
    status = sys.argv[2] if len(sys.argv) > 2 else "ok"

    for line in sys.stdin:
        req = json.loads(line)
        if req.get("cmd") == "shutdown":
            print(json.dumps({"id": req.get("id"), "status": "shutdown"}), flush=True)
            break
        pdf_path = Path(req["pdf_path"])
        if status == "error":
            markdown = ""
            error = "fake warmup failure"
        else:
            assert pdf_path.read_bytes().startswith(b"%PDF-1.4")
            markdown = "# warmup"
            error = ""
        print(
            json.dumps(
                {
                    "id": req["id"],
                    "pdf_path": str(pdf_path),
                    "status": status,
                    "elapsed_s": 0.01,
                    "markdown": markdown,
                    "engine_used": engine_used,
                    "warnings": [],
                    "paperlm_dict": {"block_count": 1},
                    "paperlm_chunks_jsonl": "{\"text\":\"warmup\"}\n",
                    "error": error,
                }
            ),
            flush=True,
        )
    """
)


def _fake_worker_arg(engine_used: str, status: str = "ok") -> str:
    return (
        f"{shlex.quote(sys.executable)} -u -c {shlex.quote(FAKE_WORKER)} "
        f"{shlex.quote(engine_used)} {shlex.quote(status)}"
    )


def test_warmup_succeeds_with_expected_engine(capsys) -> None:
    exit_code = tools.main(
        [
            "warmup",
            "--engine",
            "docling",
            "--worker-command",
            _fake_worker_arg("docling"),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "docling: ok" in captured.out
    assert captured.err == ""


def test_warmup_json_output(capsys) -> None:
    exit_code = tools.main(
        [
            "warmup",
            "--engine",
            "fallback",
            "--json",
            "--worker-command",
            _fake_worker_arg("pdfminer"),
        ]
    )

    row = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert row["engine"] == "fallback"
    assert row["status"] == "ok"
    assert row["engine_used"] == "pdfminer"


def test_warmup_fails_when_expected_engine_did_not_run(capsys) -> None:
    exit_code = tools.main(
        [
            "warmup",
            "--engine",
            "ocr",
            "--worker-command",
            _fake_worker_arg("pdfminer"),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "expected engine_used='paddleocr'" in captured.err


def test_warmup_fails_on_worker_error(capsys) -> None:
    exit_code = tools.main(
        [
            "warmup",
            "--engine",
            "docling",
            "--worker-command",
            _fake_worker_arg("docling", status="error"),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "fake warmup failure" in captured.err


def test_parse_engines_deduplicates_and_strips() -> None:
    assert tools._parse_engines(" docling, fallback,docling ") == ["docling", "fallback"]


def test_parse_engines_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="unknown warmup engine"):
        tools._parse_engines("marker")


def test_write_minimal_text_pdf(tmp_path) -> None:
    pdf = tmp_path / "warmup.pdf"

    tools.write_minimal_text_pdf(pdf)

    data = pdf.read_bytes()
    assert data.startswith(b"%PDF-1.4")
    assert b"paperlm warmup" in data
    assert b"startxref" in data
