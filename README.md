# taskrunner

A small, typed Python service that runs user-submitted tasks on a daily schedule and
enforces a per-user daily quota. It replaces the monolithic script in `Ticket.md` with a
modular design: typed models, pluggable action strategies, an executor that never
propagates task-level failures, and a clock-driven scheduler.

## Architecture

```
cli.py
  ├─ configure_logging()
  ├─ Task.from_dict() .......... validate raw dicts into frozen models
  ├─ QuotaManager(clock) ....... per-user, per-day counters (thread-safe)
  ├─ StrategyRegistry.default()  explicit action -> strategy map
  └─ TaskExecutor(registry, quota)
        └─ DailyScheduler(tasks, executor, clock)
              └─ for each task whose `at` matches now:
                    validate target
                    resolve strategy (unknown -> failed, no quota consumed)
                    quota.check -> skip + warn if exhausted
                    quota.consume
                    strategy.execute
                    -> ExecutionResult(status=ok|failed|skipped)
```

| Module | Responsibility |
| --- | --- |
| `models.py` | `Task` (frozen) and `ExecutionResult`; `Task.from_dict` validates input |
| `errors.py` | Domain exceptions (`InvalidTaskError`, `QuotaExceededError`, `StrategyNotFoundError`) |
| `quota.py` | Quota policy only; injected clock, `threading.Lock`, daily rollover |
| `strategies.py` | `ActionStrategy` ABC, built-in sync/backup/delete, explicit registry |
| `executor.py` | Fixed pipeline; logs and returns results, never raises task failures |
| `scheduler.py` | Minute-based dispatch, duplicate-minute guard, async-ready seam |
| `logging_config.py` | One `configure_logging()` entrypoint; optional JSON formatter |
| `cli.py` | Thin wiring of the modules above |

### Quota semantics

A slot is consumed **before** the strategy runs, matching the original script's
`executed += 1` behaviour, so a failed execution still counts against the user's daily
quota. Counts reset on the local calendar day reported by the injected clock. Unknown
users have a limit of zero and cannot execute.

## Usage

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e '.[dev]'

# Run one pass at the current time
python -m taskrunner.cli --once

# Demo without waiting for 12:00
python -m taskrunner.cli --once --now 12:00

# Run forever, polling every 60s
python -m taskrunner.cli

# Load custom tasks and quotas, emit JSON logs
python -m taskrunner.cli --once --now 12:00 \
  --tasks my_tasks.json --limits my_limits.json --json-logs
```

`my_limits.json` is an object such as `{"alice": 3, "bob": 5}`.

A task payload looks like:

```json
{"user": "alice", "time": "12:00", "action": "sync", "target": "/data/x",
 "params": {"dry_run": true}}
```

## Testing

```bash
ruff check .
mypy taskrunner
pytest --cov=taskrunner --cov-report=term-missing
```

Result at the time of writing: **51 tests passed**, `ruff` and `mypy --strict` clean,
**97% total coverage** (every module ≥93%; scheduler, quota, strategies, errors, and
logging at 100%).

## End-to-end smoke test (recorded)

Run after the final change set.

```bash
$ python -m taskrunner.cli --once --now 12:00
2026-11-23 16:05:08,369 INFO taskrunner.scheduler dispatching 3 task(s) due at 12:00
2026-11-23 16:05:08,369 INFO taskrunner.strategies sync source=/data/x
2026-11-23 16:05:08,369 INFO taskrunner.executor executed task=eca93ee3-... user=alice action=sync target=/data/x duration_ms=0.24
2026-11-23 16:05:08,370 INFO taskrunner.strategies backup source=/srv/y archive=/srv/y.tar
2026-11-23 16:05:08,370 INFO taskrunner.executor executed task=2927036f-... user=bob action=backup target=/srv/y duration_ms=0.14
2026-11-23 16:05:08,370 WARNING taskrunner.strategies delete path=/tmp/z recursive=False
2026-11-23 16:05:08,370 INFO taskrunner.executor executed task=d00c7fcc-... user=alice action=delete target=/tmp/z duration_ms=0.13
2026-11-23 16:05:08,370 INFO __main__ run complete tasks=3 (ok=3, failed=0, skipped=0)
exit=0
```

Failure paths — alice is given 4 tasks with a quota of 3 and bob submits an unknown
action:

```bash
$ python -m taskrunner.cli --once --now 12:00 --tasks smoke_failures.json
2026-11-23 16:05:08,732 INFO taskrunner.scheduler dispatching 6 task(s) due at 12:00
...
2026-11-23 16:05:08,735 WARNING taskrunner.executor quota exhausted task=8ce9501c-... user=alice action=sync; skipping
2026-11-23 16:05:08,735 ERROR taskrunner.executor unknown action task=defe9884-... user=bob: no strategy registered for action 'archive'
...
2026-11-23 16:05:08,736 INFO __main__ run complete tasks=6 (ok=4, failed=1, skipped=1)
exit=0
```

Both paths log traceable messages and exit cleanly with code 0.

## AI-assisted design notes

**Accepted**

- Injectable clock for quota and scheduler — makes every time-dependent path testable
  without `sleep`.
- Executor returns `ExecutionResult` instead of raising — lets the scheduler keep going
  after a failure, which the original script could not do.
- Explicit strategy registry with an ABC — satisfies the optional OOP extension without
  import-time magic.
- Frozen dataclass for `Task` and validated `from_dict` — removes `KeyError` surprises.
- Consuming quota before dispatch — preserves the original ticket's counting semantics.

**Rejected**

- Module-level mutable `users`/`tasks` dicts — untestable and not thread-safe.
- Logging inside `QuotaManager` — mixes policy with reporting; logging stays in the
  executor.
- Adding APScheduler or Celery for v1 — unnecessary dependencies for a minute-tick loop.
- Comparing times as strings — replaced with `datetime.time` hour/minute comparison.
- A full `asyncio` rewrite as part of the required scope — the optional async work is
  instead supported by an overridable dispatch seam (`_dispatch_async`) and documented
  below.
- Persisting to a database now — out of scope; the interfaces leave room for it.

## Scaling notes

- Persist tasks behind a repository interface; the scheduler then queries due tasks by
  time bucket instead of holding a list.
- Replace the tick loop with a queue/worker model (Celery/RQ/asyncio priority queue keyed
  by `at`) to distribute tens of thousands of daily tasks.
- Move quota accounting to an atomic Redis counter keyed by `user:date`, preserving the
  `QuotaManager` API behind an implementation swap.
- Reusable extraction points for other teams: `models.py` (task schema), `quota.py`
  (generic quota control), and `strategies.py` (plugin contract).
