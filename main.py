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

CHANGE (A4): agent/checkpointer construction used to happen at MODULE
IMPORT time, which meant merely importing this module (from a test, a
notebook, a future second entrypoint) opened a real sqlite3 connection to
checkpoints.sqlite and ran the integrity_check query as a side effect.
That construction now lives in build_agent(), called from main() under the
__main__ guard, so importing this module has no side effects.

CHANGE (A4): the resume path (agent.invoke(None, ...)) previously shared
the exact same broad except-Exception branch as a fresh invoke, printing
an identical generic message either way. It now has its own except branch
that names the corruption possibility explicitly and suggests a concrete
next step (fresh thread_id) rather than leaving the operator to guess
whether a resume failure is an ordinary run-time error or a checkpoint
integrity problem.
"""

import json
import pathlib
import os
import sqlite3
import sys

from deepagents import create_deep_agent, FilesystemPermission
from deepagents.backends import CompositeBackend, StateBackend, FilesystemBackend
from backends.model_provider import get_model
from langgraph.checkpoint.sqlite import SqliteSaver

from tools.prosody_tools import (
    verify_batch_tool,
    meter_schema_tool,
    verify_single_verse_tool,
)
from tools.dataset_tools import commit_verse_tool, log_unresolved_tool
from tools.sanitization_tools import sanitize_output_tool
from tools.reconciliation_tools import reconcile_case_ending_tool
from tools.context_tools import summarize_correction_report_tool
from tools.tracing import trace_run
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
    # Deny agents from altering their own instruction/guideline documents
    FilesystemPermission(
        paths=["/skills/**"], operations=["write", "edit", "delete"], mode="deny"
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
        "/skills/": FilesystemBackend(
            root_dir=str(PROJECT_ROOT / "skills"), virtual_mode=True
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

--- Context discipline across correction passes ---

verify_batch_tool's correction_report is a complete, per-foot diagnostic
text. Do not let it accumulate unpruned in your own reasoning across
passes — that is the single largest token-cost driver in this system.
Concretely:

  1. After each verify_batch_tool call, write its full correction_report to
     /workspace/pass_{{n}}_report.json (n = current pass number, starting
     at 1) instead of quoting the full text back into your own reasoning.
     Use summarize_correction_report_tool on the returned poem_result_json
     to get a terse "verse_id: score" summary for your OWN bookkeeping of
     which verses remain broken pass over pass — that summary, not the
     full report, is what should persist in your own context.
  2. When dispatching the diacritizer subagent for a given pass, hand it
     ONLY that pass's fresh correction_report (read from the file you just
     wrote, or the tool's return value directly) plus the verse's original
     input text. Never re-paste a prior pass's correction_report, and
     never re-include a verse's prior-pass rejected draft text — it already
     failed verify_batch_tool and carries no diagnostic value the fresh
     report doesn't already contain better.
  3. Locked verses need no report at all in any pass — they are not
     resubmitted (see Locking rule above), so nothing about them belongs
     in a dispatch to the diacritizer.

--- Handling a pyarud/إعراب disagreement (two-step, in this order) ---

After a verse is locked, dispatch it to BOTH irab_checker and
naturalness_critic (advisory, non-gating, via task tool).

If irab_checker returns flag=true with fix_type="case_ending_swap":
  1. This is NOT automatically poetic license — attempt reconciliation
     FIRST. Call reconcile_case_ending_tool with the word_index and
     target_harakah it proposed (target_harakah may now be a tanwin mark —
     fathatayn/dammatayn/kasratayn — in addition to the plain short
     vowels). This performs a mechanical vowel/tanwin swap, which cannot
     change the metrical pattern.
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
bug to route around. A "duplicate": true response means this exact verse
(or an identical text under a different verse_id) was already committed —
treat that as already handled, not as a failure to retry.
"""


def build_agent():
    """Construct the checkpointer and the deep agent. Called from main()
    under the __main__ guard so that merely importing this module (e.g.
    from a test) has no side effects -- no sqlite connection is opened and
    no model client is constructed at import time (A4)."""

    # Instantiates model with providers based on environment setup with retry safety
    model = get_model()

    # -----------------------------------------------------------------
    # Checkpointing
    # -----------------------------------------------------------------
    # Persists graph state (messages, files, todos) to a local SQLite file
    # after every completed step. This is separate from BACKEND above:
    # BACKEND is the agent's *virtual filesystem* (what ls/read_file/
    # write_file see), while the checkpointer is LangGraph's own run
    # history (what step you're on, what's been said so far) -- it's what
    # lets you inspect or resume a run that was interrupted mid-flight,
    # e.g. with Ctrl+C while waiting on a slow model call.
    #
    # check_same_thread=False is required because SqliteSaver may be
    # touched from a different thread than the one that opened the
    # connection in some LangGraph execution paths, even in this
    # synchronous script.
    #
    # NOTE: requires langgraph-checkpoint-sqlite>=3.0.1 (earlier releases
    # carry a SQL-injection vulnerability in the SQLite checkpointer,
    # CVE-2025-67644, fixed in 3.0.1) -- pin this in requirements.txt.
    checkpoint_db_path = PROJECT_ROOT / "checkpoints.sqlite"
    checkpoint_conn = sqlite3.connect(str(checkpoint_db_path), check_same_thread=False)

    # Optimization Pragma Settings (PRAGMA setup runs prior to SqliteSaver)
    checkpoint_conn.execute("PRAGMA busy_timeout = 30000")
    checkpoint_conn.execute("PRAGMA synchronous = NORMAL")

    # Startup Diagnostics: database file integrity check
    try:
        cursor = checkpoint_conn.cursor()
        cursor.execute("PRAGMA integrity_check")
        integrity_result = cursor.fetchone()[0]
        if integrity_result != "ok":
            print(
                f"[!] Warning: Checkpoint database corrupted. PRAGMA integrity_check returned: {integrity_result}"
            )
    except Exception as exc:
        print(f"[-] Pre-run checkpoint diagnostic failed: {exc}")

    checkpointer = SqliteSaver(checkpoint_conn)

    # -----------------------------------------------------------------
    # Subagent skill assignment
    # -----------------------------------------------------------------
    # Inject skill directory permissions dynamically into subagent dict
    # structures so that deepagents' graph creation middleware exposes
    # them to the agents.
    DIACRITIZER_SUBAGENT["skills"] = ["/skills/"]
    IRAB_SUBAGENT["skills"] = ["/skills/"]

    agent = create_deep_agent(
        model=model,
        tools=[
            verify_batch_tool,
            meter_schema_tool,
            verify_single_verse_tool,
            commit_verse_tool,
            log_unresolved_tool,
            sanitize_output_tool,
            reconcile_case_ending_tool,
            summarize_correction_report_tool,
        ],
        system_prompt=ORCHESTRATOR_SYSTEM_PROMPT,
        permissions=PERMISSIONS,
        backend=BACKEND,
        subagents=[DIACRITIZER_SUBAGENT, IRAB_SUBAGENT, NATURALNESS_CRITIC_SUBAGENT],
        checkpointer=checkpointer,
        skills=["/skills/"],
        interrupt_on={
            # Optional circuit-breaker (see design doc §6). Not a per-verse
            # gate — you explicitly declined that. This only pauses once
            # per batch if the disagreement rate looks anomalous. Delete
            # this block entirely if you'd rather have zero interrupts.
            "finalize_batch": {
                "mode": "approve",
                "condition": "disagreement_rate > 0.25",
            },
        },
    )

    return agent, checkpoint_conn, checkpoint_db_path


def main() -> None:
    agent, checkpoint_conn, checkpoint_db_path = build_agent()

    try:
        # Determine the input paths dynamically
        inputs_dir = PROJECT_ROOT / "dataset" / "inputs"
        jsonl_files = []

        # Check if input file(s) are passed as a command-line argument
        if len(sys.argv) > 1:
            arg = sys.argv[1]
            if arg == "--all":
                jsonl_files = sorted(list(inputs_dir.glob("*.jsonl")))
                print(
                    f"[*] Processing ALL {len(jsonl_files)} input files in dataset/inputs/."
                )
            else:
                arg_path = pathlib.Path(arg)
                if arg_path.is_absolute() or arg_path.exists():
                    jsonl_files = [arg_path]
                else:
                    # Check if it's a filename inside the inputs directory
                    specific_file = inputs_dir / arg_path.name
                    if specific_file.exists():
                        jsonl_files = [specific_file]
                    else:
                        print(f"[-] Input file not found: {arg}")
                        if inputs_dir.exists():
                            print("[*] Available input files in dataset/inputs/:")
                            for f in sorted(inputs_dir.glob("*.jsonl")):
                                print(f"    - {f.name}")
                        return
        else:
            # No argument provided; list and default to all files
            jsonl_files = sorted(list(inputs_dir.glob("*.jsonl")))
            if jsonl_files:
                print(
                    f"[*] No input file specified. Found {len(jsonl_files)} input files in dataset/inputs/."
                )
                print(
                    "[*] Defaulting to processing ALL files. To run a single file, pass its name as an argument:"
                )
                print("    python main.py <filename.jsonl>")
                print("[*] Starting the processing loop...")
            else:
                print(f"[-] No .jsonl files found in {inputs_dir}")
                return

        # Loop through all resolved input files
        for input_path in jsonl_files:
            print(f"\n" + "=" * 60)
            print(f"[*] Reading inputs from: {input_path.name}")
            print("=" * 60)

            # 1. Read input verses
            raw_verses = []
            with input_path.open("r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        raw_verses.append(json.loads(line))

            if not raw_verses:
                print(f"[-] No verses found in {input_path.name}. Skipping.")
                continue

            # 2. Group verses by meter to process them in coherent batches
            batches_by_meter = {}
            for v in raw_verses:
                meter = v.get("meter", "taweel")  # default fallback if not specified
                batches_by_meter.setdefault(meter, []).append(
                    {
                        "verse_id": v["verse_id"],
                        "sadr": v["sadr"],
                        "ajuz": v.get("ajuz", ""),
                    }
                )

            # 3. Invoke the DeepAgent orchestrator for each batch
            for meter, verses_batch in batches_by_meter.items():
                print(
                    f"[*] Processing batch of {len(verses_batch)} verses for meter: '{meter}' from '{input_path.name}'..."
                )

                # The graph's default state schema only recognizes "messages"
                # (plus "files"/"todos"). Passing raw "input"/"verses"/
                # "meter_name" top-level keys here silently drops them -- the
                # model never sees the batch. So the verses + meter are
                # embedded directly into the user message content as JSON
                # instead.
                verses_json = json.dumps(verses_batch, ensure_ascii=False, indent=2)
                user_message = (
                    f"Diacritize the following batch of verses against the meter "
                    f"'{meter}'.\n\n"
                    f"verses (JSON array of {{verse_id, sadr, ajuz}} objects):\n"
                    f"{verses_json}"
                )

                # Stable per-(input file, meter) thread_id: rerunning this
                # script resumes the SAME checkpointed thread instead of
                # silently starting a fresh, unrelated one each time.
                thread_id = f"{input_path.stem}:{meter}"
                run_config = {"configurable": {"thread_id": thread_id}}

                try:
                    existing_state = agent.get_state(run_config)
                except Exception:
                    existing_state = None

                # trace_run() opens a fresh, unique trace_id for THIS invoke
                # attempt (deliberately NOT the same thing as the LangGraph
                # thread_id above, which stays stable across resumes on
                # purpose — see tools/tracing.py's module docstring for why).
                # The trace_id lets you inspect token usage / latency per
                # agent (orchestrator, diacritizer, irab_checker,
                # naturalness_critic) for this specific attempt, even if the
                # same thread_id gets resumed multiple times.
                with trace_run(label=meter, langgraph_thread_id=thread_id) as trace:
                    traced_config = {**run_config, "callbacks": [trace.callback]}
                    print(
                        f"[*] trace_id='{trace.trace_id}' "
                        f"(inspect with: python -m tools.trace_report --trace {trace.trace_id})"
                    )

                    try:
                        if existing_state and existing_state.next:
                            # A previous run was interrupted (e.g. Ctrl+C)
                            # partway through this exact thread_id, with a
                            # pending next step. Passing None as input resumes
                            # from the last completed checkpoint instead of
                            # re-sending the original message and starting the
                            # batch over.
                            print(
                                f"[*] Resuming interrupted thread '{thread_id}' "
                                f"(next step: {existing_state.next})..."
                            )
                            try:
                                response = agent.invoke(None, config=traced_config)
                            except Exception as resume_exc:
                                # A4: distinct branch from the fresh-invoke
                                # path below -- a failure HERE specifically
                                # means the checkpoint we tried to resume from
                                # may itself be the problem, not just an
                                # ordinary mid-run LLM/tool error. Name that
                                # possibility explicitly rather than printing
                                # the same generic message either way.
                                print(
                                    f"[-] Resume failed for thread '{thread_id}': {resume_exc}"
                                )
                                print(
                                    "    The checkpoint may be corrupted or its state "
                                    "incompatible with a fresh run. Run `PRAGMA "
                                    f"integrity_check` against {checkpoint_db_path} to "
                                    "confirm, or re-run with a modified thread_id "
                                    "(e.g. append a suffix to input_path.stem) to "
                                    "reprocess this batch from scratch instead of "
                                    "resuming."
                                )
                                raise
                        else:
                            response = agent.invoke(
                                {
                                    "messages": [
                                        {"role": "user", "content": user_message}
                                    ]
                                },
                                config=traced_config,
                            )
                        print(
                            f"[+] Batch execution complete. Response status: {response}"
                        )
                    except Exception as e:
                        print(
                            f"[-] Execution failed for batch under meter '{meter}': {str(e)}"
                        )
                        print(
                            f"    Checkpointed state for this run is saved under "
                            f"thread_id='{thread_id}' in {checkpoint_db_path}. "
                            f"Re-running this script will attempt to resume it."
                        )
                    finally:
                        print(
                            f"[*] trace summary: python -m tools.trace_report --trace {trace.trace_id}"
                        )
    finally:
        # Guarantee resources are cleaned up and SQLite is not left with
        # dangling file descriptors
        print("[*] Terminating run. Closing checkpoint DB stream connection...")
        checkpoint_conn.close()


if __name__ == "__main__":
    main()
