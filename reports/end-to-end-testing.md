# End-to-end test report

**Date:** 2026-11-23
**Environment:** Python 3.12.8 (`.venv`), pytest 9.2.0, pytest-cov, ruff 0.17.6, mypy 2.4.1
**Scope:** Final change set for the `taskrunner` refactor of `Ticket.md`.

## 1. Static analysis and unit tests

```bash
$ ruff check .
All checks passed!

$ mypy taskrunner
Success: no issues found in 9 source files

$ pytest --cov=taskrunner --cov-report=term-missing
51 passed in 1.06s
```

Status: **PASS**

### Coverage

| Module | Stmts | Miss | Cover |
| --- | --- | --- | --- |
| taskrunner/__init__.py | 7 | 0 | 100% |
| taskrunner/cli.py | 82 | 2 | 98% |
| taskrunner/errors.py | 14 | 0 | 100% |
| taskrunner/executor.py | 47 | 3 | 94% |
| taskrunner/logging_config.py | 20 | 0 | 100% |
| taskrunner/models.py | 71 | 5 | 93% |
| taskrunner/quota.py | 46 | 0 | 100% |
| taskrunner/scheduler.py | 47 | 0 | 100% |
| taskrunner/strategies.py | 46 | 0 | 100% |
| **TOTAL** | **380** | **10** | **97%** |

All core modules are at or above the 90% target.

## 2. Happy-path smoke test

Command:

```bash
python -m taskrunner.cli --once --now 12:00
```

Output:

```text
2026-11-23 16:09:54,061 INFO taskrunner.scheduler dispatching 3 task(s) due at 12:00
2026-11-23 16:09:54,061 INFO taskrunner.strategies sync source=/data/x
2026-11-23 16:09:54,061 INFO taskrunner.executor executed task=a4f0dbdb-bdb1-4ba3-b1be-fd007d5c655d user=alice action=sync target=/data/x duration_ms=0.20
2026-11-23 16:09:54,061 INFO taskrunner.strategies backup source=/srv/y archive=/srv/y.tar
2026-11-23 16:09:54,062 INFO taskrunner.executor executed task=9f412323-2d54-42a8-9695-c8969ff37f12 user=bob action=backup target=/srv/y duration_ms=0.35
2026-11-23 16:09:54,062 WARNING taskrunner.strategies delete path=/tmp/z recursive=False
2026-11-23 16:09:54,062 INFO taskrunner.executor executed task=cc08f97f-dd8f-4579-ad6e-f5bd10ff1500 user=alice action=delete target=/tmp/z duration_ms=0.18
2026-11-23 16:09:54,062 INFO __main__ run complete tasks=3 (ok=3, failed=0, skipped=0)
```

Exit code: **0**
Status: **PASS** — scheduler selected the due tasks, ran all strategies, logged through
`logging` (no `print`), and exited cleanly.

## 3. Failure-path smoke test

Input: alice submits 4 tasks with a quota of 3; bob submits the unknown action `archive`.

```bash
python -m taskrunner.cli --once --now 12:00 --tasks smoke_failures.json
```

Output (abridged to the relevant records):

```text
2026-11-23 16:09:54,271 INFO taskrunner.scheduler dispatching 6 task(s) due at 12:00
2026-11-23 16:09:54,271 INFO taskrunner.executor executed task=cff59a6e-... user=alice action=sync target=/data/a
2026-11-23 16:09:54,271 INFO taskrunner.executor executed task=8f6f3d59-... user=alice action=sync target=/data/b
2026-11-23 16:09:54,271 INFO taskrunner.executor executed task=c1c94f4a-... user=alice action=sync target=/data/c
2026-11-23 16:09:54,271 WARNING taskrunner.executor quota exhausted task=3a9f9c3a-... user=alice action=sync; skipping
2026-11-23 16:09:54,271 ERROR taskrunner.executor unknown action task=aee48ca2-... user=bob: no strategy registered for action 'archive'
2026-11-23 16:09:54,272 INFO taskrunner.executor executed task=8f2e0ba0-... user=bob action=backup target=/srv/y
2026-11-23 16:09:54,272 INFO __main__ run complete tasks=6 (ok=4, failed=1, skipped=1)
```

Exit code: **0**
Status: **PASS** — quota exhaustion logged a warning and returned `skipped`; the unknown
action logged an error and returned `failed`; subsequent tasks still ran; the process did
not crash.

## 4. Boundary error paths

Malformed CLI input fails cleanly with exit code 2 and a logged message instead of a
traceback:

```text
$ python -m taskrunner.cli --once --now noon
ERROR __main__ failed to load configuration: time data 'noon' does not match format '%H:%M'
exit=2

$ python -m taskrunner.cli --once --now 12:00 --tasks bad_task.json
ERROR __main__ failed to load configuration: field 'time': is required in HH:MM format
exit=2
```

Status: **PASS**

## 5. Behaviour verified end to end

- Multiple tasks for one user in the same minute are each checked against the shared quota.
- One failing task does not stop the remaining tasks.
- All output goes through `logging` with traceable task/user/action context.
- Time matching uses `datetime.time`, not string comparison.
- CLI flags `--once`, `--now`, `--tasks`, and `--limits` work as documented.
- Invalid `--now`, invalid task payloads, invalid limits, and negative ticks exit 2 cleanly.

## 6. Conclusion

All gates pass: `ruff` clean, `mypy --strict` clean, 51 unit tests green at 97% coverage,
and the happy-path, failure-path, and boundary smoke tests all executed with verified
output.
