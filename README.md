# Arabic Prosody Diacritization — Dataset Builder (DeepAgents PoC)

Generates diacritized Arabic verses matching a target meter, verified against
`pyarud` via `arabic_prosody_feedback.py`, to build a training dataset.

## Before you run anything

1. **`verification/arabic_prosody_feedback.py` is a STUB, not your real module.**
   Your upload was a skeleton extract (docstrings + signatures, function bodies
   omitted, one top-level side-effecting statement omitted). I could not
   reconstruct the real implementation, so this file currently raises
   `NotImplementedError` everywhere. **Replace it with your actual working
   `arabic_prosody_feedback.py`** (the one that imports `pyarud`/`arudi.py`
   and actually runs). Keep the file name and public function signatures —
   `tools/prosody_tools.py` imports directly against the contract described
   in your skeleton (`analyze_poem`, `analyze_verse`,
   `generate_poem_correction_report`, `PoemResult`, `VerseResult`).

2. **`config/meter_tables.py`** is ported directly from your `METER_TEMPLATES`
   / `CANONICAL_PATTERNS` / `METER_ARABIC_NAMES` dicts, unmodified. It's marked
   read-only to the agent (see `main.py` permissions) — treat any change to it
   as a deliberate config change, not something the agent should ever propose.

3. **إعراب checking is pure LLM judgment, not rule-based.** There is no
   deterministic rule file — `subagents/irab_checker_agent.py` is a
   prompt-only advisory subagent, the same shape as `naturalness_critic.py`.
   Be aware this means إعراب and naturalness now share a representation
   (both are "an LLM reads the text and judges it") rather than being
   independent verification axes. The only genuinely independent, deciding
   axes in this system are Structural (pyarud) and Security (sanitizer).
   Treat إعراب/naturalness agreement as weak corroboration, not confirmation.

4. Install deps and set your DeepSeek (or other OpenAI-compatible) credentials:

   ```bash
   pip install -r requirements.txt
   pip install pyarud
   export DEEPSEEK_API_KEY=...        # or swap the model config in main.py
   ```

5. `deepagents`' exact API (`create_deep_agent` signature, `permissions=`
   schema, `interrupt_on` condition syntax) moves fast. Everything here
   reflects the framework as understood at design time — **confirm against
   `docs.langchain.com/oss/python/deepagents` before running in anger**,
   particularly the permissions rule schema in `main.py`.

## What's real vs. placeholder in this scaffold

| File | Status |
|---|---|
| Directory structure, permission rules, orchestrator control flow | Real, intended to run as-is |
| `tools/dataset_tools.py` (`commit_verse`) | Real logic, placeholder score threshold — tune it |
| `tools/sanitization_tools.py` | Real, minimal — extend the allowed-codepoint set if needed |
| `verification/arabic_prosody_feedback.py` | **Stub — replace with your real file** |
| `subagents/irab_checker_agent.py` | Real prompt, but pure LLM judgment — no deterministic rules behind it (by design) |
| `subagents/*.py` system prompts | Skeleton prompts with the precedence/locking rules encoded — refine with real meter-specific guidance |
| `main.py` | Real wiring, one placeholder model string (`deepseek-chat` — confirm the exact model id you want) |

## Running

```bash
python main.py
```

`main.py` as shipped just constructs the agent object — wire in your actual
batch-invocation loop (reading verses.jsonl input, calling `agent.invoke(...)`)
once you've replaced the two stub files above. Left out deliberately: this is
where your specific input format and batch cadence belong, not something to
guess into a scaffold.
