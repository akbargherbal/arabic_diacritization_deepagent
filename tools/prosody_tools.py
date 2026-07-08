"""
tools/prosody_tools.py
========================
Agent-facing tools wrapping verification/arabic_prosody_feedback.py.

These are the ONLY sanctioned way an agent touches the pyarud gate. Note
that these are read-driven — none of them write into verification/, and the
orchestrator (not any subagent) is the one that calls verify_batch_tool,
per the design's separation between "the entity that decides pass/fail"
and "the entity trying to pass" (see main.py's system prompt).
"""

from __future__ import annotations
import json

from verification import arabic_prosody_feedback as prosody
from config import meter_tables


def meter_schema_tool(meter_id: str) -> dict:
    """Return the canonical template and Arabic name for a meter id.

    Read-only lookup against config/meter_tables.py — never generated or
    guessed by the model.
    """
    resolved = meter_tables._METER_TABLE_TO_PYARUD.get(meter_id, meter_id)
    return {
        "meter_id": resolved,
        "template": meter_tables.METER_TEMPLATES.get(resolved),
        "arabic_name": meter_tables.METER_ARABIC_NAMES.get(resolved),
    }


def verify_batch_tool(verses: list[dict], meter_name: str) -> dict:
    """Run the deterministic pyarud check over a batch of verses.

    Args:
        verses: list of {"verse_id": str, "sadr": str, "ajuz": str}
        meter_name: target meter (any supported alias)

    Returns:
        {
          "locked": [verse_id, ...],       # passed, do not resubmit
          "broken": [verse_id, ...],       # failed, needs another pass
          "correction_report": str,        # LLM-actionable text for broken verses only
          "poem_result_json": str,         # full structured result, for logging
        }

    This is called by the ORCHESTRATOR directly, never delegated to the
    diacritizer subagent — the entity deciding pass/fail must not be the
    entity trying to pass.
    """
    pairs = [(v["sadr"], v.get("ajuz", "")) for v in verses]
    poem_result = prosody.analyze_poem(pairs, meter_name=meter_name)

    locked, broken = [], []
    for v, verse_result in zip(verses, poem_result.verses):
        target = locked if verse_result.combined_score >= 0.99 else broken
        target.append(v["verse_id"])

    report = prosody.generate_poem_correction_report(poem_result, only_broken=True)

    return {
        "locked": locked,
        "broken": broken,
        "correction_report": report,
        "poem_result_json": json.dumps(
            {"overall_score": poem_result.overall_score,
             "is_metrically_sound": poem_result.is_metrically_sound,
             "candidate_meters": poem_result.candidate_meters},
            ensure_ascii=False,
        ),
    }


def verify_single_verse_tool(sadr: str, ajuz: str, meter_name: str) -> dict:
    """Used by commit_verse_tool for the final re-check before a dataset write.
    Not intended for the diacritizer subagent to call directly during drafting —
    it drafts against the batch-level correction_report instead.
    """
    result = prosody.analyze_verse(sadr, ajuz, meter_name=meter_name)
    return {
        "combined_score": result.combined_score,
        "is_sound": result.combined_score >= 0.99,
        "issues": result.issues,
    }
