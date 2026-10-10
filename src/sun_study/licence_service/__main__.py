"""``python -m sun_study.licence_service``: run the licence service, or check
how it is set up.

::

    python -m sun_study.licence_service serve          answers on $PORT, or 8080
    python -m sun_study.licence_service check          says what it would run with

Settings come from the environment (``app.Settings.from_environment``).
``check`` prints the public half of the signing key it was given, which must
be the one in ``licence_public_key.py``: a service signing with any other key
gives leases no build believes.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence

from sun_study import licence_public_key, signing
from sun_study.licence_service.app import Service, Settings, serve


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m sun_study.licence_service")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("serve", help="Answer requests until stopped.")
    run.add_argument("--host", default="0.0.0.0")
    run.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8080")))
    commands.add_parser("check", help="Say what the service would run with, and stop.")
    arguments = parser.parse_args(argv)

    try:
        settings = Settings.from_environment()
    except (ValueError, OSError) as problem:
        print(f"The licence service cannot start: {problem}", file=sys.stderr)
        return 1
    public = signing.public_key(settings.seed).hex()
    trusted = licence_public_key.PUBLIC_KEY
    if arguments.command == "check":
        print(f"Signing key's public half: {public}")
        if trusted is None:
            print("This checkout's build carries no public key yet.")
        elif trusted != public:
            print("It is NOT the public key this checkout's build carries.", file=sys.stderr)
            return 1
        else:
            print("It is the public key this checkout's build carries.")
        print(f"Database: {settings.database}")
        print(f"Admin token: {'set' if settings.admin_token else 'NOT set'}")
        print(f"Stripe webhook secret: {'set' if settings.stripe_secret else 'NOT set'}")
        mail = settings.smtp_host and settings.sender
        print(f"Mail: {settings.sender} via {settings.smtp_host}" if mail else "Mail: NOT set")
        return 0
    settings.database.parent.mkdir(parents=True, exist_ok=True)
    serve(Service(settings), host=arguments.host, port=arguments.port)
    return 0  # pragma: no cover - serve returns only when stopped


if __name__ == "__main__":
    raise SystemExit(main())
