---
name: meter-fitting
description: Reference for fitting Arabic verse diacritization to a target
  prosodic meter (تقطيع عروضي) — canonical foot patterns, known zihafat
  (metrical variations) per foot, and the foot sequence for each of the
  16 classical meters. Use when diacritizing or repairing a verse against
  a named meter, or when interpreting a correction_report that names a
  specific foot or zihaf.
---

# Skill: Meter Fitting (تقطيع عروضي)

## When to use

Loaded by the `diacritizer` subagent when a `correction_report` names a
specific foot, a specific zihaf, or a divergence between the expected and
actual U/\_ (harakah/sukun) pattern, and the base system prompt's
instructions aren't enough to act on that report precisely. Also useful
whenever you need the canonical bit pattern for a foot or the foot
sequence that makes up a given meter.

This file only contains what's already encoded as ground truth in
`config/meter_tables.py` (which is deny(write, edit) — never propose
changing it to make a verse "pass"). It does not invent domain knowledge
beyond that file's tables; see **Status** below for what's still missing.

## Reading the patterns

Each foot pattern below is a bit string: `1` = a syllable with a harakah
(mutaharrik), `0` = a syllable with sukun (sakin). A zihaf changes a
canonical foot's pattern in a specific, foot-appropriate way — it is not
an arbitrary bit flip.

## Canonical foot patterns

From `CANONICAL_PATTERNS`:

| Foot (transliterated)       | Pattern   |
| --------------------------- | --------- |
| Fawlon (فَعُولُنْ)          | `11010`   |
| Faelon (فَاعِلُنْ)          | `10110`   |
| Faelaton (فَاعِلَاتُنْ)     | `1011010` |
| Mafaeelon (مَفَاعِيلُنْ)    | `1101010` |
| Mustafelon (مُسْتَفْعِلُنْ) | `1010110` |
| Mutafaelon (مُتَفَاعِلُنْ)  | `1110110` |
| Mafaelaton (مُفَاعَلَتُنْ)  | `1101110` |
| Mafoolato (مَفْعُولَاتُ)    | `1010101` |
| Mustafe_lon                 | `1010110` |
| Fae_laton                   | `1011010` |

## Known zihafat per foot

From `_ZIHAF_MAP` — keyed by `(canonical_pattern, observed_pattern)`. If a
foot's observed pattern doesn't match its canonical one, check here before
assuming an error; it may be a named, licensed variation:

- **Fawlon** (`11010`): `1101`→Qabadh, `110`→Hadhf, `10`→Batr
- **Faelon** (`10110`): `1110`→Khaban
- **Faelaton** (`1011010`): `111010`→Khaban, `101101`→Kaff, `10110`→Hadhf,
  `11101`→Shakal, `1011`→Waqf
- **Mafaeelon** (`1101010`): `110110`→Qabadh, `110101`→Kaff, `11010`→Hadhf,
  `11011`→Shakl_alt
- **Mustafelon** (`1010110`): `110110`→Khaban, `101110`→Tay, `11110`→Khabal,
  `101010`→Kasf
- **Mutafaelon** (`1110110`): `1010110`→Edmaar, `110110`→Waqas,
  `101110`→Khazal
- **Mafaelaton** (`1101110`): `110110`→Akal, `1101010`→Asab, `11010`→Qatf
- **Mafoolato** (`1010101`): `110101`→Khaban, `101101`→Tay, `10101`→Kasf

## Meter → foot sequence

From `METER_TEMPLATES` (diacritized), with the matching Arabic meter name
from `METER_ARABIC_NAMES`:

| Meter (key) | الاسم    | Template                                       |
| ----------- | -------- | ---------------------------------------------- |
| taweel      | الطويل   | فَعُولُنْ مَفَاعِيلُنْ فَعُولُنْ مَفَاعِلُ     |
| madeed      | المديد   | فَاعِلَاتُنْ فَاعِلُنْ فَاعِلَاتُ              |
| baseet      | البسيط   | مُسْتَفْعِلُنْ فَاعِلُنْ مُسْتَفْعِلُنْ فَعِلُ |
| wafer       | الوافر   | مُفَاعَلَتُنْ مُفَاعَلَتُنْ فَعُولُ            |
| kamel       | الكامل   | مُتَفَاعِلُنْ مُتَفَاعِلُنْ مُتَفَاعِلُ        |
| hazaj       | الهزج    | مَفَاعِيلُنْ مَفَاعِيلُ                        |
| rajaz       | الرجز    | مُسْتَفْعِلُنْ مُسْتَفْعِلُنْ مُسْتَفْعِلُ     |
| ramal       | الرمل    | فَاعِلَاتُنْ فَاعِلَاتُنْ فَاعِلَاتُ           |
| saree       | السريع   | مُسْتَفْعِلُنْ مُسْتَفْعِلُنْ فَاعِلُ          |
| munsareh    | المنسرح  | مُسْتَفْعِلُنْ مَفْعُولَاتُ مُفْتَعِلُ         |
| khafeef     | الخفيف   | فَاعِلَاتُنْ مُسْتَفْعِلُنْ فَاعِلَاتُ         |
| mudhare     | المضارع  | مَفَاعِيلُ فَاعِلَاتُ                          |
| muqtadheb   | المقتضب  | مَفْعُولَاتُ مُفْتَعِلُ                        |
| mujtath     | المجتث   | مُسْتَفْعِلُنْ فَاعِلَاتُ                      |
| mutakareb   | المتقارب | فَعُولُنْ فَعُولُنْ فَعُولُنْ فَعُولُ          |
| mutadarak   | المتدارك | فَعِلُنْ فَعِلُنْ فَعِلُنْ فَعِلُ              |

Note the trailing foot of a hemistich is often a truncated variant of the
foot used elsewhere in the same template (e.g. taweel ends `مَفَاعِلُ`,
not the full `مَفَاعِيلُنْ`) — that's expected, not a defect to "fix".

Accepted spellings/aliases for a meter name (e.g. `tawil`, `ṭawīl`, `طويل`
all resolve to the same meter) are in `_ALIASES`; `_METER_TABLE_TO_PYARUD`
maps that internal key to the name pyarud itself expects.

## Status

The tables above are reproduced directly from `config/meter_tables.py` and
are safe to treat as ground truth. Two things called for in the original
design are **not** included here and remain a stub, because fabricating
them would be worse than leaving them blank:

- Classical example verses correctly scanned per meter, for few-shot
  grounding.
- Meter-specific notes on common LLM failure patterns (e.g. Taweel vs.
  Mutaqarib foot-count confusion), which need to come from observed
  correction-pass failures, not be guessed in advance.

Populate both incrementally as real correction-pass data accumulates,
ideally with a linguist collaborator reviewing additions before they're
treated as guidance.
