# Arabic Prosody Diacritization — Dataset Builder (DeepAgents PoC)

This project is a dataset generation pipeline designed to produce metrically sound, letter-faithful, and grammatically plausible diacritized Arabic poetry. It leverages large language models (LLMs) as generative drafters while enforcing deterministic quality criteria through automated validation gates to assemble high-fidelity training data.

---

## 1. Project Purpose & Scope

The primary purpose of this system is to compile training corpora of classical Arabic verses. It processes normalized (undiacritized) inputs and outputs fully diacritized pairs (Sadr and Ajuz) matching specific poetic meters. The system operates on a hybrid verification model where generative AI proposes drafts, but deterministic programmatic logic holds absolute veto power over what is ultimately committed.

---

## 2. Core Objectives

- **Metrical Compliance**: Guarantee that all committed verses strictly adhere to the target prosodic meter (rhythm) as evaluated by the `pyarud` engine.
- **Skeleton Fidelity**: Ensure that the underlying consonant structure (the letter skeleton) of the input verse remains completely unchanged during the diacritization process, preventing hallucinated verse substitutions or character-level drift.
- **Security & Sanitization**: Protect downstream consumers by filtering out invalid character injections, control characters, or non-Arabic Unicode blocks.
- **Linguistic Coherence**: Identify and document potential grammatical (`إعراب`) or stylistic anomalies using LLM-based advisory judgment.

---

## 3. High-Level Architecture

The system utilizes an orchestrator-agent pattern, segregating generation from verification to maintain strict quality boundaries.

```
       [ Raw Undiacritized Inputs ]
                   │
                   ▼
         ┌───────────────────┐
         │   Orchestrator    │◄───────┐
         └───────────────────┘        │
           │               │          │ [Up to 3 correction passes]
           ▼               ▼          │
     [Subagents]     [Verification] ──┘
     - Diacritizer   - Sanitizer (Security) [Deciding]
     - Irab Checker  - Fidelity Check (Consonants) [Deciding]
     - Naturalness   - pyarud (Structure/Meter) [Deciding]
                           │
                           ├──► [PASS] ──► [ dataset/verses.jsonl ]
                           │
                           └──► [FAIL] ──► [ dataset/verses_rejected.jsonl ]
```

### The Orchestrator

The main control loop manages the execution pipeline:

1. Coordinates the subagents' batch processing.
2. Implements a lock-on-success rule, shielding metrically sound verses from subsequent modifications.
3. Facilitates mechanical case-ending (`إعراب`) adjustments where grammar and meter can be reconciled without altering rhythmic weights.
4. Manages the iteration budget (maximum 3 passes) and routes unresolved or failed verses to the review queue.

### Advisory Subagents

- **Diacritizer**: Drafts and repairs diacritics (Harakat) for non-locked verses based on structural correction reports. It is restricted from modifying base letters.
- **Irab Checker**: Advises on case-ending consistency and proposes minor, non-metrical vowel swaps to resolve basic grammatical errors.
- **Naturalness Critic**: Identifies phonological stretches, unnatural silent letters, or stylistic anomalies introduced to artificially satisfy metrical constraints.

### The Verification Gates (Four-Axis Validation)

To qualify for the final dataset, every proposed verse must pass through three deciding gates and is annotated by a fourth advisory axis:

1.  **Security Axis (Sanitizer)** `[Deciding]`: Scans unicode ranges to ensure only expected Arabic characters and punctuation are present.
2.  **Fidelity Axis (Consonants)** `[Deciding]`: Strips diacritics from the proposed output and performs an exact string comparison against the original undiacritized input. Any consonant modification triggers a hard reject.
3.  **Structural Axis (pyarud)** `[Deciding]`: Runs a prosodic analysis to confirm the verse conforms to the expected syllable weight patterns.
4.  **Linguistic Axis (LLM Advisory)** `[Advisory]`: Captures and documents irab or naturalness flags. Flagged verses are committed but tagged as `needs_review`.

---

## 4. Dataset Integrity

The pipeline generates two output streams:

- **`dataset/verses.jsonl`**: The primary output corpus containing only verses that successfully cleared all deciding gates.
- **`dataset/verses_rejected.jsonl`**: A uniform diagnostic log capturing every failed attempt. It lists the rejection stage, structural scores, character-level diffs, and validation notes to assist human operators in auditing false positives or system bugs.
