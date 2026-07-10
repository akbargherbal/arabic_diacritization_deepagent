---
name: irab-checking
description: Rules and guidelines for reviewing basic (non-edge-case) classical
  Arabic grammar (إعراب) on already metrically-sound verses. Distinguishes between
  mechanical, metrically-free case-ending swaps and structural/poetic license
  violations.
---

# Skill: Basic إعراب Checking

## When to use

Loaded by the `irab_checker` subagent to evaluate whether a metrically correct Arabic verse contains glaring grammatical anomalies. Your judgment is advisory and non-blocking, but your classification governs whether the orchestrator can attempt an automated mechanical fix before committing.

## Classification Framework

You must classify every detected issue into one of these two categories:

### 1. `case_ending_swap` (Mechanically Fixable)
*   **Definition:** The grammatical error is purely on the final vowel mark of a single word, where changing it resolves the error completely. This covers two related cases:
    *   Swapping among the three basic short vowels (fatha/damma/kasra) on a definite ending.
    *   Swapping to/from tanwin (fathatayn/dammatayn/kasratayn) on an **indefinite** noun ending.
*   **Metrical Impact:** Metrically free in both cases! The parser scans only vowel presence (harakah vs. sukun), not the identity of the short vowel, and a tanwin mark is a single mutaharrik unit exactly like a plain short vowel. Swapping a damma for a kasra, or a dammatayn for a fathatayn, does not alter the meter.
*   **Action:** Propose a mechanical swap. Provide the whitespace-split, 0-indexed `word_index` and the target vowel mark (`target_harakah`: `"fatha"` | `"damma"` | `"kasra"` | `"fathatayn"` | `"dammatayn"` | `"kasratayn"`).
*   **Examples:**
    *   *على الكتبُ* (wrong nominative after a preposition) $\rightarrow$ swap to *على الكتبِ* (genitive `kasra`).
    *   *إنّ زيدٌ* (wrong nominative noun of *Inna*) $\rightarrow$ swap to *إنّ زيداً* (accusative `fatha`).
    *   *رأيتُ كِتَابٌ* (indefinite object wrongly left nominative-tanwin) $\rightarrow$ swap to *رأيتُ كِتَاباً* (accusative `fathatayn` — note the accompanying orthographic alif seat; `tools/reconciliation_tools.py` applies this automatically when swapping to `fathatayn`, except on تاء مربوطة، ألف مقصورة، or hamza-already-on-alif endings).
    *   *مررتُ بكِتَابٌ* (indefinite object of a preposition wrongly left nominative-tanwin) $\rightarrow$ swap to *مررتُ بكِتَابٍ* (genitive `kasratayn`, no alif seat involved).

### 2. `structural` (Metrically Non-Free / Poetic License)
*   **Definition:** Fixing the grammatical issue requires changing consonantal letters, adding/dropping syllables, altering internal/middle short vowels, or changing a final vowel to or from a sukun.
*   **Metrical Impact:** Metrically risky. Modifying structural elements will alter the harakah/sukun pattern, potentially breaking the pyarud scan. 
*   **Action:** Flag the verse as `structural`. Describe the issue in the `note` but do not suggest a deterministic word swap. The orchestrator will rely on the precedence rule: **pyarud decides**, and the original text is preserved with a review flag.

---

## Positive List (Glaring Grammatical Violations to Flag)

Flag ONLY unambiguous, clear-cut grammatical breaks:
1.  **Agreement Anomalies:** Lack of gender, number, or definiteness coordination between an adjective (*na't*) and its qualified noun (*man'ut*), provided it cannot be resolved via alternative parsing.
2.  **Basic Subjunctive/Jussive Breaks:** Sound verbs that are clearly governed by jussive (جزم) or subjunctive (نصب) particles but carry incorrect indicative case endings (like keeping a nominative damma after *lam* or *lan*).
3.  **Severe Subject/Predicate Inversions:** When a clear subject or nominal sentence starter (*mubtada*) is marked with a genitive kasra, or a prepositional object is marked with a nominative damma (and is not an instance of poetic license below).

---

## Negative List (Edge Cases Out of Scope — DO NOT FLAG)

Do not over-flag legitimate classical constructions. Treat the following as
grammatically plausible:

*   **Mamnu' min al-Sarf (الممنوع من الصرف):** Words on specific
    morphological structures that end in fatha instead of kasra when
    genitive. Do not flag them.
*   **Sakin Collision (التقاء الساكنين):** When a word's final sakin
    consonant meets the next word's initial consonant across a hemistich
    boundary or in fluid recitation, the resulting reading may require a
    helping vowel or elision that looks like a case-ending anomaly when the
    word is read in isolation. Before flagging, check whether the apparent
    error resolves once the word is read together with its neighbor — if it
    does, this is not an error.
*   **Weak Verb Truncation (حذف حرف العلة للجزم):** A weak/muʿtall verb
    (root containing و/ي/ا) legitimately DROPS its final weak letter under
    jussim (جزم) — e.g. لم يَقُلْ (not لم يَقُولْ), لم يَخْشَ (not لم يَخْشَى).
    This is standard grammar, not poetic license — never flag it as an
    error, and never propose a `case_ending_swap` for it (there is no vowel
    swap that "fixes" a correctly-truncated weak verb).
*   **Weak Verb Dialectal Vowel Variation:** Distinct from truncation above
    — an atypical but attested short-vowel choice on a weak verb's
    remaining letters (not a truncation question). This is a much weaker
    "don't flag" signal than truncation above; if genuinely uncertain, a
    low-confidence `structural` flag with a note explaining the specific
    dialectal reading considered is acceptable here, unlike the other items
    in this list.
*   **Ellipsis (حذف):** Omission of standard nouns or particles when implied
    by context.

---

## Poetic License (الضرورات الشعرية)
If a verse scans perfectly according to pyarud, classical tradition grants the poet the right to override rigid grammar rules. **Assume Poetic License is active if a structural mismatch is the only way to fit the meter.**
Common poetic licenses include:
*   Adding tanween to un-tanweened nouns (*صرف الممنوع من الصرف*).
*   Shortening long vowels (*قصر الممدود*) or lengthening short ones (*مد المقصور*).
*   Quieting a syllable by putting a sukun on a moving middle consonant (e.g., *كُتُب* $\rightarrow$ *كُتْب*).

## Status

Fully configured. Grounded in standard classical grammar rules and compatible with the orchestrator's automated reconciliation tools, including the tanwin extension in `tools/reconciliation_tools.py`.
