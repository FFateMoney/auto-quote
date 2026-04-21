from __future__ import annotations

import argparse
import sys


def _cmd_sync(args: argparse.Namespace) -> None:
    from backend.common.logging import setup_logging
    from backend.cleaning.library import CleaningLibrary
    setup_logging()
    library = CleaningLibrary()
    report = library.sync()
    _print_report(report)


def _cmd_rebuild(args: argparse.Namespace) -> None:
    from backend.common.logging import setup_logging
    from backend.cleaning.library import CleaningLibrary
    setup_logging()
    library = CleaningLibrary()
    report = library.rebuild()
    _print_report(report)


def _cmd_serve(args: argparse.Namespace) -> None:
    try:
        import uvicorn
    except ImportError:
        print("[error] uvicorn is required: pip install uvicorn", file=sys.stderr)
        sys.exit(1)

    from backend.cleaning.settings import get_settings
    s = get_settings()
    host = args.host or s.host
    port = args.port or s.port
    print(f"[cleaning] starting HTTP server on {host}:{port}")
    uvicorn.run("backend.cleaning.http.app:app", host=host, port=port, reload=False)


def _print_report(report: object) -> None:
    print(f"[cleaning] mode={report.mode}")
    print(f"[cleaning] total_found={report.total_found} processed={report.processed} skipped={report.skipped} failed={report.failed} elapsed={report.elapsed_ms:.0f}ms")
    for failure in report.failures:
        print(f"[cleaning] FAILED: {failure}", file=sys.stderr)
    if report.failed:
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m backend.cleaning.cli", description="Markdown cleaning tool")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("sync", help="Incremental cleaning: process new or changed OCR outputs")
    sub.add_parser("rebuild", help="Full rebuild: clean all OCR outputs from scratch")

    p_serve = sub.add_parser("serve", help="Start the HTTP server")
    p_serve.add_argument("--host", metavar="HOST", help="Bind host")
    p_serve.add_argument("--port", type=int, metavar="PORT", help="Bind port")

    args = parser.parse_args()
    {"sync": _cmd_sync, "rebuild": _cmd_rebuild, "serve": _cmd_serve}[args.command](args)


if __name__ == "__main__":
    main()
