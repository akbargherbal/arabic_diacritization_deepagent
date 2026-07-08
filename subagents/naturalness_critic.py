"""
subagents/naturalness_critic.py
=================================
LLM-based advisory pass targeting the specific Goodhart gap: a verse can
satisfy pyarud's binary scan while being phonologically unnatural (extra
vowels, unnatural elongations, silent-letter abuse) in a way no human would
actually vocalize. This check exists BECAUSE the pyarud proxy is gameable,
not as a generic quality pass.

Same model family as the diacritizer (per project constraint: DeepSeek for
both) — treat its flags as weaker evidence than the deterministic axes.
Never used as a gate, never used as a tiebreaker for a pyarud/إعراب conflict.
"""

NATURALNESS_SYSTEM_PROMPT = """
You review an already metrically-verified (pyarud-passing) Arabic verse for
phonological naturalness: would a fluent speaker actually vocalize it this
way, or does it read as artificially stretched/padded to force a metrical
match (e.g. unnatural vowel lengthening, implausible silent-letter choices,
an unlikely reading of an ambiguous word chosen only because it scans)?

You are advisory only. You do not have access to any verification tool and
cannot alter the verse. Return {"verse_id": ..., "natural": bool, "note": str}.

Be specific in your note about WHAT reads as unnatural if you flag one —
"feels off" is not useful, "the elongation on X requires reading it as Y
which no fluent speaker would default to" is.
"""

NATURALNESS_CRITIC_SUBAGENT = {
    "name": "naturalness_critic",
    "description": (
        "Advisory LLM pass flagging pyarud-passing verses that read as "
        "phonologically unnatural. Same model family as the diacritizer — "
        "treat flags as weaker evidence than deterministic axes."
    ),
    "system_prompt": NATURALNESS_SYSTEM_PROMPT,
    "tools": [],
}
