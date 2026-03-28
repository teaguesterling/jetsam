# Jetsam Integration with Patterns for Toolcraft

*Reference prompt for integrating jetsam with the design patterns from the Ma experimental program.*

## Before doing anything

Read these files in the judgementalmonad.com repo:

1. `blog/patterns/07-the-mode-controller.md` — **Primary.** Jetsam is the natural home for workflow-level mode transitions. Save points, mode state, transitions triggered by failure patterns.
2. `blog/patterns/04-write-execute-separation.md` — Jetsam's save/sync/finish workflow maps to the write/execute separation. `jetsam save` is an auditable checkpoint; `blq run test` is sandboxed execution.
3. `blog/patterns/08-the-coach.md` — Jetsam provides git state awareness: what's changed, what's committed, what needs attention. The Coach uses this for stale-context detection.
4. `blog/patterns/01-the-quartermaster.md` — The Quartermaster's kit selection can trigger jetsam workflow state (start a plan, set the mode, configure save behavior).

Also read:
5. `blog/patterns/05-sandbox-specifications.md` — Sandbox specs for commands that jetsam dispatches (via blq).
6. `experiments/pilot-findings.md` — Sections 8-11 for the evidence.
7. `blog/fuel/04-the-failure-driven-controller.md` — The Ratchet Fuel post on the mode controller, which jetsam can implement.

## Jetsam's role in the pattern ecosystem

Jetsam manages workflow state: git branches, save points, plans, sync, finish. It's the coordination layer for development workflow — System 2 in Beer's VSM.

The patterns extend jetsam's role from coordination (routing messages, enforcing protocols) to **control** (monitoring whether the current configuration is working and changing it when it isn't). This is the System 3 function that the Ma framework identifies as missing from current agent systems.

```
Jetsam today (System 2 — coordination):
  start → save → sync → finish
  Each step follows the same protocol regardless of how the work is going.

Jetsam with Mode Controller (System 2 + System 3 — coordination + control):
  start(mode=debug) → [failure detected] → switch(mode=implement) → save →
  [tests passing] → switch(mode=review) → finish
  Mode transitions respond to what's happening.
```

## What jetsam should gain

### 1. Mode state (for the Mode Controller)

Jetsam already tracks workflow state (branch, plan, changes). Add mode as part of the state:

```python
# jetsam status output, extended with mode
{
    "branch": "feature/fix-auth",
    "plan": "Fix authentication timeout bug",
    "mode": "implement",        # NEW: current mode
    "changes": 3,
    "tests_passing": true,
    "turns_in_mode": 12,        # NEW: how long in this mode
    "failure_count": 0,         # NEW: failures since last mode switch
}
```

Mode transitions are jetsam commands:

```bash
jetsam mode debug      # switch to debug mode (read-only + tests)
jetsam mode implement  # switch to implement mode (edit + test)
jetsam mode review     # switch to review mode (read-only)
```

Each mode change:
- Updates jetsam's state
- Signals the MCP server to reconfigure available tools (via the coordinator)
- Logs the transition with reason and counters

### 2. Failure-triggered transitions

The Mode Controller watches jetsam's state and triggers transitions:

```python
# In a PostToolUse hook or jetsam's own monitoring
if jetsam.status().failure_count > 3:
    jetsam.mode("debug")  # too many failures, step back to diagnosis

if jetsam.status().turns_in_mode > 20 and jetsam.status().mode == "debug":
    jetsam.mode("implement")  # spent too long diagnosing, try fixing

if jetsam.status().tests_passing and jetsam.status().mode == "implement":
    jetsam.mode("review")  # implementation done, review before finishing
```

These are specified rules — counters and thresholds, not trained judgment. They can be configured per task type:

```toml
[mode_controller]
max_failures_before_debug = 3
max_turns_in_debug = 20
auto_review_on_tests_passing = true
```

### 3. Save points as checkpoints

Jetsam's `save` command is already an auditable checkpoint. The Mode Controller can trigger automatic saves at mode transitions:

```
debug → implement:  jetsam save "diagnosis complete, starting implementation"
implement → review: jetsam save "implementation complete, starting review"
review → finish:    jetsam finish
```

Each save is a git commit with a message that records the mode transition. The full history shows the agent's workflow: when it diagnosed, when it started implementing, when it reviewed. This is the Write/Execute Separation pattern applied to workflow: every phase transition is a checkpoint.

### 4. Protected paths per mode

Jetsam can enforce the test boundary from the Mode Controller pattern:

```toml
[modes.implement]
writable = ["src/"]
readonly = ["tests/"]

[modes.test_dev]
writable = ["tests/"]
readonly = ["src/"]

[modes.debug]
writable = []         # read-only everything
readonly = ["src/", "tests/"]

[modes.review]
writable = []
readonly = ["src/", "tests/"]
```

Jetsam already knows about file paths (it manages git state). Adding path protection per mode is a natural extension. When the agent tries to edit a file outside the mode's writable set, jetsam refuses — or signals the Coach to suggest switching modes first.

### 5. Git state for the Coach

Jetsam provides the git awareness the Coach needs for stale-context detection:

```bash
# What changed since the agent last read a file?
jetsam diff --since-read src/auth.py
# Returns: diff if file changed since last file_read("src/auth.py")

# What's been modified but not tested?
jetsam status --untested
# Returns: files edited since last test run
```

These aren't new jetsam commands — they're views over jetsam's existing state + Fledgling's conversation analytics. The Coach queries both.

## What jetsam should NOT do

- **Run tests or builds.** That's blq. Jetsam manages workflow state; blq manages execution.
- **Analyze code structure.** That's Fledgling. Jetsam knows about files and git; Fledgling knows about code.
- **Select tools.** That's the Quartermaster. Jetsam manages the mode state that determines which tools are active, but the tool registry configuration is the Harness's job.
- **Generate coaching suggestions.** That's the Coach hook. Jetsam provides the data (git state, mode state) but doesn't compose suggestions.

## The three-tool architecture

```
Fledgling (level 0)     blq (level 1-2)          Jetsam (level 1-2)
reads code intelligence  captures build/test      manages workflow state
├─ CodeStructure        ├─ run(command)           ├─ save/sync/finish
├─ FindDefinitions      ├─ events/errors          ├─ mode transitions
├─ ChatToolUsage        ├─ sandbox enforcement    ├─ protected paths
└─ coaching queries     └─ test output            └─ git state

          ↓ feeds                ↓ feeds               ↓ feeds
       ┌──────────────────────────────────────────────────────┐
       │                    Coordinator                        │
       │  (Claude Code hooks / Harness-level logic)            │
       │  - Quartermaster: select kit at task start            │
       │  - Mode Controller: switch modes on failure patterns  │
       │  - Coach: inject suggestions from Fledgling queries   │
       │  - Sandbox: enforce blq specs on execution            │
       └──────────────────────────────────────────────────────┘
```

Each tool stays at its natural level. Fledgling reads. blq executes and captures. Jetsam manages state. The Coordinator composes them — and the Coordinator is specified (hooks with counters and thresholds, not an LLM making decisions).

## Priority for jetsam

1. **Mode state** — add `mode` to jetsam's status, `jetsam mode <name>` command
2. **Auto-save on mode transitions** — checkpoint at every mode switch
3. **Protected paths per mode** — writable/readonly sets per mode
4. **Failure counters** — track failures_since_mode_switch, turns_in_mode
5. **Mode transition rules** — configurable thresholds for auto-transitions

## Key experimental findings relevant to jetsam

1. **The test boundary matters.** In our experiments, the agent could modify both source and test files when both were writable. The Write/Execute Separation pattern prevents this by making tests read-only during implementation. Jetsam's protected paths enforce this structurally.

2. **Mode transitions should be cheap.** Our experiment showed that tool reconfiguration overhead matters — the Mode Controller should switch modes without a full session restart. Jetsam's mode command should update state and signal the MCP server, not create a new conversation.

3. **Failure-driven control is better than time-driven.** Our experiments didn't test the Mode Controller directly, but the data shows clear failure patterns (Haiku spinning for 50 turns, Opus over-analyzing) that specified counters would catch. The thresholds should be tuned from experimental data.

4. **The strategy instruction is mode-dependent.** Debug mode needs "identify all failures before fixing." Implementation mode might need "batch your edits by file." Review mode needs "read everything before forming an opinion." Each mode has its own principle — and the principle's value is model-dependent.
