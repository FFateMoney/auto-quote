from __future__ import annotations

import argparse
import json
from pathlib import Path

from backendV2.core.catalog.repository import TestProjectRepository
from backendV2.core.catalog.special_fields import SpecialFieldDefinitionRepository
from backendV2.core.history.repository import HistoricalQuotationRepository
from backendV2.core.runs.service import RunService
from backendV2.core.settings import Settings
from backendV2.core.submissions.validator import QuoteTableValidator
from backendV2.core.tools.query_test_project_capability_fields import QueryTestProjectCapabilityFieldsTool
from backendV2.core.tools.query_test_project_aliases import QueryTestProjectAliasesTool
from backendV2.core.tools.query_test_projects import QueryTestProjectsTool
from backendV2.core.tools.query_history_quotation_cache import QueryHistoricalQuotationCacheTool
from backendV2.core.tools.submit_quote_batch import SubmitQuoteBatchTool
from backendV2.core.tools.validate_quote_table import ValidateQuoteTableTool


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="quote-core")
    commands = parser.add_subparsers(dest="command", required=True)

    query = commands.add_parser("query-test-projects")
    query.add_argument("--run-dir", required=True)

    capabilities = commands.add_parser("query-test-project-capability-fields")
    capabilities.add_argument("--run-dir", required=True)
    capabilities.add_argument("--test-project-id", required=True, type=int)

    aliases = commands.add_parser("query-test-project-aliases")
    aliases.add_argument("--run-dir", required=True)
    aliases.add_argument("--test-project-id", required=True, type=int)

    history_cache = commands.add_parser("query-history-quotation-cache")
    history_cache.add_argument("--run-dir", required=True)
    history_cache.add_argument("--standard-type", required=True)
    history_cache.add_argument("--test-item", required=True)
    history_cache.add_argument("--standard-code", required=True)

    validate = commands.add_parser("validate-quote-table")
    validate.add_argument("--run-dir", required=True)
    validate.add_argument("--file", required=True)

    submit = commands.add_parser("submit-batch")
    submit.add_argument("--run-dir", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = Settings.from_environment()
    validator = QuoteTableValidator()
    runs = RunService(settings)

    try:
        if args.command == "query-test-projects":
            destination = QueryTestProjectsTool(settings, TestProjectRepository(settings)).execute(args.run_dir)
            print(json.dumps({"accepted": True, "file": str(destination)}, ensure_ascii=False))
            return 0

        if args.command == "query-test-project-capability-fields":
            destination = QueryTestProjectCapabilityFieldsTool(
                settings,
                TestProjectRepository(settings),
                SpecialFieldDefinitionRepository(settings),
            ).execute(args.run_dir, args.test_project_id)
            print(json.dumps({"accepted": True, "file": str(destination)}, ensure_ascii=False))
            return 0

        if args.command == "query-test-project-aliases":
            destination = QueryTestProjectAliasesTool(
                settings,
                TestProjectRepository(settings),
            ).execute(args.run_dir, args.test_project_id)
            print(json.dumps({"accepted": True, "file": str(destination)}, ensure_ascii=False))
            return 0

        if args.command == "query-history-quotation-cache":
            destination = QueryHistoricalQuotationCacheTool(
                settings,
                HistoricalQuotationRepository(settings),
            ).execute(args.run_dir, args.standard_type, args.test_item, args.standard_code)
            print(json.dumps({"accepted": True, "file": str(destination)}, ensure_ascii=False))
            return 0

        if args.command == "validate-quote-table":
            result, destination = ValidateQuoteTableTool(settings, validator).execute(Path(args.run_dir), args.file)
        else:
            result, destination = SubmitQuoteBatchTool(settings, validator, runs).execute(args.run_dir)
        print(json.dumps({**result.to_dict(), "file": str(destination)}, ensure_ascii=False))
        return 0 if result.accepted else 2
    except (OSError, ValueError, KeyError) as exc:
        print(json.dumps({"accepted": False, "phase": "format", "message": "格式错误", "details": [{"path": "$", "rule": "tool", "detail": str(exc)}]}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
