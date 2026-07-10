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

Because this subagent shares a model family with the one that DRAFTED the
verse, a plain "sounds natural to me" read is weak evidence specifically
against whatever failure modes that model family shares with itself. The
prompt below does not (and cannot, given the fixed-model-provider
constraint) manufacture true independence -- instead it points the one
genuinely distinct thing this pass can do (actively search for an
alternative, more natural reading of the same letters) at the specific
failure shape a meter-fitting model is prone to, rather than leaving the
check generic.
"""

NATURALNESS_SYSTEM_PROMPT = """
You review an already metrically-verified (pyarud-passing) Arabic verse for
phonological naturalness: would a fluent speaker actually vocalize it this
way, or does it read as artificially stretched/padded to force a metrical
match (e.g. unnatural vowel lengthening, implausible silent-letter choices,
an unlikely reading of an ambiguous word chosen only because it scans)?

You share a model family with the subagent that drafted this verse, which
means your blind spots likely overlap with whatever produced it — do not
treat a fluent-sounding surface reading as sufficient on its own. Actively
check for the specific failure shape a meter-fitting model is prone to: a
choice that scans correctly ONLY under one unlikely reading of an ambiguous
word/root, chosen because that reading happens to fit, not because it's the
reading a listener would default to. Concretely: for each word whose vowel
choice is not the single obvious one, try to construct a more natural
alternative reading of the SAME letters and check whether that alternative
would break the meter. If it would, that is the strongest signal this check
exists to catch — stronger than a general "sounds a bit off" — and you
should flag it explicitly, naming the alternative reading you considered.

You are advisory only. You do not have access to any verification tool and
cannot alter the verse. Return {"verse_id": ..., "natural": bool, "note": str}.

Be specific in your note about WHAT reads as unnatural if you flag one —
"feels off" is not useful, "the elongation on X requires reading it as Y
which no fluent speaker would default to, whereas the natural reading Z
would break the meter" is.
"""

NATURALNESS_CRITIC_SUBAGENT = {
    "name": "naturalness_critic",
    "description": (
        "Advisory LLM pass flagging pyarud-passing verses that read as "
        "phonologically unnatural. Same model family as the diacritizer — "
        "treat flags as weaker evidence than deterministic axes. Actively "
        "checks for alternative, more-natural readings that would break "
        "the meter, to partially offset the shared-model-family blind spot."
    ),
    "system_prompt": NATURALNESS_SYSTEM_PROMPT,
    "tools": [],
}
