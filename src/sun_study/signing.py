"""Ed25519 signatures from the standard library alone: RFC 8032, section 5.1.

A licence key is a statement -- this email, these seats, until this date --
signed with a private key only the vendor holds, and Loriini checks the
signature with the public half compiled into it (roadmap R5, D124). The check
happens offline, at every start, on a workstation with no administrator
rights, so it has to be in the bundle; and a runtime dependency is a
conversation here (D106). Ed25519 is the right signature for it -- short
keys, short signatures, no parameters to choose wrongly -- and its reference
algorithm in RFC 8032 is a page of integer arithmetic that Python's own
``int`` and ``hashlib.sha512`` carry out exactly. So it is written here, and
checked against the RFC's own test vectors and against an independent
implementation (``tests/unit/test_signing.py``).

What this is and is not
-----------------------
Verification works on public data only, so its speed and its timing reveal
nothing: a few milliseconds, once per start. Signing uses the private key and
is not constant-time; it runs on the vendor's own machine, to issue a key,
where there is nobody to time it. Nothing else in Loriini signs.

The decoding checks the RFC asks for are all here, because they are where a
careless implementation accepts what it should not: a coordinate at or past
the field prime, a point off the curve, a zero ``x`` with its sign bit set,
and a signature whose ``S`` is not below the group order ``L`` -- that last
check is what stops one valid signature being turned into another.
"""

from __future__ import annotations

import hashlib
import secrets

__all__ = ["KEY_BYTES", "SIGNATURE_BYTES", "new_seed", "public_key", "sign", "verify"]

#: A private key (the RFC's 32-byte "secret"), and a public key, in bytes.
KEY_BYTES = 32
SIGNATURE_BYTES = 64

#: The field prime, the group order, the curve constant and the square root
#: of -1, as RFC 8032 section 5.1 names them.
_P = 2**255 - 19
_L = 2**252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, _P - 2, _P) % _P
_SQRT_M1 = pow(2, (_P - 1) // 4, _P)

#: A point in extended homogeneous coordinates, ``(X, Y, Z, T)`` with
#: ``x = X/Z``, ``y = Y/Z`` and ``x*y = T/Z``.
Point = tuple[int, int, int, int]

_NEUTRAL: Point = (0, 1, 1, 0)


def _sha512(*parts: bytes) -> bytes:
    digest = hashlib.sha512()
    for part in parts:
        digest.update(part)
    return digest.digest()


def _sha512_mod_l(*parts: bytes) -> int:
    return int.from_bytes(_sha512(*parts), "little") % _L


def _add(p: Point, q: Point) -> Point:
    """RFC 8032 5.1.4: the unified addition, which also doubles."""
    a = (p[1] - p[0]) * (q[1] - q[0]) % _P
    b = (p[1] + p[0]) * (q[1] + q[0]) % _P
    c = 2 * p[3] * q[3] * _D % _P
    d = 2 * p[2] * q[2] % _P
    e, f, g, h = b - a, d - c, d + c, b + a
    return (e * f % _P, g * h % _P, f * g % _P, e * h % _P)


def _multiply(scalar: int, point: Point) -> Point:
    result = _NEUTRAL
    while scalar > 0:
        if scalar & 1:
            result = _add(result, point)
        point = _add(point, point)
        scalar >>= 1
    return result


def _equal(p: Point, q: Point) -> bool:
    """Whether two points are the same, compared projectively."""
    if (p[0] * q[2] - q[0] * p[2]) % _P != 0:
        return False
    return (p[1] * q[2] - q[1] * p[2]) % _P == 0


def _recover_x(y: int, sign: int) -> int | None:
    """RFC 8032 5.1.3: the ``x`` for this ``y`` and sign bit, or ``None`` when
    there is no such point on the curve."""
    if y >= _P:
        return None
    x2 = (y * y - 1) * pow(_D * y * y + 1, _P - 2, _P) % _P
    if x2 == 0:
        # x is zero, and a zero has no sign to set: "if x = 0 and x_0 = 1,
        # decoding fails".
        return None if sign else 0
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P != 0:
        x = x * _SQRT_M1 % _P
    if (x * x - x2) % _P != 0:
        return None
    if (x & 1) != sign:
        x = _P - x
    return x


def _base() -> Point:
    y = 4 * pow(5, _P - 2, _P) % _P
    x = _recover_x(y, 0)
    if x is None:  # pragma: no cover - the base point is on the curve
        raise AssertionError("the Ed25519 base point did not decode")
    return (x, y, 1, x * y % _P)


_G = _base()


def _compress(point: Point) -> bytes:
    inverse = pow(point[2], _P - 2, _P)
    x = point[0] * inverse % _P
    y = point[1] * inverse % _P
    return int.to_bytes(y | ((x & 1) << 255), KEY_BYTES, "little")


def _decompress(data: bytes) -> Point | None:
    if len(data) != KEY_BYTES:
        return None
    y = int.from_bytes(data, "little")
    sign = y >> 255
    y &= (1 << 255) - 1
    x = _recover_x(y, sign)
    if x is None:
        return None
    return (x, y, 1, x * y % _P)


def _expand(seed: bytes) -> tuple[int, bytes]:
    """RFC 8032 5.1.5: the private scalar, clamped, and the nonce prefix."""
    if len(seed) != KEY_BYTES:
        raise ValueError(f"an Ed25519 private key is {KEY_BYTES} bytes, not {len(seed)}")
    digest = _sha512(seed)
    scalar = int.from_bytes(digest[:32], "little")
    scalar &= (1 << 254) - 8
    scalar |= 1 << 254
    return scalar, digest[32:]


def new_seed() -> bytes:
    """A new private key: 32 bytes from the operating system's own source."""
    return secrets.token_bytes(KEY_BYTES)


def public_key(seed: bytes) -> bytes:
    """The public key that goes with a private one."""
    scalar, _ = _expand(seed)
    return _compress(_multiply(scalar, _G))


def sign(seed: bytes, message: bytes) -> bytes:
    """RFC 8032 5.1.6: the 64-byte signature of ``message``."""
    scalar, prefix = _expand(seed)
    public = _compress(_multiply(scalar, _G))
    nonce = _sha512_mod_l(prefix, message)
    commitment = _compress(_multiply(nonce, _G))
    challenge = _sha512_mod_l(commitment, public, message)
    s = (nonce + challenge * scalar) % _L
    return commitment + int.to_bytes(s, 32, "little")


def verify(public: bytes, message: bytes, signature: bytes) -> bool:
    """RFC 8032 5.1.7: whether ``signature`` is ``public``'s over ``message``.

    Answers False rather than raising for anything malformed -- a key of the
    wrong length, a point not on the curve, an ``S`` not below ``L`` -- since
    to a caller each of those is simply a signature that does not check out.
    """
    if len(public) != KEY_BYTES or len(signature) != SIGNATURE_BYTES:
        return False
    signer = _decompress(public)
    if signer is None:
        return False
    commitment = _decompress(signature[:32])
    if commitment is None:
        return False
    s = int.from_bytes(signature[32:], "little")
    if s >= _L:
        return False
    challenge = _sha512_mod_l(signature[:32], public, message)
    return _equal(_multiply(s, _G), _add(commitment, _multiply(challenge, signer)))
