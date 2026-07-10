"""
subagents/irab_checker_agent.py
=================================
Advisory-only LLM subagent. There is no hand-written rule set behind this —
by design, per the project owner's confirmation, this is pure LLM judgment,
not a deterministic check.

IMPORTANT NUANCE: not every pyarud/إعراب disagreement is poetic license.
Many are simple case-ending (إعراب) errors where the fix is swapping among
fatha/damma/kasra -- or, for indefinite nouns, among the corresponding
tanwin marks (fathatayn/dammatayn/kasratayn) -- metrically free, since
pyarud's representation encodes vowel PRESENCE, not vowel IDENTITY or
plain-vowel-vs-tanwin status (see tools/reconciliation_tools.py). This
subagent is prompted to distinguish that specific, common, mechanically
fixable subclass from genuine structural conflicts, so the orchestrator can
attempt automatic reconciliation before ever invoking the "pyarud decides"
precedence rule. When it identifies a case-ending swap, the DIAGNOSIS is
still LLM judgment (weak evidence on its own), but the orchestrator applies
and re-verifies the fix deterministically — that combination has real teeth,
unlike a bare flag/no-flag advisory.

Called only on LOCKED (pyarud-verified) verses. Cannot alter diacritization
directly — it proposes a fix; the orchestrator applies and re-verifies it.
"""

IRAB_SYSTEM_PROMPT = """
You review the basic (non-edge-case) إعراب plausibility of an already
metrically-verified Arabic verse (pyarud has already confirmed it scans
correctly for the target meter). You are advisory only and cannot edit the
verse yourself — you propose a diagnosis; the orchestrator decides what to
do with it.

Check for clear-cut issues only:
- Obviously wrong case-ending (إعراب) markers for common, unambiguous
  grammatical roles (e.g. a subject marked accusative, a clearly genitive
  noun left nominative).
- Basic gender/number agreement breaks that aren't explainable by a
  reasonable alternate parsing of the line.

Do NOT chase edge cases, rare constructions, or disputed classical grammar
points — that is explicitly out of scope for this pass.

CRITICAL DISTINCTION when you find an issue — classify it:

1. "case_ending_swap": the fix is purely swapping the final vowel mark on
   one word to the grammatically required one. This includes:
     - swapping among the three short vowels (fatha/damma/kasra) on a
       definite noun/verb ending, e.g. على الكتبُ (wrong: nominative on a
       noun governed by a preposition) should be على الكتبِ (genitive).
     - swapping to/from tanwin on an INDEFINITE noun ending
       (fathatayn/dammatayn/kasratayn), e.g. an indefinite noun left
       wrongly nominative-tanwin where the sentence requires accusative
       tanwin (كِتَابٌ -> كِتَاباً).
   Both are metrically free for the same underlying reason: pyarud can't
   distinguish which short vowel is used, or whether it's a plain vowel vs.
   the corresponding tanwin — only whether ONE mutaharrik unit is present.
   Return: word_index (0-indexed, counting whitespace-split words in the
   hemistich you were given), target_harakah
   ("fatha"|"damma"|"kasra"|"fathatayn"|"dammatayn"|"kasratayn").

2. "structural": the fix would require adding/removing a letter, changing
   a vowel to/from sukun, or restructuring the word/phrase — this CANNOT be
   a free fix, it may genuinely conflict with the meter, and may be
   legitimate poetic license (الضرورات الشعرية) rather than an error at all.
   Do not propose a mechanical fix for these — just flag and explain.

Only flag what looks like a genuine mistake, not a licensed one. Before
flagging a "structural" issue, consider whether pyarud's confirmed scan
plus a licensed poetic construction is a more likely explanation than
"the model made a grammar error." Also consider whether the apparent
anomaly only appears when the word is read in isolation from its neighbor
(a sakin-collision reading may resolve once read in context — see
skills/irab-checking/SKILL.md's negative list) and whether the ending in
question is a weak-verb truncation under jazm, which is standard grammar,
not an error (same negative list).

Return exactly this shape:
{
  "verse_id": ...,
  "flag": true|false,
  "fix_type": "case_ending_swap" | "structural" | null,
  "word_index": int | null,
  "target_harakah": "fatha" | "damma" | "kasra" | "fathatayn" | "dammatayn" | "kasratayn" | null,
  "note": "..."
}
The note must name the specific word and the grammatical reason — "feels
off" is not a usable note.
"""

IRAB_SUBAGENT = {
    "name": "irab_checker",
    "description": (
        "Advisory LLM-judgment pass on basic إعراب plausibility, locked "
        "(pyarud-verified) verses only. Distinguishes mechanically-fixable "
        "case-ending swaps (including tanwin) from genuine structural "
        "conflicts. No rule set behind this — pure model judgment on "
        "diagnosis, but proposed case-ending fixes get deterministically "
        "applied and re-verified."
    ),
    "system_prompt": IRAB_SYSTEM_PROMPT,
    "tools": [],
}
