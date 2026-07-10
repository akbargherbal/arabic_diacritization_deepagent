# Arabic Prosody Diacritization — Dataset Builder (DeepAgents PoC)

This project is a dataset generation pipeline designed to produce metrically sound, letter-faithful, and grammatically plausible diacritized Arabic poetry. It leverages Large Language Models (LLMs) as generative drafters while enforcing deterministic programmatic quality criteria through automated validation gates to assemble high-fidelity training data.

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

### The Orchestrator & Validation Core

- **Orchestration**: Manages the execution pipeline over raw verse batches, enforcing a lock-on-success rule, a maximum of 3 correction passes, and automated state-saving checkpointing.
- **Advisory Subagents**: Cooperating agents specializing in draft diacritization (`diacritizer`), grammatical analysis (`irab_checker`), and stylistic compliance (`naturalness_critic`).
- **Four-Axis Validation**: To qualify for the final dataset, every proposed verse must clear three Deciding gates (Security, Fidelity, and Structural) and is annotated by a fourth Advisory axis (Linguistic) to determine if it should be committed with a review flag.

For a detailed walkthrough of the pipeline flow, subagent prompts, and the mechanical case-ending reconciliation loop, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## 4. Quick Start

### Installation & Setup

1. Clone the repository and navigate to the project root:
   ```bash
   cd arabic_diacritization_deepagent
   ```

````

2. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Set your target model provider API keys and optional custom base URLs in your environment:
   ```bash
   export MODEL_PROVIDER="deepseek"
   export DEEPSEEK_API_KEY="your-api-key"
   ```

### Running the Pipeline

To run the diacritization pipeline against the standard inputs:

```bash
python main.py
```

- **Checkpoint & Resume**: If interrupted mid-flight (e.g., via `Ctrl+C`), re-running the script will automatically resume from the last saved state in `checkpoints.sqlite` using LangGraph's native checkpointer.

---

## 5. Directory Structure

```
.
├── AGENTS.md                 # Agent charter, persistent rules, and design rationale
├── README.md                 # This file (Project Overview & Quick Start)
├── main.py                   # Main pipeline entrypoint and orchestrator agent
├── requirements.txt          # Python dependencies
├── backends/
│   └── model_provider.py    # Multi-provider model loader with retry and timeout layers
├── config/
│   └── meter_tables.py       # Ground-truth poetic meter templates & canonical patterns
├── dataset/
│   ├── inputs/               # Untrusted raw input batches (e.g., batch_01.jsonl)
│   ├── verses.jsonl          # High-fidelity committed dataset (Deciding gates passed)
│   └── verses_rejected.jsonl # Uniform diagnostic log of all rejected attempts
├── docs/                     # Detailed technical and execution documentation
│   ├── ARCHITECTURE.md       # Pipeline flows, subagents, and reconciliation details
│   ├── CONFIGURATION.md      # Sandbox permissions, model provider parameters, & checkpointing
│   └── TRACING.md            # Execution token tracing & offline reporting
├── logs/disagreements/       # JSON exports of advisory flags and unresolved failures
├── skills/                   # Guidance and rules loaded dynamically by subagents
├── subagents/                # Advisory and generative agent prompt declarations
└── tools/                    # Core programmatic validation and debugging utilities
```

---

## 6. Documentation Index

For advanced configuration, auditing, and architectural specifics, refer to the following documents:

- **[AGENTS.md](AGENTS.md)**: Persistent memory, non-negotiable behavior constraints, and project rules.
- **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**: Deep dive into the orchestrator loop, subagents, validation axes, and the case-ending swap reconciliation tool.
- **[docs/CONFIGURATION.md](docs/CONFIGURATION.md)**: Technical breakdown of DeepAgents security paths, local database checkpointing settings, and supported LLM backends (Anthropic, OpenAI, DeepSeek, and NVIDIA NIM).
- **[docs/TRACING.md](docs/TRACING.md)**: Guide to using `traces.sqlite` and the trace reporting CLI to audit latency, token counts, and execution runs.
````
