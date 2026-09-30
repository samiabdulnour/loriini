"""The licence service: where online licence keys are kept in force.

Roadmap R5's second half (D125; docs/licence-model.md is why, and
docs/licence-service.md is how to run it). A small web service the vendor runs
on one small container. Loriini asks it for leases (``licence_lease``) and
frees seats with it; Stripe tells it of payments; the vendor's script
(``scripts/licence.py``) issues keys through it, looks licences up, withdraws
them, recalls a version and backs it all up.

- ``store`` -- the SQLite file it keeps: licences, computers, a log.
- ``decide`` -- the one decision it makes: what lease a computer gets.
- ``stripe_events`` -- what Stripe's events do to a licence.
- ``app`` -- the requests it answers, and how it is run.

Nothing in Loriini imports this package, and the bundle leaves it out, as it
leaves out ``licence_issue``: it runs with the standard library alone, from a
checkout or a container, never from ``Loriini.exe``.
"""
