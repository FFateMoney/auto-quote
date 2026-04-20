"""
OCR CLI — library builder and HTTP server launcher.

Usage:
  # Incremental build: process new/changed PDFs in standards/origin/
  python -m backend.ocr.cli sync

  # Full rebuild: wipe data/ocr_markdown/ and reprocess all PDFs
  python -m backend.ocr.cli rebuild

  # Start HTTP server
  python -m backend.ocr.cli serve
  python -m backend.ocr.cli serve --host 0.0.0.0 --port 8001
"""
from __future__ import annotations

import argparse
import sys


def _cmd_sync(args: argparse.Namespace) -> None:
    from backend.common.logging import setup_logging
    from backend.ocr.library import LibraryBuilder
    setup_logging()
    builder = LibraryBuilder()
    report = builder.sync()
    _print_report(report)


def _cmd_rebuild(args: argparse.Namespace) -> None:
    from backend.common.logging import setup_logging
    from backend.ocr.library import LibraryBuilder
    setup_logging()
    builder = LibraryBuilder()
    report = builder.rebuild()
    _print_report(report)


def _cmd_serve(args: argparse.Namespace) -> None:
    try:
        import uvicorn
    except ImportError:
        print("[error] uvicorn is required: pip install uvicorn", file=sys.stderr)
        sys.exit(1)

    from backend.ocr.settings import get_settings
    s = get_settings()
    host = args.host or s.host
    port = args.port or s.port
    print(f"[ocr] starting HTTP server on {host}:{port}")
    uvicorn.run("backend.ocr.http.app:app", host=host, port=port, reload=False)


def _print_report(report: object) -> None:
    print(f"[ocr] mode={report.mode}")  # type: ignore[union-attr]
    print(f"[ocr] found={report.total_found}  processed={report.processed}  skipped={report.skipped}  failed={report.failed}  removed={report.removed}  elapsed={report.elapsed_ms:.0f}ms")  # type: ignore[union-attr]
    for failure in report.failures:  # type: ignore[union-attr]
        print(f"[ocr] FAILED: {failure}", file=sys.stderr)
    if report.failed:  # type: ignore[union-attr]
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m backend.ocr.cli", description="OCR library builder (PP-StructureV3)")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("sync", help="Incremental build: process new/changed PDFs in standards/origin/")
    sub.add_parser("rebuild", help="Full rebuild: wipe output and reprocess all PDFs")

    p_serve = sub.add_parser("serve", help="Start the HTTP server")
    p_serve.add_argument("--host", metavar="HOST", help="Bind host (default: from config or 127.0.0.1)")
    p_serve.add_argument("--port", type=int, metavar="PORT", help="Bind port (default: from config or 8001)")

    args = parser.parse_args()
    {"sync": _cmd_sync, "rebuild": _cmd_rebuild, "serve": _cmd_serve}[args.command](args)


if __name__ == "__main__":
    main()
