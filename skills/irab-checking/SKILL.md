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
*   **Definition:** The grammatical error is purely on the final short vowel mark (fatha, damma, kasra) of a single word, where changing it resolves the error completely.
*   **Metrical Impact:** Metrically free! The parser scans only vowel presence (harakah vs. sukun), not the identity of the short vowel. Swapping a damma for a kasra does not alter the meter.
*   **Action:** Propose a mechanical swap. Provide the whitespace-split, 0-indexed `word_index` and the target vowel mark (`target_harakah`: `"fatha"` | `"damma"` | `"kasra"`).
*   **Examples:**
    *   *على الكتبُ* (wrong nominative after a preposition) $\rightarrow$ swap to *على الكتبِ* (genitive `kasra`).
    *   *إنّ زيدٌ* (wrong nominative noun of *Inna*) $\rightarrow$ swap to *إنّ زيداً* (accusative `fatha`).

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

Do not over-flag legitimate classical constructions. Treat the following as grammatically plausible:
*   **Mamnu' min al-Sarf (الممنوع من الصرف):** Words on specific morphological structures that end in fatha instead of kasra when genitive. Do not flag them.
*   **Weak Verbs:** Dropping or keeping weak vowels in atypical positions, which often follows less common dialectical rules (*lughat*).
*   **Ellipsis (حذف):** Omission of standard nouns or particles when implied by context.

---

## Poetic License (الضرورات الشعرية)
If a verse scans perfectly according to pyarud, classical tradition grants the poet the right to override rigid grammar rules. **Assume Poetic License is active if a structural mismatch is the only way to fit the meter.**
Common poetic licenses include:
*   Adding tanween to un-tanweened nouns (*صرف الممنوع من الصرف*).
*   Shortening long vowels (*قصر الممدود*) or lengthening short ones (*مد المقصور*).
*   Quieting a syllable by putting a sukun on a moving middle consonant (e.g., *كُتُب* $\rightarrow$ *كُتْب*).

## Status

Fully configured. Grounded in standard classical grammar rules and compatible with the orchestrator's automated reconciliation tools.