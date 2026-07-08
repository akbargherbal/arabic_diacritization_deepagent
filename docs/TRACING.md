# Tracing / observability

`tools/tracing.py` + `tools/trace_report.py` give you, per `agent.invoke(...)`
attempt:

- a fresh, unique **`trace_id`** every time (format: `2026-07-08T14-32-01Z_a3f9c2d1`)
- input/output/cached token totals **per agent** — `orchestrator`,
  `diacritizer`, `irab_checker`, `naturalness_critic` — attributed
  automatically from the real dispatch mechanism (see below), no manual
  tagging needed anywhere in `subagents/*.py`
- latency per LLM call and per tool call
- everything in a local `traces.sqlite` (same pattern as your existing
  `checkpoints.sqlite`), queryable via a CLI

This already lives in `main.py` — nothing further to wire in.

## Why this exists

Your 12-verse taweel run produced a 70k+ token transcript where the
`diacritizer` subagent looped for 3+ passes doing manual prosody analysis
before the orchestrator gave up and logged 4 verses unresolved. Right now
there's no way to see *that this happened* except reading the whole
transcript. With this on:

```
agent         kind  calls  in_tok  out_tok  cached  total_tok  avg_ms  sum_ms  errors
------------  ----  -----  ------  -------  ------  ---------  ------  ------  ------
diacritizer   llm   6      210000  9800     58000   161800     10400   62400   0
orchestrator  llm   9      95000   3200     84000   14200      1800    16200   0
irab_checker  llm   1      500     50       0       550        900     900     0
```

...tells you in one glance where the token/latency budget went, and `--calls`
shows you exactly which pass it happened in.

## How attribution actually works (no manual tagging required)

Your subagents aren't invoked as separate LangGraph nodes with stable names
— they're dispatched through deepagents' **`task` tool**, whose call
arguments include `subagent_type` (you can see this directly in your own
transcript: `{'name': 'task', 'args': {..., 'subagent_type': 'diacritizer'}}`).

So the callback in `tools/tracing.py`:

1. Watches every tool call. When a `task` call starts, it reads
   `subagent_type` out of the args.
2. Watches every LLM call. To attribute it, it walks up the chain of
   `parent_run_id`s (LangChain always provides these) until it finds an
   ancestor `task` call — that's the subagent. If there isn't one, the call
   belongs to the orchestrator itself.

This means `subagents/diacritizer.py`, `subagents/irab_checker_agent.py`,
and `subagents/naturalness_critic.py` needed **zero changes**. If deepagents
changes its internal dispatch mechanism in a future version (the project's
own README flags this API as moving fast), the one place to update is
`DISPATCH_TOOL_NAME` / `SUBAGENT_ARG_KEYS` at the top of `tools/tracing.py`.

## `trace_id` vs. LangGraph's `thread_id` — these are deliberately different

`main.py` already has a `thread_id`:

```python
thread_id = f"{INPUT_PATH.stem}:{meter}"
```

This is **intentionally stable** per `(input file, meter)` so a Ctrl+C'd run
resumes the same checkpoint instead of starting over. That's the opposite of
what you want for observability, where you want to tell attempt #1 apart
from the retry after a crash.

So `trace_run()` generates a separate `trace_id`, fresh every single
`agent.invoke(...)` call — including resumes on the same `thread_id`. The
`thread_id` is recorded alongside it for cross-reference
(`--for-thread <thread_id>` lists every attempt under it).

## Usage

```bash
# list recent traced attempts
python -m tools.trace_report --list

# per-agent summary for the most recent attempt
python -m tools.trace_report

# a specific attempt
python -m tools.trace_report --trace 2026-07-08T14-32-01Z_a3f9c2d1

# raw chronological timeline for one attempt — shows exactly which pass
# looped without converging
python -m tools.trace_report --trace 2026-07-08T14-32-01Z_a3f9c2d1 --calls

# every attempt recorded under a given LangGraph thread_id (e.g. to see
# how many times a batch was interrupted/resumed, and what each attempt cost)
python -m tools.trace_report --for-thread batch_01:taweel
```

Running `python main.py` now also prints the `trace_id` for each batch as it
starts, and the exact `trace_report` command to inspect it, right after the
batch finishes (success or failure).

## Alternative: LangSmith (already in your dependencies via `langsmith`)

If you'd rather not maintain a local SQLite store, three env vars before
`python main.py` get you a fully hosted trace tree with token counts and
latency per node, no code changes:

```bash
export LANGCHAIN_TRACING_V2=true
export LANGCHAIN_API_KEY=<your key>
export LANGCHAIN_PROJECT=arabic-diacritization-deepagent
```

Good complement, not a replacement — the SQLite approach here works fully
offline, keeps data local, and is easy to assert against in `tests/`
(e.g. "this pass must not exceed N tokens for the diacritizer").

## Notes / caveats

- Tracing failures never break your actual run — token extraction in
  `on_llm_end` is wrapped in a bare `try/except` for exactly this reason.
- `traces.sqlite` grows unbounded; add a periodic
  `DELETE FROM runs WHERE started_at < ...` cleanup if you run this a lot.
  Consider adding it (and `traces.sqlite*`) to `.gitignore` alongside your
  existing `.db` entry.
- Token field names (`input_token_details.cache_read` /
  `prompt_tokens_details.cached_tokens`) match what your own transcript
  shows from the DeepSeek/OpenAI-compatible response shape. If you switch
  model providers, double check that field name still matches.
- `SUBAGENT_ARG_KEYS = ("subagent_type", "subagent", "agent_type")` in
  `tools/tracing.py` is intentionally defensive against small API drift in
  deepagents' `task` tool signature — extend it if a future version renames
  the argument.
