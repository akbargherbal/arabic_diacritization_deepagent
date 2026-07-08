"""
tools/dataset_tools.py
========================
commit_verse_tool is the ONLY path into dataset/. Permission rules deny the
agent's built-in write_file/edit_file against dataset/**, but that layer
does NOT cover custom tools -- a custom tool is just a Python function the
agent can call, invisible to the declarative permissions system. So the
real enforcement lives here, in code:

  1. re-run the sanitizer (security axis, deciding)
  2. re-run the skeleton fidelity check (fidelity axis, deciding) --
     see tools/fidelity_tools.py
  3. re-run the pyarud check (never trust a stale "it passed earlier")
     (structural axis, deciding)
  4. append-only write, never overwrite/delete

This is design principle 3 made concrete: the gate's enforcement point is
code the agent cannot edit (verification/ is permission-denied), not
agent discretion, and not the permission system either.

Nothing is silently discarded. Every verse that fails any of the three
deciding gates -- sanitize, fidelity, pyarud -- is written to
dataset/verses_rejected.jsonl with full diagnostic detail (which gate
failed, the pyarud score if one was computed, the fidelity diff if one was
computed) so a human reviewer can see *why* it was rejected. pyarud is not
assumed infallible -- a rejection here is a candidate for human review,
not a verdict.
"""

import json
import pathlib
from datetime import datetime, timezone

from tools.prosody_tools import verify_single_verse_tool
from tools.sanitization_tools import sanitize_output_tool
from tools.fidelity_tools import verify_skeleton_fidelity_tool

DATASET_PATH = (
    pathlib.Path(__file__).resolve().parent.parent / "dataset" / "verses.jsonl"
)
REJECTED_PATH = (
    pathlib.Path(__file__).resolve().parent.parent / "dataset" / "verses_rejected.jsonl"
)
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
    """Commit one verified verse to the dataset. Re-checks sanitize,
    skeleton fidelity, and pyarud itself before writing -- do not treat an
    earlier verify_batch_tool pass as sufficient, this call re-verifies.

    A verse that fails any of the three checks is NOT discarded: it's
    written to dataset/verses_rejected.jsonl with the failing stage, the
    pyarud score (if computed), and the fidelity diff (if computed), for
    human review. pyarud has known false positives/negatives -- a
    rejection here is a lead for a reviewer, not a final judgment.

    If reconciled=True, sadr/ajuz are the POST-reconciliation text (after a
    deterministic case-ending swap resolved an إعراب flag without touching
    the meter — see tools/reconciliation_tools.py) and original_sadr/
    original_ajuz preserve what pyarud originally verified, for audit.
    Reconciled verses do NOT need needs_review — the fix was mechanically
    applied and re-verified, not left as an open disagreement.

    Verses that pass all three gates but were flagged by the advisory
    إعراب (structural, non-reconcilable) or naturalness checks are still
    committed to verses.jsonl, but with needs_review=True and a
    disagreement log entry — flagged, not silently dropped, not silently
    "cleaned."
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    full_text = f"{sadr} {ajuz}".strip()

    sanitize_result = sanitize_output_tool(full_text)
    if not sanitize_result["valid"]:
        reason = f"sanitization failed: {sanitize_result['reason']}"
        _append_rejected(
            _rejection_record(
                verse_id,
                sadr,
                ajuz,
                meter,
                stage="sanitize",
                reason=reason,
                pyarud_score=None,
                pyarud_detail=None,
                fidelity=None,
                irab_flag=irab_flag,
                naturalness_flag=naturalness_flag,
                notes=notes,
                timestamp=timestamp,
            )
        )
        return {"committed": False, "reason": reason, "logged_for_review": True}

    fidelity_result = verify_skeleton_fidelity_tool(verse_id, sadr, ajuz)
    if not fidelity_result["match"]:
        reason = (
            "skeleton fidelity check failed -- output letters diverge "
            "from the input verse, not just its diacritics"
        )
        _append_rejected(
            _rejection_record(
                verse_id,
                sadr,
                ajuz,
                meter,
                stage="fidelity",
                reason=reason,
                pyarud_score=None,
                pyarud_detail=None,
                fidelity=fidelity_result,
                irab_flag=irab_flag,
                naturalness_flag=naturalness_flag,
                notes=notes,
                timestamp=timestamp,
            )
        )
        return {
            "committed": False,
            "reason": reason,
            "fidelity": fidelity_result,
            "logged_for_review": True,
        }

    verify_result = verify_single_verse_tool(sadr, ajuz, meter)
    if not verify_result["is_sound"]:
        reason = "failed pyarud re-check at commit time"
        _append_rejected(
            _rejection_record(
                verse_id,
                sadr,
                ajuz,
                meter,
                stage="pyarud_commit",
                reason=reason,
                pyarud_score=verify_result.get("combined_score"),
                pyarud_detail=verify_result,
                fidelity=fidelity_result,
                irab_flag=irab_flag,
                naturalness_flag=naturalness_flag,
                notes=notes,
                timestamp=timestamp,
            )
        )
        return {
            "committed": False,
            "reason": reason,
            "score": verify_result.get("combined_score"),
            "logged_for_review": True,
        }

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
        "committed_at": timestamp,
    }

    DATASET_PATH.parent.mkdir(parents=True, exist_ok=True)
    with DATASET_PATH.open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(record, ensure_ascii=False) + "\n"
        )  # append-only, never overwrite

    if needs_review:
        _log_disagreement(verse_id, record)

    return {"committed": True, "needs_review": needs_review}


def _rejection_record(
    verse_id,
    sadr,
    ajuz,
    meter,
    *,
    stage,
    reason,
    pyarud_score,
    pyarud_detail,
    fidelity,
    irab_flag,
    naturalness_flag,
    notes,
    timestamp,
) -> dict:
    """Uniform schema for every rejected verse, regardless of which gate
    rejected it, so a human reviewer can scan verses_rejected.jsonl with
    one mental model instead of three different shapes."""
    return {
        "verse_id": verse_id,
        "meter": meter,
        "sadr": sadr,
        "ajuz": ajuz,
        "stage": stage,  # "sanitize" | "fidelity" | "pyarud_commit" | "unresolved_max_passes"
        "reason": reason,
        "pyarud_score": pyarud_score,  # combined_score if pyarud ran this time, else null
        "pyarud_detail": pyarud_detail,  # full verify_single_verse_tool() dict if it ran, else null
        "fidelity": fidelity,  # full verify_skeleton_fidelity_tool() dict if it ran, else null
        "irab_flag": irab_flag,
        "naturalness_flag": naturalness_flag,
        "notes": notes,
        "rejected_at": timestamp,
    }


def _append_rejected(record: dict) -> None:
    REJECTED_PATH.parent.mkdir(parents=True, exist_ok=True)
    with REJECTED_PATH.open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(record, ensure_ascii=False) + "\n"
        )  # append-only, mirrors verses.jsonl


def _log_disagreement(verse_id: str, record: dict) -> None:
    log_dir = pathlib.Path(__file__).resolve().parent.parent / "logs" / "disagreements"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{verse_id}.json"
    log_path.write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def log_unresolved_tool(
    verse_id: str, sadr: str, ajuz: str, meter: str, last_report: str
) -> dict:
    """Log a verse that failed to converge within the max-pass budget.
    Excluded from dataset/verses.jsonl -- never force a further pass,
    never auto-accept -- but still appended to verses_rejected.jsonl (not
    just the per-verse audit file under logs/disagreements/) so it shows
    up in the same human-review sweep as sanitize/fidelity/pyarud
    rejections, instead of needing a separate lookup path.
    """
    timestamp = datetime.now(timezone.utc).isoformat()

    log_dir = pathlib.Path(__file__).resolve().parent.parent / "logs" / "disagreements"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{verse_id}_unresolved.json"
    detail_record = {
        "verse_id": verse_id,
        "sadr": sadr,
        "ajuz": ajuz,
        "meter": meter,
        "status": "unresolved",
        "last_correction_report": last_report,
        "logged_at": timestamp,
    }
    log_path.write_text(
        json.dumps(detail_record, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    _append_rejected(
        _rejection_record(
            verse_id,
            sadr,
            ajuz,
            meter,
            stage="unresolved_max_passes",
            reason="did not converge within max correction passes",
            pyarud_score=None,
            pyarud_detail={"last_correction_report": last_report},
            fidelity=None,
            irab_flag=False,
            naturalness_flag=False,
            notes="",
            timestamp=timestamp,
        )
    )

    return {"logged": True}
