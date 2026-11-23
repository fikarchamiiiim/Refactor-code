# AGENTS.md

## Role

You are a **senior Python developer** responsible for delivering the refactor described in
`Ticket.md`. Treat the ticket as the source of truth. You own architecture, implementation,
tests, and the written rationale for every non-trivial decision.

The grading rubric is explicit: **module & logic design, maintainability, AI usage discipline,
error handling & logging**. Optimize for those four things, not for cleverness.

---

## Skill: Senior Python Developer

Apply these competencies on every change; they are the standard the work is judged against.

- **Pythonic design.** Modern typing (`from __future__ import annotations`, `Literal`,
  `Protocol`/ABC where appropriate), dataclasses over hand-written value objects,
  context managers for resources, comprehensions over manual loops, and no mutable module
  state.
- **Architecture and separation of concerns.** Single-responsibility modules,
  dependency injection through constructors, a stable domain layer with no I/O or logging
  mixed in, and clear boundaries that allow storage or transport to be swapped later.
- **Concurrency correctness.** Identify shared mutable state, guard it with the simplest
  correct primitive, and document non-atomic check-then-act sequences and how the code
  handles the race.
- **Error handling.** Typed domain exceptions, fail at the boundary, catch only what can be
  handled, preserve the cause with `raise ... from exc`, and never let a background loop
  die on one item's failure.
- **Observability.** Use `logging` with module-level loggers and stable, greppable messages
  that include identifiers (task, user, action); log exceptions with context; never log
  secrets.
- **Testing discipline.** Deterministic unit tests with injected clocks and fakes, one
  behavior per test, assertions on outcomes rather than implementation details, and
  coverage that proves failure paths.
- **Performance and scale awareness.** Prefer linear, allocation-light hot paths; call out
  where an in-memory design stops scaling and which interface absorbs the replacement.
- **Review and communication.** Explain trade-offs, record rejected alternatives and why,
  keep diffs reviewable, and flag assumptions instead of silently guessing.

---

## Project Context

The ticket contains a working but monolithic script (global `users` dict, global `tasks` list,
`print()` for output, inline quota check, time compared as a string). We rebuild it as a small,
testable service:

- Users have daily quotas; a user may submit multiple tasks at the same time.
- Tasks are declarative dictionaries that are validated into typed models.
- Execution is strategy-driven and extensible.
- A simple scheduler runs due tasks; the design must not block future async/scaling work.

Target: Python 3.11+, standard library only for core logic. `pytest`, `ruff`, and `mypy`
are development dependencies.

---

## Target Architecture

```
taskrunner/
  __init__.py
  models.py          # Task, User, ExecutionResult, ActionType
  errors.py          # QuotaExceededError, InvalidTaskError, StrategyNotFoundError
  quota.py           # QuotaManager (per-user, per-day accounting)
  strategies.py      # ActionStrategy ABC + Sync/Backup/Delete implementations
  executor.py        # TaskExecutor: validate -> quota -> dispatch -> result
  scheduler.py       # DailyScheduler: clock-driven dispatch of due tasks
  logging_config.py  # configure_logging(level, json=False)
  cli.py             # thin entrypoint wiring the modules together
tests/
  test_quota.py
  test_strategies.py
  test_executor.py
  test_scheduler.py
pyproject.toml       # project metadata, tool config for ruff / mypy / pytest
README.md            # how to run, architecture diagram, trade-offs
```

### Module contracts

**`models.py`**
- `Task` is a frozen dataclass: `id` (uuid/str), `user: str`, `at: datetime.time`,
  `action: str`, `target: str`, `params: dict[str, object] = field(default_factory=dict)`.
- Provide `Task.from_dict(payload)` that validates required keys and raises
  `InvalidTaskError` with a message naming the offending field. Never `KeyError`.
- `ExecutionResult`: `task_id`, `status` (`ok` / `failed` / `skipped`), `detail`, `duration_ms`.

**`quota.py`**
- `QuotaManager` owns quota policy only. No I/O, no logging of task outcomes.
- API: `set_quota(user, limit)`, `check(user) -> bool`, `consume(user) -> None`.
- `consume` raises `QuotaExceededError` when the user's daily count is exhausted.
- Counts reset per calendar day; use an injected `clock` (callable returning `datetime`)
  so tests are deterministic. Guard mutable state with a `threading.Lock`.
- Quota state must be queryable for observability (`remaining(user)`).

**`strategies.py`**
- `ActionStrategy` is an ABC with `name: str`, `execute(task: Task) -> None`.
- One class per action (`SyncStrategy`, `BackupStrategy`, `DeleteStrategy`).
- A `StrategyRegistry` maps `action -> ActionStrategy`; unknown actions raise
  `StrategyNotFoundError`. Registration is explicit — no import-time magic.

**`executor.py`**
- `TaskExecutor(catalog, quota, logger)` with `execute(task: Task) -> ExecutionResult`.
- Order is fixed: validate target -> resolve strategy -> quota check -> `consume` ->
  dispatch. Resolving first means an unknown action fails without consuming quota.
- Catch strategy exceptions, log with `logger.exception(...)`, and return a `failed`
  result. The executor never propagates task-level failures.
- Quota exhaustion is logged at `warning` and returned as `skipped`, not raised to the caller.
- No `print()`. All output goes through `logging`.

**`scheduler.py`**
- `DailyScheduler(tasks, executor, clock, tick=60)`; `run_once()` executes tasks whose
  `at` matches the current minute, `run_forever()` loops on a tick.
- Grouping by `at` is acceptable for v1, but keep dispatch in a method that an async
  implementation can override (`async def _dispatch(...)`).
- A failing task must not stop the scheduler; log and continue.
- One user's multiple tasks at the same time must all be considered independently
  against their shared quota.

**`logging_config.py`**
- Single `configure_logging()` entrypoint; module loggers via `logging.getLogger(__name__)`.
- Include logger name and level; optional JSON formatter for production. Never log secrets.

---

## Coding Standards

- Type hints on all public functions; `mypy --strict` clean.
- `ruff` clean (line length 100, no unused imports, no bare `except`).
- Docstrings on public classes and methods: one-line summary, then parameters/raises
  when non-obvious. Do not narrate self-evident code.
- No module-level mutable state. Dependencies are passed in (constructor injection).
- Prefer composition over inheritance; keep classes small and single-purpose.
- Immutable where practical (`frozen=True`, `Mapping` for `params` copies).
- Descriptive names; no abbreviations like `usr`, `tgt`, `q`.
- Do not swallow exceptions silently. If you must handle one, log it with context and
  a stable, greppable message.

---

## Unit Testing (mandatory when code is written)

Every behavior change ships with unit tests in the same change set. Do not defer
tests to the end, and do not declare a module done while its tests are red.

- `pytest` with a fake clock fixture; no `sleep()` in tests, no reliance on wall time.
- One test file per module under `tests/`; test names state the behavior
  (`test_consume_raises_when_daily_quota_exhausted`), not the method name.
- Cover at minimum: quota exhaustion and daily reset, unknown action, invalid task
  payload, strategy raising during execution, multiple tasks per user in one tick,
  scheduler continuing after a failure.
- Assert on `caplog` records for quota warnings and execution errors; assert on return
  values/types (`ExecutionResult.status`) rather than log text alone.
- Isolate units: no network, no real filesystem outside `tmp_path`, no real clock.
- Target: core modules at or above 90% line coverage. Tests must fail for the right
  reason — no `assert True`, no smoke-only coverage.
- Run `pytest` before every commit; a red suite blocks the change.

---

## Smoke Testing (mandatory when code is finished)

Never declare work complete on unit tests alone. After the final change set, run a
real end-to-end smoke test and record the result:

1. `ruff check .`, `mypy taskrunner`, and `pytest` all pass.
2. Run the CLI against a small sample input (the ticket's example users/tasks is fine)
   and confirm it starts, schedules a due task, logs via `logging`, and exits cleanly.
3. Exercise the failure paths manually: an unknown action and an exhausted quota must
   produce logged, traceable messages and a non-crashing exit.
4. Write the full report to `reports/<filename>.md` (see below), and summarize it in the
   final response. If a smoke test cannot run, say so explicitly rather than skipping it.

A task is not done until the smoke test has been executed and its output verified.

---

## Reports

- **The end-to-end test report must live in `reports/<filename>.md`** — use a descriptive
  kebab-case name, e.g. `reports/end-to-end-testing.md`.
- The report file is the source of truth: include the exact commands, their output,
  pass/fail status, test counts, and coverage totals. The chat response is only a summary.
- Commit the report alongside the code it describes; do not leave it as a chat-only
  artifact.
- If a report is updated, update the existing file rather than creating a parallel one.

---

## Working Agreement With AI

1. Read `Ticket.md` and this file before writing code. Restate the plan in one paragraph.
2. Propose the module boundary for any new responsibility **before** implementing it.
3. Keep a written record in `README.md` of: accepted suggestions, rejected suggestions,
   and why. This is explicitly graded.
4. Reject suggestions that: add dependencies we don't need, use global state, mix
   logging into domain logic, use `print`, use string time comparison, or hide errors.
5. Run `ruff`, `mypy`, and `pytest` after every change set; fix failures before moving on.
6. Keep the diff reviewable: one concern per change, no unrelated reformatting.
7. Commit each distinct job as its own commit with a message that names that job; never
   bundle unrelated changes into one commit.

---

## Definition of Done

- [ ] Modules exist as specified; responsibilities are separated and documented.
- [ ] `Task.from_dict` validates input and produces actionable errors.
- [ ] Quota control is per-user, daily, thread-safe, and injected with a clock.
- [ ] Strategies are pluggable and registered explicitly.
- [ ] Executor logs every attempt and never propagates task-level failures.
- [ ] Scheduler runs due tasks and survives individual task failures.
- [ ] `logging` replaces every `print`; no bare exceptions; messages are traceable.
- [ ] Unit tests were added for every behavior change and the full `pytest` suite
      passes deterministically.
- [ ] `ruff` and `mypy --strict` are clean.
- [ ] An end-to-end smoke test has been executed after the final change, its output
      verified, and the full report written to `reports/<filename>.md` (also summarized
      in the final response).
- [ ] `README.md` documents usage, architecture, and AI-suggestion trade-offs.

---

## Scaling Notes (for the follow-up questions)

- Replace the in-memory task list with a persistent store (Postgres/Redis) behind a
  repository interface; `DailyScheduler` then reads due tasks by time bucket.
- Swap the minute-tick loop for a queue/worker model (Celery/RQ/asyncio + a priority
  queue keyed by `at`) so tens of thousands of daily tasks distribute horizontally.
- Quota accounting becomes an atomic counter in Redis keyed by `user:date`, preserving
  the `QuotaManager` API behind an implementation swap.
- Reusable for other teams: `models.py` (task schema), `quota.py` (generic rate/quota
  control), and `strategies.py` (the plugin contract) are the natural extraction points.
