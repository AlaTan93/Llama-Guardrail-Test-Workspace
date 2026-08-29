"""Typed progress reporting for pipeline runs.

Pipeline functions accept a ``ProgressReporter`` (default: the no-op base
class) and call explicit methods — no callback-shape guessing.  The web job
adapter (:class:`src.web.runners.JobProgress`) subclasses it to emit SSE
events and update the job's progress snapshot.
"""


class ProgressReporter:
    """No-op base.  Subclass (or pass any duck-typed object) to observe.

    Methods:
      ``attack_total(total)``          — attack phase size is known
      ``attack_done(rows)``            — attack phase finished, *rows* raw rows
      ``scorer_tick(scorer, done, total)`` — one response scored by *scorer*
      ``phase(name)``                  — pipeline phase transition
    """

    def attack_total(self, total: int) -> None:
        """Attack phase will run *total* atomic attacks."""

    def attack_done(self, rows: int) -> None:
        """Attack phase complete; produced *rows* raw response rows."""

    def scorer_tick(self, scorer_type: str, done: int, total: int) -> None:
        """*scorer_type* scored its *done*-th of *total* responses."""

    def phase(self, name: str) -> None:
        """Pipeline entered phase *name* (attack / extract / scoring / …)."""
