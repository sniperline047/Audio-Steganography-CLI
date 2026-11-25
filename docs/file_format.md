# Algorithms and file format

[Back to the README](../README.md)

| Name | Algorithm | Bits per sample | Largest change to a sample |
| --- | --- | --- | --- |
| `lsb` | `LSB` | 1 (lowest bit) | 1 |
| `lsb_2` | `LSB_2` | 2 (two lowest bits) | 3 |
| `lsb_4` | `LSB_4` | 4 (four lowest bits) | 15 |
| `lsb_matching` | `LSB_MATCHING` | 1 (lowest bit) | 1 |
| `lsb_parity` | `LSB_PARITY` | 1 in each group of 8 samples | 1 |
| `lsb_keyed` | `LSB_KEYED` | 1 (lowest bit) | 1 |

`LSB` and `LSB_2` are in `algorithms/lsb.py`, `LSB_4` in `algorithms/lsb_four.py`, and each other one in a file with its name. The samples of all channels are used in the order in which they are stored, except by `LSB_KEYED`. All of them change only the lowest byte of a sample, except `LSB_MATCHING`.

`LSB_MATCHING` adds or subtracts 1 at random if the lowest bit of a sample is wrong. It counts the whole sample as one number (unsigned for 8 bits, signed and little-endian for more), so higher bytes can change too. The smallest number only moves up, and the largest only down. The lowest bits are the same as with `LSB`, so **a reader cannot tell them apart**: `inspect` and `reveal` call such a message `lsb`.

`LSB_PARITY` takes 8 samples in a row for each bit. The bit is 1 if an odd number of their lowest bits is 1, and 0 if not. If it is wrong, the lowest bit of one randomly chosen sample of the group is flipped. Samples left over at the end are not used.

`LSB_KEYED` is described [below](#lsb_keyed).

## Capacity

For an audio file with `n` samples (counting every channel), the largest message is:

| Algorithm | Plain | Encrypted |
| --- | --- | --- |
| `LSB` | `n / 8 - 14` bytes | `n / 8 - 54` bytes |
| `LSB_2` | `2n / 8 - 14` bytes | `2n / 8 - 54` bytes |
| `LSB_4` | `4n / 8 - 14` bytes | `4n / 8 - 54` bytes |
| `LSB_MATCHING` | `n / 8 - 14` bytes | `n / 8 - 54` bytes |
| `LSB_PARITY` | `n / 64 - 14` bytes | `n / 64 - 54` bytes |
| `LSB_KEYED` | none | `n / 8 - 54` bytes |

The division is rounded down. One character can take up to four UTF-8 bytes.

## Audio quality

These are signal-to-noise ratios for the included sample (higher is better). Results change slightly with the message.

| Algorithm | 43 B | 1 KB | 10 KB |
| --- | --- | --- | --- |
| `LSB`, plain | 101.4 dB | 89.0 dB | 79.0 dB |
| `LSB`, encrypted | 99.1 dB | 88.8 dB | 79.0 dB |
| `LSB_2`, plain | 97.3 dB | 85.1 dB | 75.2 dB |
| `LSB_2`, encrypted | 95.4 dB | 85.0 dB | 75.0 dB |
| `LSB_4`, plain | 88.9 dB | 76.8 dB | 67.0 dB |
| `LSB_4`, encrypted | 85.5 dB | 75.5 dB | 65.7 dB |
| `LSB_MATCHING`, plain | 101.4 dB | 89.0 dB | 79.0 dB |
| `LSB_MATCHING`, encrypted | 99.2 dB | 88.8 dB | 79.0 dB |
| `LSB_PARITY`, plain | 101.4 dB | 88.9 dB | does not fit |
| `LSB_PARITY`, encrypted | 99.2 dB | 88.8 dB | does not fit |
| `LSB_KEYED`, encrypted | 99.3 dB | 88.8 dB | 79.0 dB |
| Old Basic | 57.9 dB | 43.9 dB | 33.9 dB |
| Old Enhanced without flipping | 40.0 dB | 28.1 dB | 17.9 dB |
| Old Enhanced with flipping | 40.5 dB | 27.8 dB | 17.6 dB |

The old algorithms also changed the high byte of 16-bit samples, so the start of the file could have audible noise. `LSB_PARITY` changes as many samples as `LSB` for the same message, but spreads them over 8 times as many. No algorithm is proven to resist detection by statistics.

## Container layout

The hidden bytes are written from the first sample on, except by `LSB_KEYED`. Each byte starts with its most significant bit. `LSB_2` puts two bits into each sample: the first in the second lowest bit, the second in the lowest bit. `LSB_4` puts four bits into each sample, the first in the fourth lowest bit and the last in the lowest bit.

Every container starts with a 10-byte header:

| Offset | Size | Content |
| --- | --- | --- |
| 0 | 4 | Marker: `ASTG` (`41 53 54 47`) |
| 4 | 1 | Version: 1 |
| 5 | 1 | Flags: bit 0 (value 1) means encrypted; all other bits are 0 |
| 6 | 4 | Message length `m` in bytes, before encryption, big-endian |

A plain container continues with:

| Offset | Size | Content |
| --- | --- | --- |
| 10 | `m` | Message as UTF-8 |
| 10 + `m` | 4 | CRC-32 (as in zlib) of the header and the message, big-endian |

An encrypted container continues with:

| Offset | Size | Content |
| --- | --- | --- |
| 10 | 16 | Salt |
| 26 | 12 | Nonce |
| 38 | `m` | Message as UTF-8, encrypted with AES-256-GCM |
| 38 + `m` | 16 | AES-GCM tag, which also covers the header (as associated data) |

The key is 32 bytes from scrypt with `n` = 131072, `r` = 8, and `p` = 1. Its input is the salt and the passphrase, normalized to Unicode NFC and stored as UTF-8. These values belong to version 1 and are never read from a file. The salt and nonce are random for every message. Making the key needs about 128 MiB of memory.

## lsb_keyed

A message of `LSB_KEYED` uses the encrypted container above, with two keys from the passphrase and another order of the samples. Everything that is needed to read it:

1. Let `n` be the number of samples, counting every channel. With `n` below 432, there is no message.
2. The lowest bits of samples 0 to 127 are the 16 bytes of the salt, most significant bit first.
3. The master key is 32 bytes from scrypt, with the same numbers and passphrase as above.
4. Two keys of 32 bytes come from the master key with HKDF-Expand (RFC 5869, SHA-256). The `info` of the **order key** is the ASCII text `audiosteg keyed 1: order`. That of the **encryption key** is `audiosteg keyed 1: encryption`. For 32 bytes, this is HMAC-SHA256 with the master key of the `info` followed by the byte 1.
5. The order key decides a permutation `P` of the numbers from 0 to `N - 1`, with `N = n - 128`, as described below.
6. The container without its salt (header, nonce, encrypted message, tag) is a row of bits, most significant bit of each byte first. Bit `i` is the lowest bit of sample `128 + P(i)`.
7. The header is the first 80 bits. If it does not start with the marker, the passphrase is wrong or there is no message. It must say that the message is encrypted, and `m + 54` must be at most `n / 8`, rounded down.
8. The nonce (12 bytes), the encrypted message (`m` bytes), and the tag (16 bytes) follow. The encryption is AES-256-GCM with the encryption key and the header as associated data.

The permutation is a Feistel network with 10 rounds that walks in cycles:

- `w` is the smallest whole number, at least 1, with `4^w >= N`.
- Round `r` (from 0 to 9) has a table of `2^w` entries. It is made from the first `2 * 2^w` bytes of SHAKE-256 of the order key (32 bytes), `N` (8 bytes, big-endian), and `r` (1 byte). Each 2 bytes are one big-endian number, and its `w` lowest bits are the entry.
- To find `P(i)`, start with `x = i`. Split `x` into `left` (its upper `w` bits) and `right` (its lower `w` bits). In each round, the new `left` is the old `right`, and the new `right` is the old `left` XOR entry number `right` (the old one) of the table. After the last round, `x = left * 2^w + right`.
- If `x` is `N` or more, do all rounds again with this `x`. Otherwise it is `P(i)`.

The salt and the nonce are random for every message, so the places differ every time. The tables need at most 1.3 MB, however large the file is.

Without the passphrase, the salt looks like any other random bits and nothing else has a known place. **This only means that no marker, length, or text can be read.** Comparing with the original shows every change. Statistics can show that lowest bits were replaced, most of all in silence, in very clean audio, or with a long message, and the first 128 lowest bits are always random. Adding or removing samples, even at the end, makes the message unreadable.

## Security

- Encryption hides what the message says, not that it exists. The marker makes a hidden message easy to find. The message length is not encrypted. With `LSB_KEYED`, the marker and the length have secret places, but statistics can still show that something is there.
- Anyone can find, read, change, or replace a message that has no passphrase. The CRC only detects accidents. It is not protection against tampering.
- An encrypted message cannot be changed without an error. It can still be removed, or replaced by a plain message. With a passphrase, `decode` refuses a plain message. Hiding another message in a file can destroy an earlier one, also one of `LSB_KEYED`.
- A short or common passphrase can be guessed. Use a long one that you use nowhere else.
- A lost passphrase cannot be recovered.
- Editing, compressing, or converting the audio destroys the message.

This is a learning project and has not been audited.
