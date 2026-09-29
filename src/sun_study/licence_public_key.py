"""The public half of the key Loriini's licence keys are signed with.

Written by ``scripts/licence.py keygen`` and by nothing else: that command
makes a new key pair, keeps the private half in a file of the vendor's
choosing -- never in this repository -- and writes the public half here, as
hex, for the next build to carry (docs/licensing.md).

``None`` means this build takes no licence keys at all. It then runs on its
own term alone (``licence.EXPIRES``), exactly as builds did before keys
existed, and nothing about keys reaches the screen. A build with a public key
here asks for a key the first time it is started, and checks it at every start
after.
"""

from __future__ import annotations

#: 32 bytes of Ed25519 public key, as 64 hex digits, or ``None``.
PUBLIC_KEY: str | None = None
