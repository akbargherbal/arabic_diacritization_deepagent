"""
tools/reconciliation_tools.py
================================
Handles the specific, common case where pyarud and إعراب "disagree" but
aren't actually in conflict: a case-ending (إعراب) error where the required
fix is swapping among fatha/damma/kasra.

Why this is mechanically safe: pyarud's structural representation encodes
whether a letter carries a short vowel at all (mutaharrik vs sakin) — it
does NOT distinguish which short vowel. Fatha, damma, and kasra are all a
single mora / one "moving" unit. Swapping between them cannot change the
metrical (U/_) pattern in the underlying model.

This is a claim about Arabic prosody in general, not a guarantee about this
specific pyarud build's converter (which has at least one documented
upstream bug already — see verification/arabic_prosody_feedback.py's
module docstring). So this tool does NOT assume immunity: every caller
MUST re-verify with verify_single_verse_tool after applying a swap, and
only treat it as reconciled if that re-check still passes. If it doesn't,
this was not actually a free fix, and the orchestrator should fall back
to the poetic-license precedence rule instead (see AGENTS.md).

Known limitation of this mechanical implementation: it targets the LAST
basic harakah mark (fatha/damma/kasra) in a whitespace-delimited word as
"the case ending." It does NOT handle tanwin, shadda-stacked marks, or a
pausal (waqf) sukun ending — if none of the three basic marks is found,
it reports failure rather than guessing, and the orchestrator should route
that case to the standard precedence rule / disagreement log instead.
"""

FATHA = "\u064E"
DAMMA = "\u064F"
KASRA = "\u0650"

HARAKAT = {"fatha": FATHA, "damma": DAMMA, "kasra": KASRA}
BASIC_MARKS = set(HARAKAT.values())


def reconcile_case_ending_tool(hemistich_text: str, word_index: int, target_harakah: str) -> dict:
    """
    Mechanically swap the final basic harakah on the word at word_index
    (0-indexed, whitespace-split) to target_harakah ("fatha"|"damma"|"kasra").

    Returns {"success": bool, "reconciled_text": str | None, "reason": str | None}.

    This function makes NO pyarud call itself — the orchestrator must call
    verify_single_verse_tool on the result and only accept it as reconciled
    if the score still meets threshold. If it drops, treat this as a genuine
    structural conflict, not a free fix, and fall back to the precedence rule.
    """
    if target_harakah not in HARAKAT:
        return {"success": False, "reconciled_text": None,
                "reason": f"unknown target_harakah '{target_harakah}', expected fatha/damma/kasra"}

    words = hemistich_text.split(" ")
    if word_index < 0 or word_index >= len(words):
        return {"success": False, "reconciled_text": None, "reason": "word_index out of range"}

    word = words[word_index]
    positions = [i for i, ch in enumerate(word) if ch in BASIC_MARKS]
    if not positions:
        return {"success": False, "reconciled_text": None,
                "reason": ("no basic fatha/damma/kasra mark found on this word's ending "
                           "(tanwin/sukun/shadda case) — not handled by this mechanical tool, "
                           "route to the standard precedence rule instead")}

    last_pos = positions[-1]
    new_word = word[:last_pos] + HARAKAT[target_harakah] + word[last_pos + 1:]
    words[word_index] = new_word
    return {"success": True, "reconciled_text": " ".join(words), "reason": None}
