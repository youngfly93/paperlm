"""Tests for the paperlm-batch CLI using a fake worker."""

from __future__ import annotations

import json
import shlex
import sys
import textwrap
from pathlib import Path

from markitdown_paperlm.cli import batch

FAKE_WORKER = textwrap.dedent(
    r"""
    import json
    import sys

    for line in sys.stdin:
        req = json.loads(line)
        if req.get("cmd") == "shutdown":
            print(json.dumps({"id": req.get("id"), "status": "shutdown"}), flush=True)
            break
        pdf_path = req["pdf_path"]
        markdown = "# " + pdf_path.split("/")[-1]
        print(
            json.dumps(
                {
                    "id": req["id"],
                    "pdf_path": pdf_path,
                    "status": "ok",
                    "elapsed_s": 0.01,
                    "markdown": markdown,
                    "engine_used": "fake",
                    "warnings": [],
                    "paperlm_dict": {"block_count": 1, "blocks": [{"content": markdown}]},
                    "paperlm_chunks_jsonl": "{\"text\":\"ok\"}\n",
                    "error": "",
                }
            ),
            flush=True,
        )
    """
)


def _fake_worker_arg() -> str:
    return f"{shlex.quote(sys.executable)} -u -c {shlex.quote(FAKE_WORKER)}"


def test_batch_cli_writes_jsonl_and_artifacts(tmp_path, capsys) -> None:
    pdf = tmp_path / "paper one.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    out_dir = tmp_path / "out"

    exit_code = batch.main(
        [
            str(pdf),
            "--worker-command",
            _fake_worker_arg(),
            "--output-dir",
            str(out_dir),
            "--include-markdown",
        ]
    )

    assert exit_code == 0
    rows = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert len(rows) == 1
    row = rows[0]
    assert row["status"] == "ok"
    assert row["engine_used"] == "fake"
    assert row["block_count"] == 1
    assert row["markdown"] == "# paper one.pdf"
    assert Path(row["markdown_path"]).read_text(encoding="utf-8") == "# paper one.pdf"
    assert Path(row["paperlm_json_path"]).exists()
    assert Path(row["chunks_jsonl_path"]).read_text(encoding="utf-8") == '{"text":"ok"}\n'


def test_batch_cli_reads_jsonl_and_writes_output_file(tmp_path, capsys) -> None:
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    input_jsonl = tmp_path / "input.jsonl"
    output_jsonl = tmp_path / "result.jsonl"
    input_jsonl.write_text(json.dumps({"id": "doc-1", "pdf_path": str(pdf)}) + "\n", encoding="utf-8")

    exit_code = batch.main(
        [
            "--input-jsonl",
            str(input_jsonl),
            "--output-jsonl",
            str(output_jsonl),
            "--worker-command",
            _fake_worker_arg(),
        ]
    )

    assert exit_code == 0
    assert capsys.readouterr().out == ""
    rows = [json.loads(line) for line in output_jsonl.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["id"] == "doc-1"
    assert rows[0]["status"] == "ok"
    assert "markdown" not in rows[0]


def test_batch_cli_returns_nonzero_on_failure_by_default(tmp_path, capsys) -> None:
    missing = tmp_path / "missing.pdf"

    exit_code = batch.main(
        [
            str(missing),
            "--worker-command",
            _fake_worker_arg(),
        ]
    )

    row = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert row["status"] == "error"
    assert "PDF not found" in row["error"]


def test_batch_cli_allow_failures_returns_zero(tmp_path, capsys) -> None:
    missing = tmp_path / "missing.pdf"

    exit_code = batch.main(
        [
            str(missing),
            "--worker-command",
            _fake_worker_arg(),
            "--allow-failures",
        ]
    )

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out)["status"] == "error"
