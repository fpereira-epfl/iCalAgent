# iCalAgent

Python CLI tool to scrape event agenda pages, parse events with GPT, and export calendar files.

## What this first version supports

- Read agenda URLs from `data/list_of_agendas.json`.
- Or parse one URL from CLI input.
- Or parse a local raw text file (copy-pasted page text).
- Scrape detailed raw page text.
- Send text to GPT and request structured JSON event extraction.
- Normalize parsed event text fields to English.
- Enforce event title prefix format as `[TYPE] Title` using an allowed type list from `data/event_types.txt`.
- Save parsed outputs in `data/parsed_events/`:
  - `data/parsed_events/json/<event_id>.json`
  - `data/parsed_events/ics/<event_id>.ics`
- Select event subsets and generate `.ics` files.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

Set your OpenAI API key:

```bash
export OPENAI_API_KEY="your_api_key_here"
```

Optional `.env` parameters used by the CLI:

```env
ICALAGENT_MODEL=gpt-4o-mini
ICALAGENT_EVENT_TYPES_FILE=data/event_types.txt
ICALAGENT_OUTPUT_DIR=data
ICALAGENT_AGENDA_FILE=data/list_of_agendas.json
ICALAGENT_SCAN_LIMIT=0
ICALAGENT_CALENDAR_NAME=iCalAgent
ICALAGENT_IMPORT_TARGET=ics
ICALAGENT_IMPORT_BASENAME=selected_events
ICALAGENT_GPT_MAX_TOTAL_CHARS=180000
ICALAGENT_GPT_MAX_CHARS_PER_CHUNK=60000
ICALAGENT_GPT_MAX_CHUNKS=3
ICALAGENT_OPENAI_TIMEOUT_SECONDS=120
ICALAGENT_OPENAI_MAX_RETRIES=2
```

## Agenda URL list format

`data/list_of_agendas.json` can be either:

```json
["https://site-a.com/agenda", "https://site-b.com/events"]
```

or

```json
{ "urls": ["https://site-a.com/agenda", "https://site-b.com/events"] }
```

## CLI usage

By default, commands print `[trace]` messages showing each processing step.
Use `--quiet` to disable traces.

Parse every URL from agenda file (writes per-event files in `data/parsed_events/{json,ics}`):

```bash
icalagent scan --agenda-file data/list_of_agendas.json --output-dir data
```

Parse a single URL:

```bash
icalagent parse-url "https://example.com/events" --output-dir data --event-types-file data/event_types.txt
```

Parse a local text file directly:

```bash
icalagent parse-text data/copied_page.txt --output-dir data --source-ref "https://example.com/events" --event-types-file data/event_types.txt
```

If the text contains a pasted URL and `--source-ref` is omitted, the first detected URL is used automatically.

For `parse-text`, you can force classification by putting a type hint on the first non-empty line, for example:

```text
jazz
...rest of pasted page text...
```

or:

```text
type: jazz
...rest of pasted page text...
```

When present, that type is strictly enforced for all parsed events in that file.

Export existing events JSON to ICS:

```bash
icalagent export data/my_events.json data/my_events.ics
```

Export selected events for import:

```bash
icalagent import-selected data/my_events.json --indices 1,3,4 --target ics --output-dir data --basename my_selected
```

Text-based filter selection:

```bash
icalagent import-selected data/my_events.json --contains "workshop" --target ics
```

## Notes

- The same `.ics` files can be imported into Google Calendar and Apple Calendar.
- Parsed event quality depends on source page clarity and GPT extraction accuracy.
- Event IDs are deterministic composites (source + title + datetime + location), so rescans of the same source keep the same IDs and filenames.
- Timed events are normalized to a minimum duration of 1 hour.
