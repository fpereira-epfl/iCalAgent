from __future__ import annotations

import argparse
import re
from pathlib import Path

from icalagent.config import env_int, env_str, load_env
from icalagent.event_types import normalize_event_type


def _trace(enabled: bool, message: str) -> None:
    if enabled:
        print(f"[trace] {message}")


def _extract_first_url(text: str) -> str | None:
    match = re.search(r"(https?://[^\s<>\"]+)", text, flags=re.IGNORECASE)
    if not match:
        return None
    return match.group(1).rstrip(").,;]")


def _extract_type_hint(raw_text: str, allowed_types: list[str]) -> tuple[str | None, str]:
    lines = raw_text.splitlines()
    allowed = {normalize_event_type(t) for t in allowed_types}

    for idx, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        candidate = stripped
        lowered = stripped.lower()
        if lowered.startswith("type:"):
            candidate = stripped.split(":", 1)[1].strip()
        normalized = normalize_event_type(candidate)
        if normalized in allowed:
            remaining = "\n".join(lines[:idx] + lines[idx + 1 :]).strip()
            return normalized, remaining
        break

    return None, raw_text


def _process_url(
    url: str,
    output_dir: Path,
    model: str,
    event_types_file: Path,
    trace_enabled: bool,
) -> tuple[Path, Path, int, int]:
    from icalagent.exporters import save_parsed_events_by_platform
    from icalagent.event_types import load_event_types
    from icalagent.parser import parse_events_with_gpt
    from icalagent.scrapers.web import scrape_agenda_text

    _trace(trace_enabled, f"Scraping URL: {url}")
    raw_text = scrape_agenda_text(url)
    _trace(trace_enabled, f"Scraped {len(raw_text)} characters of text.")

    event_types = load_event_types(event_types_file)
    _trace(trace_enabled, f"Parsing events with model: {model}")
    events = parse_events_with_gpt(
        raw_text=raw_text,
        source_url=url,
        model=model,
        event_types=event_types,
        trace=lambda m: _trace(trace_enabled, m),
    )
    parsed_root = output_dir / "parsed_events"
    _trace(trace_enabled, f"Saving per-event files under {parsed_root}")
    write_result = save_parsed_events_by_platform(events, parsed_root)
    _trace(trace_enabled, f"Pipeline complete for URL: {url}")

    return (write_result["json_dir"], write_result["ics_dir"], len(events), int(write_result["files_written"]))


def _process_raw_text(
    raw_text: str,
    source_ref: str,
    slug: str,
    output_dir: Path,
    model: str,
    event_types_file: Path,
    trace_enabled: bool,
) -> tuple[Path, Path, int, int]:
    from icalagent.exporters import save_parsed_events_by_platform
    from icalagent.event_types import load_event_types
    from icalagent.parser import parse_events_with_gpt

    event_types = load_event_types(event_types_file)
    hinted_type, cleaned_text = _extract_type_hint(raw_text, event_types)
    if hinted_type:
        _trace(trace_enabled, f"Detected leading type hint '{hinted_type}' and enforcing it for all events.")
    _trace(trace_enabled, "Using provided raw text input.")
    _trace(trace_enabled, f"Parsing events with model: {model}")
    events = parse_events_with_gpt(
        raw_text=cleaned_text,
        source_url=source_ref,
        model=model,
        event_types=event_types,
        forced_event_type=hinted_type,
        trace=lambda m: _trace(trace_enabled, m),
    )
    parsed_root = output_dir / "parsed_events"
    _trace(trace_enabled, f"Saving per-event files under {parsed_root}")
    write_result = save_parsed_events_by_platform(events, parsed_root)
    _trace(trace_enabled, f"Pipeline complete for source: {source_ref}")

    return (write_result["json_dir"], write_result["ics_dir"], len(events), int(write_result["files_written"]))


def cmd_scan(args: argparse.Namespace) -> None:
    from icalagent.agenda_sources import load_agenda_urls

    trace_enabled = not args.quiet
    _trace(trace_enabled, f"Loading agenda URL list from {args.agenda_file}")
    urls = load_agenda_urls(Path(args.agenda_file))
    if args.limit:
        urls = urls[: args.limit]

    if not urls:
        print("No URLs found in agenda list.")
        return

    output_dir = Path(args.output_dir)
    event_types_file = Path(args.event_types_file)
    output_dir.mkdir(parents=True, exist_ok=True)
    _trace(trace_enabled, f"Output directory ready: {output_dir}")
    _trace(trace_enabled, f"Loading allowed event types from: {event_types_file}")

    total_events = 0
    for url in urls:
        json_dir, ics_dir, count, written_files = _process_url(
            url=url,
            output_dir=output_dir,
            model=args.model,
            event_types_file=event_types_file,
            trace_enabled=trace_enabled,
        )
        total_events += count
        print(f"Processed: {url}")
        print(f"  json dir:   {json_dir}")
        print(f"  ics dir:    {ics_dir}")
        print(f"  events: {count}")
        print(f"  files written: {written_files}")

    print(f"Done. Total parsed events: {total_events}")


def cmd_parse_url(args: argparse.Namespace) -> None:
    trace_enabled = not args.quiet
    output_dir = Path(args.output_dir)
    event_types_file = Path(args.event_types_file)
    output_dir.mkdir(parents=True, exist_ok=True)
    _trace(trace_enabled, f"Output directory ready: {output_dir}")
    _trace(trace_enabled, f"Loading allowed event types from: {event_types_file}")

    json_dir, ics_dir, count, written_files = _process_url(
        url=args.url,
        output_dir=output_dir,
        model=args.model,
        event_types_file=event_types_file,
        trace_enabled=trace_enabled,
    )

    print(f"Processed: {args.url}")
    print(f"json dir:   {json_dir}")
    print(f"ics dir:    {ics_dir}")
    print(f"events: {count}")
    print(f"files written: {written_files}")


def cmd_parse_text(args: argparse.Namespace) -> None:
    trace_enabled = not args.quiet
    input_path = Path(args.input_text)
    if not input_path.exists():
        raise FileNotFoundError(f"Input text file not found: {input_path}")

    _trace(trace_enabled, f"Reading input text file: {input_path}")
    raw_text = input_path.read_text(encoding="utf-8")
    if not raw_text.strip():
        raise ValueError(f"Input text file is empty: {input_path}")

    output_dir = Path(args.output_dir)
    event_types_file = Path(args.event_types_file)
    output_dir.mkdir(parents=True, exist_ok=True)
    _trace(trace_enabled, f"Output directory ready: {output_dir}")
    _trace(trace_enabled, f"Loading allowed event types from: {event_types_file}")

    detected_url = _extract_first_url(raw_text)
    source_ref = args.source_ref or detected_url or f"local-text:{input_path}"
    if detected_url and not args.source_ref:
        _trace(trace_enabled, f"Detected URL in text and using it as source reference: {detected_url}")
    slug = args.slug or input_path.stem

    json_dir, ics_dir, count, written_files = _process_raw_text(
        raw_text=raw_text,
        source_ref=source_ref,
        slug=slug,
        output_dir=output_dir,
        model=args.model,
        event_types_file=event_types_file,
        trace_enabled=trace_enabled,
    )

    print(f"Processed text file: {input_path}")
    print(f"source: {source_ref}")
    print(f"json dir:   {json_dir}")
    print(f"ics dir:    {ics_dir}")
    print(f"events: {count}")
    print(f"files written: {written_files}")


def cmd_export(args: argparse.Namespace) -> None:
    from icalagent.exporters import export_events_to_ics
    from icalagent.importers import load_events_json

    trace_enabled = not args.quiet
    input_path = Path(args.input_json)
    output_path = Path(args.output_ics)

    _trace(trace_enabled, f"Loading events JSON: {input_path}")
    events = load_events_json(input_path)
    _trace(trace_enabled, f"Exporting {len(events)} event(s) to ICS: {output_path}")
    export_events_to_ics(events, output_path, calendar_name=args.calendar_name)
    print(f"Exported {len(events)} events to {output_path}")


def _parse_indices(indices_raw: str | None) -> list[int] | None:
    if not indices_raw:
        return None
    values = []
    for chunk in indices_raw.split(","):
        text = chunk.strip()
        if not text:
            continue
        values.append(int(text))
    return values or None


def cmd_import_selected(args: argparse.Namespace) -> None:
    from icalagent.importers import export_selected_for_targets, load_events_json, select_events

    trace_enabled = not args.quiet
    _trace(trace_enabled, f"Loading events JSON: {args.input_json}")
    events = load_events_json(Path(args.input_json))
    indices = _parse_indices(args.indices)
    selected = select_events(events, indices=indices, contains=args.contains)
    _trace(trace_enabled, f"Selected {len(selected)} event(s) from {len(events)} total.")

    if not selected:
        print("No events matched your selection criteria.")
        return

    output_dir = Path(args.output_dir)
    written = export_selected_for_targets(
        events=selected,
        output_dir=output_dir,
        basename=args.basename,
        target=args.target,
    )
    _trace(trace_enabled, f"Wrote {len(written)} file(s) to {output_dir}")

    print(f"Selected {len(selected)} / {len(events)} events")
    for path in written:
        print(f"Wrote: {path}")


def build_parser() -> argparse.ArgumentParser:
    load_env()

    default_agenda_file = env_str("ICALAGENT_AGENDA_FILE", "data/list_of_agendas.json")
    default_output_dir = env_str("ICALAGENT_OUTPUT_DIR", "data")
    default_model = env_str("ICALAGENT_MODEL", env_str("OPENAI_MODEL", "gpt-4o-mini"))
    default_event_types_file = env_str("ICALAGENT_EVENT_TYPES_FILE", "data/event_types.txt")
    default_calendar_name = env_str("ICALAGENT_CALENDAR_NAME", "iCalAgent")
    default_import_target = env_str("ICALAGENT_IMPORT_TARGET", "ics")
    if default_import_target not in {"ics"}:
        default_import_target = "ics"
    default_import_basename = env_str("ICALAGENT_IMPORT_BASENAME", "selected_events")
    default_scan_limit = env_int("ICALAGENT_SCAN_LIMIT", 0)

    parser = argparse.ArgumentParser(description="iCalAgent: scrape agendas and build calendar imports")
    subparsers = parser.add_subparsers(required=True)

    scan = subparsers.add_parser("scan", help="Parse all agenda URLs from JSON file")
    scan.add_argument("--agenda-file", default=default_agenda_file)
    scan.add_argument("--output-dir", default=default_output_dir)
    scan.add_argument("--model", default=default_model)
    scan.add_argument("--event-types-file", default=default_event_types_file)
    scan.add_argument("--limit", type=int, default=(default_scan_limit or None))
    scan.add_argument("--quiet", action="store_true", help="Disable trace messages")
    scan.set_defaults(func=cmd_scan)

    parse_url = subparsers.add_parser("parse-url", help="Parse a single agenda URL")
    parse_url.add_argument("url")
    parse_url.add_argument("--output-dir", default=default_output_dir)
    parse_url.add_argument("--model", default=default_model)
    parse_url.add_argument("--event-types-file", default=default_event_types_file)
    parse_url.add_argument("--quiet", action="store_true", help="Disable trace messages")
    parse_url.set_defaults(func=cmd_parse_url)

    parse_text = subparsers.add_parser("parse-text", help="Parse events from a local raw text file")
    parse_text.add_argument("input_text", help="Path to a local text file containing agenda text")
    parse_text.add_argument("--source-ref", default=None, help="Optional source label saved in parsed events")
    parse_text.add_argument("--slug", default=None, help="Optional filename prefix for outputs")
    parse_text.add_argument("--output-dir", default=default_output_dir)
    parse_text.add_argument("--model", default=default_model)
    parse_text.add_argument("--event-types-file", default=default_event_types_file)
    parse_text.add_argument("--quiet", action="store_true", help="Disable trace messages")
    parse_text.set_defaults(func=cmd_parse_text)

    export = subparsers.add_parser("export", help="Export events JSON file to ICS")
    export.add_argument("input_json")
    export.add_argument("output_ics")
    export.add_argument("--calendar-name", default=default_calendar_name)
    export.add_argument("--quiet", action="store_true", help="Disable trace messages")
    export.set_defaults(func=cmd_export)

    import_sel = subparsers.add_parser(
        "import-selected",
        help="Select subset of events and export ICS files",
    )
    import_sel.add_argument("input_json")
    import_sel.add_argument("--indices", default=None, help="1-based CSV indexes, e.g. 1,3,4")
    import_sel.add_argument("--contains", default=None, help="Text filter in title/description/location")
    import_sel.add_argument("--target", choices=["ics"], default=default_import_target)
    import_sel.add_argument("--output-dir", default=default_output_dir)
    import_sel.add_argument("--basename", default=default_import_basename)
    import_sel.add_argument("--quiet", action="store_true", help="Disable trace messages")
    import_sel.set_defaults(func=cmd_import_selected)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
