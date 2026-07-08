"""
main.py
========
Entrypoint. Constructs the orchestrator agent. Domain logic (real pyarud
implementation, real irab rules, real batch-invocation loop reading your
input format) is intentionally left for you to wire in — see README.md.

NOTE: deepagents' exact create_deep_agent signature, the permissions= rule
schema, and interrupt_on condition syntax move fast on this framework.
Confirm this against docs.langchain.com/oss/python/deepagents before
relying on it in production. What's below reflects the framework's
documented shape at design time, not a guarantee of the current API.
"""

import json
import pathlib
import os
import sqlite3

from deepagents import create_deep_agent, FilesystemPermission
from deepagents.backends import CompositeBackend, StateBackend, FilesystemBackend
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.sqlite import SqliteSaver

from tools.prosody_tools import (
    verify_batch_tool,
    meter_schema_tool,
    verify_single_verse_tool,
)
from tools.dataset_tools import commit_verse_tool, log_unresolved_tool
from tools.sanitization_tools import sanitize_output_tool
from tools.reconciliation_tools import reconcile_case_ending_tool
from subagents.diacritizer import DIACRITIZER_SUBAGENT
from subagents.irab_checker_agent import IRAB_SUBAGENT
from subagents.naturalness_critic import NATURALNESS_CRITIC_SUBAGENT

MAX_CORRECTION_PASSES = (
    3  # hard cap — do not raise without re-reading the design rationale
)

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent

PERMISSIONS = [
    # Order matters: first-match-wins, top-down. Unmatched paths default to
    # ALLOW in deepagents — every deny below is written defensively because
    # of that default, not because deny-by-default can be assumed.
    FilesystemPermission(
        paths=["/verification/**"], operations=["write", "edit"], mode="deny"
    ),
    FilesystemPermission(
        paths=["/config/meter_tables.py"], operations=["write", "edit"], mode="deny"
    ),
    FilesystemPermission(
        paths=["/dataset/**"], operations=["write", "edit", "delete"], mode="deny"
    ),
    FilesystemPermission(
        paths=["/tests/**"], operations=["write", "edit"], mode="deny"
    ),
    FilesystemPermission(paths=["/logs/**"], operations=["write"], mode="allow"),
    FilesystemPermission(
        paths=["/workspace/**"], operations=["read", "write", "edit"], mode="allow"
    ),
]

# ---------------------------------------------------------------------------
# Backend wiring
# ---------------------------------------------------------------------------
# create_deep_agent defaults to StateBackend(): an in-memory, per-thread
# filesystem that starts EMPTY on every invoke. The PERMISSIONS above only
# mean something if the paths they reference ("/dataset/**", "/workspace/**",
# etc.) actually correspond to your real project directories on disk — so we
# route each of those project paths to FilesystemBackend, and leave
# everything else (the agent's own internal bookkeeping under
# /large_tool_results/, /conversation_history/, etc.) on the ephemeral
# StateBackend default.
#
# virtual_mode=True is kept on even though root_dir is scoped per-folder,
# since the default (virtual_mode=False) gives no path-restriction safety
# even with root_dir set.
BACKEND = CompositeBackend(
    default=StateBackend(),
    routes={
        "/workspace/": FilesystemBackend(
            root_dir=str(PROJECT_ROOT / "workspace"), virtual_mode=True
        ),
        "/dataset/": FilesystemBackend(
            root_dir=str(PROJECT_ROOT / "dataset"), virtual_mode=True
        ),
        "/logs/": FilesystemBackend(
            root_dir=str(PROJECT_ROOT / "logs"), virtual_mode=True
        ),
        "/verification/": FilesystemBackend(
            root_dir=str(PROJECT_ROOT / "verification"), virtual_mode=True
        ),
        "/config/": FilesystemBackend(
            root_dir=str(PROJECT_ROOT / "config"), virtual_mode=True
        ),
        "/tests/": FilesystemBackend(
            root_dir=str(PROJECT_ROOT / "tests"), virtual_mode=True
        ),
    },
)

ORCHESTRATOR_SYSTEM_PROMPT = f"""
You coordinate diacritization of a batch of normalized Arabic verses against
a target meter, producing dataset records for a downstream training set.

The batch of verses and the target meter name are given to you directly in
the user message as JSON — read them from there. Do not go looking for them
on the filesystem; if a batch is already in your context, use it as-is.

You do NOT diacritize verses yourself — delegate to the `diacritizer`
subagent via the task tool. You DO call verify_batch_tool yourself between
passes; never let a subagent call it. The entity deciding pass/fail must
not be the entity trying to pass.

Locking rule: once a verse's pyarud scan is sound (from verify_batch_tool),
mark it locked and never resubmit it to the diacritizer for regeneration,
even in later passes or later batches.

Pass budget: maximum {MAX_CORRECTION_PASSES} correction passes per batch.
Verses still broken after that are logged via log_unresolved_tool and
EXCLUDED from the dataset — do not force a further pass, do not auto-accept.

--- Handling a pyarud/إعراب disagreement (two-step, in this order) ---

After a verse is locked, dispatch it to BOTH irab_checker and
naturalness_critic (advisory, non-gating, via task tool).

If irab_checker returns flag=true with fix_type="case_ending_swap":
  1. This is NOT automatically poetic license — attempt reconciliation
     FIRST. Call reconcile_case_ending_tool with the word_index and
     target_harakah it proposed. This performs a mechanical fatha/damma/
     kasra swap, which cannot change the metrical pattern.
  2. Re-run verify_single_verse_tool on the reconciled text.
  3. If it still passes: this was a genuine grammar fix with no metrical
     cost. Commit the reconciled text via commit_verse_tool with
     reconciled=True and original_sadr/original_ajuz set to the pre-swap
     text. Do NOT mark needs_review — this is resolved, not an open
     disagreement.
  4. If the reconciled text FAILS pyarud (rare, but the underlying
     converter has known quirks — see verification/arabic_prosody_feedback.py's
     docstring): the swap was not actually free in this instance. Fall
     back to the precedence rule below, using the ORIGINAL (pre-swap) text.

If irab_checker returns flag=true with fix_type="structural", or
reconciliation was attempted and failed per step 4 above:
  Precedence rule: pyarud decides. Commit the ORIGINAL pyarud-verified
  text via commit_verse_tool with irab_flag=True, needs_review will be set
  automatically. This is presumed poetic license (الضرورات الشعرية) unless
  a human reviewer says otherwise later — log it, don't block on it.

naturalness_critic flags follow the same non-blocking pattern as the
"structural" branch above — advisory only, feeds needs_review, never
triggers reconciliation (there is no mechanical fix for "reads unnatural").

commit_verse_tool re-verifies pyarud and sanitization itself before
writing — treat its "committed": false response as authoritative, not a
bug to route around.
"""

MODEL = ChatOpenAI(
    model="deepseek-chat",
    base_url="https://api.deepseek.com",
    api_key=os.environ.get("DEEPSEEK_API_KEY"),
    # DeepSeek is OpenAI-API-compatible, so ChatOpenAI + base_url override is
    # the standard way to route to it in LangChain. This is a reasonable,
    # commonly-used pattern, but confirm it against deepagents' current
    # model-handling behavior — if the harness wraps/validates models
    # against a provider allowlist internally, a plain ChatOpenAI pointed
    # elsewhere could behave unexpectedly. Test with one real call before
    # trusting a full batch run.
)

# ---------------------------------------------------------------------------
# Checkpointing
# ---------------------------------------------------------------------------
# Persists graph state (messages, files, todos) to a local SQLite file after
# every completed step. This is separate from BACKEND above: BACKEND is the
# agent's *virtual filesystem* (what ls/read_file/write_file see), while the
# checkpointer is LangGraph's own run history (what step you're on, what's
# been said so far) -- it's what lets you inspect or resume a run that was
# interrupted mid-flight, e.g. with Ctrl+C while waiting on a slow model call.
#
# check_same_thread=False is required because SqliteSaver may be touched from
# a different thread than the one that opened the connection in some
# LangGraph execution paths, even in this synchronous script.
#
# NOTE: requires langgraph-checkpoint-sqlite>=3.0.1 (earlier releases carry
# a SQL-injection vulnerability in the SQLite checkpointer, CVE-2025-67644,
# fixed in 3.0.1) -- pin this in requirements.txt.
CHECKPOINT_DB_PATH = PROJECT_ROOT / "checkpoints.sqlite"
checkpoint_conn = sqlite3.connect(str(CHECKPOINT_DB_PATH), check_same_thread=False)
checkpointer = SqliteSaver(checkpoint_conn)

agent = create_deep_agent(
    model=MODEL,
    tools=[
        verify_batch_tool,
        meter_schema_tool,
        verify_single_verse_tool,
        commit_verse_tool,
        log_unresolved_tool,
        sanitize_output_tool,
        reconcile_case_ending_tool,
    ],
    system_prompt=ORCHESTRATOR_SYSTEM_PROMPT,
    permissions=PERMISSIONS,
    backend=BACKEND,
    subagents=[DIACRITIZER_SUBAGENT, IRAB_SUBAGENT, NATURALNESS_CRITIC_SUBAGENT],
    checkpointer=checkpointer,
    interrupt_on={
        # Optional circuit-breaker (see design doc §6). Not a per-verse gate —
        # you explicitly declined that. This only pauses once per batch if
        # the disagreement rate looks anomalous. Delete this block entirely
        # if you'd rather have zero interrupts.
        "finalize_batch": {"mode": "approve", "condition": "disagreement_rate > 0.25"},
    },
)


if __name__ == "__main__":
    # Define absolute paths
    INPUT_PATH = PROJECT_ROOT / "dataset" / "inputs" / "batch_01.jsonl"

    if not INPUT_PATH.exists():
        print(f"[-] Input file not found at {INPUT_PATH}")
        print("[*] Please create the input file with your normalized verses first.")
        exit(1)

    # 1. Read input verses
    raw_verses = []
    with INPUT_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                raw_verses.append(json.loads(line))

    if not raw_verses:
        print("[-] No verses found in the input file.")
        exit(0)

    # 2. Group verses by meter to process them in coherent batches
    batches_by_meter = {}
    for v in raw_verses:
        meter = v.get("meter", "taweel")  # default fallback if not specified
        batches_by_meter.setdefault(meter, []).append(
            {"verse_id": v["verse_id"], "sadr": v["sadr"], "ajuz": v.get("ajuz", "")}
        )

    # 3. Invoke the DeepAgent orchestrator for each batch
    for meter, verses_batch in batches_by_meter.items():
        print(
            f"[*] Processing batch of {len(verses_batch)} verses for meter: '{meter}'..."
        )

        # The graph's default state schema only recognizes "messages"
        # (plus "files"/"todos"). Passing raw "input"/"verses"/"meter_name"
        # top-level keys here silently drops them -- the model never sees
        # the batch. So the verses + meter are embedded directly into the
        # user message content as JSON instead.
        verses_json = json.dumps(verses_batch, ensure_ascii=False, indent=2)
        user_message = (
            f"Diacritize the following batch of verses against the meter "
            f"'{meter}'.\n\n"
            f"verses (JSON array of {{verse_id, sadr, ajuz}} objects):\n"
            f"{verses_json}"
        )

        # Stable per-(input file, meter) thread_id: rerunning this script
        # against the same input file resumes the SAME checkpointed thread
        # instead of silently starting a fresh, unrelated one each time.
        thread_id = f"{INPUT_PATH.stem}:{meter}"
        run_config = {"configurable": {"thread_id": thread_id}}

        try:
            existing_state = agent.get_state(run_config)
        except Exception:
            existing_state = None

        try:
            if existing_state and existing_state.next:
                # A previous run was interrupted (e.g. Ctrl+C) partway
                # through this exact thread_id, with a pending next step.
                # Passing None as input resumes from the last completed
                # checkpoint instead of re-sending the original message and
                # starting the batch over.
                print(
                    f"[*] Resuming interrupted thread '{thread_id}' "
                    f"(next step: {existing_state.next})..."
                )
                response = agent.invoke(None, config=run_config)
            else:
                response = agent.invoke(
                    {"messages": [{"role": "user", "content": user_message}]},
                    config=run_config,
                )
            print(f"[+] Batch execution complete. Response status: {response}")
        except Exception as e:
            print(f"[-] Execution failed for batch under meter '{meter}': {str(e)}")
            print(
                f"    Checkpointed state for this run is saved under "
                f"thread_id='{thread_id}' in {CHECKPOINT_DB_PATH}. "
                f"Re-running this script will attempt to resume it."
            )
