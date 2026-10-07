"""The public half of the key Loriini's licence keys are signed with,
and where the licence service is.

Written by ``scripts/licence.py keygen`` and ``service``: the private half
is kept by the vendor, outside this repository. A build carrying a key
here asks for a licence key and checks it at every start; with a service
as well, it takes the online keys the service keeps in force
(docs/licensing.md).
"""

from __future__ import annotations

#: 32 bytes of Ed25519 public key, as 64 hex digits, or ``None``.
PUBLIC_KEY: str | None = "8e492b9f33f4c72b836e2dff7f08238b68d7b5564f35dd7ed80311081d2b48a8"

#: The licence service's address, ``https://...``, or ``None``.
SERVICE: str | None = "https://loriini-licences.fly.dev"
