"""
tools/dataset_tools.py
========================
commit_verse_tool is the ONLY path into dataset/. Permission rules deny the
agent's built-in write_file/edit_file against dataset/**, but that layer
does NOT cover custom tools — a custom tool is just a Python function the
agent can call, invisible to the declarative permissions system. So the
real enforcement lives here, in code:

  1. re-run the pyarud check (never trust a stale "it passed earlier")
  2. run the sanitizer (security axis, deciding)
  3. append-only write, never overwrite/delete

This is design principle 3 made concrete: the gate's enforcement point is
code the agent cannot edit (verification/ is permission-denied), not
agent discretion, and not the permission system either.
"""

import json
import pathlib

from tools.prosody_tools import verify_single_verse_tool
from tools.sanitization_tools import sanitize_output_tool

DATASET_PATH = pathlib.Path(__file__).resolve().parent.parent / "dataset" / "verses.jsonl"
SCORE_THRESHOLD = 0.99  # placeholder — tune deliberately against real data


def commit_verse_tool(
    verse_id: str,
    sadr: str,
    ajuz: str,
    meter: str,
    irab_flag: bool = False,
    naturalness_flag: bool = False,
    reconciled: bool = False,
    original_sadr: str | None = None,
    original_ajuz: str | None = None,
    notes: str = "",
) -> dict:
    """Commit one verified verse to the dataset. Re-checks pyarud and runs
    the sanitizer itself before writing — do not treat an earlier
    verify_batch_tool pass as sufficient, this call re-verifies.

    If reconciled=True, sadr/ajuz are the POST-reconciliation text (after a
    deterministic case-ending swap resolved an إعراب flag without touching
    the meter — see tools/reconciliation_tools.py) and original_sadr/
    original_ajuz preserve what pyarud originally verified, for audit.
    Reconciled verses do NOT need needs_review — the fix was mechanically
    applied and re-verified, not left as an open disagreement.

    Verses that pass pyarud but were flagged by the advisory إعراب
    (structural, non-reconcilable) or naturalness checks are still
    committed, but with needs_review=True and a disagreement log entry —
    flagged, not silently dropped, not silently "cleaned."
    """
    full_text = f"{sadr} {ajuz}".strip()

    sanitize_result = sanitize_output_tool(full_text)
    if not sanitize_result["valid"]:
        return {"committed": False, "reason": f"sanitization failed: {sanitize_result['reason']}"}

    verify_result = verify_single_verse_tool(sadr, ajuz, meter)
    if not verify_result["is_sound"]:
        return {"committed": False, "reason": "failed pyarud re-check at commit time",
                 "score": verify_result["combined_score"]}

    # Reconciled verses resolved their disagreement mechanically; only a
    # non-reconciled flag is a genuine open disagreement worth review.
    needs_review = (irab_flag or naturalness_flag) and not reconciled
    record = {
        "verse_id": verse_id,
        "meter": meter,
        "sadr": sadr,
        "ajuz": ajuz,
        "combined_score": verify_result["combined_score"],
        "needs_review": needs_review,
        "irab_flag": irab_flag,
        "naturalness_flag": naturalness_flag,
        "reconciled": reconciled,
        "original_sadr": original_sadr,
        "original_ajuz": original_ajuz,
        "notes": notes,
    }

    DATASET_PATH.parent.mkdir(parents=True, exist_ok=True)
    with DATASET_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")  # append-only, never overwrite

    if needs_review:
        _log_disagreement(verse_id, record)

    return {"committed": True, "needs_review": needs_review}


def _log_disagreement(verse_id: str, record: dict) -> None:
    log_dir = pathlib.Path(__file__).resolve().parent.parent / "logs" / "disagreements"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{verse_id}.json"
    log_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")


def log_unresolved_tool(verse_id: str, sadr: str, ajuz: str, meter: str, last_report: str) -> dict:
    """Log a verse that failed to converge within the max-pass budget.
    Excluded from the dataset entirely — never force a further pass,
    never auto-accept.
    """
    log_dir = pathlib.Path(__file__).resolve().parent.parent / "logs" / "disagreements"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{verse_id}_unresolved.json"
    log_path.write_text(
        json.dumps(
            {"verse_id": verse_id, "sadr": sadr, "ajuz": ajuz, "meter": meter,
             "status": "unresolved", "last_correction_report": last_report},
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    return {"logged": True}
