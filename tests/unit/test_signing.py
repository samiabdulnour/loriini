"""Ed25519 against the RFC that defines it.

The vectors are RFC 8032 section 7.1's own, copied from the RFC text: the
private key, the public key it must give, the message and the one signature
Ed25519's determinism allows. Passing them means the arithmetic is the
standard's; the refusals below are the decoding checks the RFC asks for,
which is where an implementation that signs correctly can still verify
something it should not. (Cross-checked by hand against the ``cryptography``
package on two hundred random keys when the module was written; that package
is not a dependency, so it is not a test.)
"""

from __future__ import annotations

import pytest

from sun_study import signing

#: (secret key, public key, message, signature), RFC 8032 7.1 TEST 1, 2, 3
#: and SHA(abc).
RFC_8032 = [
    (
        "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60",
        "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a",
        "",
        "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b",
    ),
    (
        "4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb",
        "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c",
        "72",
        "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00",
    ),
    (
        "c5aa8df43f9f837bedb7442f31dcb7b166d38535076f094b85ce3a2e0b4458f7",
        "fc51cd8e6218a1a38da47ed00230f0580816ed13ba3303ac5deb911548908025",
        "af82",
        "6291d657deec24024827e69c3abe01a30ce548a284743a445e3680d7db5ac3ac18ff9b538d16f290ae67f760984dc6594a7c15e9716ed28dc027beceea1ec40a",
    ),
    (
        "833fe62409237b9d62ec77587520911e9a759cec1d19755b7da901b96dca3d42",
        "ec172b93ad5e563bf4932c70e1245034c35467ef2efd4d64ebf819683467e2bf",
        "ddaf35a193617abacc417349ae20413112e6fa4e89a97ea20a9eeee64b55d39a2192992a274fc1a836ba3c23a3feebbd454d4423643ce80e2a9ac94fa54ca49f",
        "dc2a4459e7369633a52b1bf277839a00201009a3efbf3ecb69bea2186c26b58909351fc9ac90b3ecfdfbc7c66431e0303dca179c138ac17ad9bef1177331a704",
    ),
]

L = 2**252 + 27742317777372353535851937790883648493


@pytest.mark.parametrize(("secret", "public", "message", "signature"), RFC_8032)
def test_the_rfc_vectors(secret: str, public: str, message: str, signature: str) -> None:
    seed, key = bytes.fromhex(secret), bytes.fromhex(public)
    text, signed = bytes.fromhex(message), bytes.fromhex(signature)

    assert signing.public_key(seed) == key
    assert signing.sign(seed, text) == signed
    assert signing.verify(key, text, signed)


@pytest.mark.parametrize(("secret", "public", "message", "signature"), RFC_8032)
def test_anything_changed_does_not_verify(
    secret: str, public: str, message: str, signature: str
) -> None:
    key, text, signed = bytes.fromhex(public), bytes.fromhex(message), bytes.fromhex(signature)
    for position in (0, 31, 32, 63):
        bent = bytearray(signed)
        bent[position] ^= 0x01
        assert not signing.verify(key, text, bytes(bent)), f"a bit flipped at {position}"
    assert not signing.verify(key, text + b"!", signed), "a longer message"
    other = signing.public_key(bytes(32))
    assert not signing.verify(other, text, signed), "somebody else's key"


def test_a_signature_with_s_past_the_group_order_is_refused() -> None:
    """S and S + L are the same scalar; accepting both would let anyone turn
    one valid signature into a second. RFC 8032 5.1.7 requires S < L."""
    _secret, public, message, signature = (bytes.fromhex(part) for part in RFC_8032[1])
    s = int.from_bytes(signature[32:], "little") + L
    forged = signature[:32] + s.to_bytes(32, "little")
    assert signing.verify(public, message, signature)
    assert not signing.verify(public, message, forged)


def test_what_is_not_a_key_or_a_signature_is_refused_not_raised() -> None:
    _secret, public, message, signature = (bytes.fromhex(part) for part in RFC_8032[0])
    assert not signing.verify(public[:31], message, signature), "a short key"
    assert not signing.verify(public, message, signature[:63]), "a short signature"
    # A y coordinate of the field prime itself decodes to no point at all.
    past_the_prime = (2**255 - 19).to_bytes(32, "little")
    assert not signing.verify(past_the_prime, message, signature)
    # x = 0 with the sign bit set: RFC 8032 5.1.3 says decoding fails.
    one_with_sign = (1 | (1 << 255)).to_bytes(32, "little")
    assert not signing.verify(one_with_sign, message, signature)


def test_a_new_key_signs_and_verifies_and_is_never_the_last_one() -> None:
    first, second = signing.new_seed(), signing.new_seed()
    assert len(first) == signing.KEY_BYTES and first != second
    signed = signing.sign(first, b"Loriini")
    assert len(signed) == signing.SIGNATURE_BYTES
    assert signing.verify(signing.public_key(first), b"Loriini", signed)
    assert not signing.verify(signing.public_key(second), b"Loriini", signed)


def test_a_private_key_of_the_wrong_size_is_an_error() -> None:
    with pytest.raises(ValueError, match="32 bytes"):
        signing.sign(b"short", b"message")
