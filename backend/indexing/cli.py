from __future__ import annotations

import argparse
import sys


def _cmd_sync(args: argparse.Namespace) -> None:
    from backend.common.logging import setup_logging
    from backend.indexing.library import IndexingLibrary
    setup_logging()
    library = IndexingLibrary()
    report = library.sync()
    _print_report(report)


def _cmd_rebuild(args: argparse.Namespace) -> None:
    from backend.common.logging import setup_logging
    from backend.indexing.library import IndexingLibrary
    setup_logging()
    library = IndexingLibrary()
    report = library.rebuild()
    _print_report(report)


def _cmd_serve(args: argparse.Namespace) -> None:
    try:
        import uvicorn
    except ImportError:
        print("[error] uvicorn is required", file=sys.stderr)
        sys.exit(1)

    from backend.indexing.settings import get_settings
    s = get_settings()
    host = args.host or s.host
    port = args.port or s.port
    print(f"[indexing] starting mixed-search service on {host}:{port}")
    uvicorn.run("backend.indexing.http.app:app", host=host, port=port, reload=False)


def _print_report(report: object) -> None:
    print(f"[indexing] mode={getattr(report, 'mode')}")
    print(f"[indexing] files={getattr(report, 'processed_files')}/{getattr(report, 'total_files')} chunks={getattr(report, 'total_chunks')} failed={getattr(report, 'failed_files')} elapsed={getattr(report, 'elapsed_ms'):.0f}ms")
    for failure in getattr(report, "failures"):
        print(f"[indexing] FAILED: {failure}", file=sys.stderr)
    if getattr(report, "failed_files"):
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m backend.indexing.cli", description="Standard Knowledge Indexer")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("sync", help="Incremental sync: update Qdrant from cleaned MDs")
    sub.add_parser("rebuild", help="Full rebuild: clear Qdrant and re-index everything")

    p_serve = sub.add_parser("serve", help="Start the search service")
    p_serve.add_argument("--host", help="Bind host")
    p_serve.add_argument("--port", type=int, help="Bind port")

    args = parser.parse_args()
    {"sync": _cmd_sync, "rebuild": _cmd_rebuild, "serve": _cmd_serve}[args.command](args)


if __name__ == "__main__":
    main()
