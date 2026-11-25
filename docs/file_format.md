# Algorithms and file format

[Back to the README](../README.md)

| Name | Algorithm | Bits per sample | Largest change to a sample |
| --- | --- | --- | --- |
| `lsb` | `LSB` | 1 (lowest bit) | 1 |
| `lsb_2` | `LSB_2` | 2 (two lowest bits) | 3 |

Both are in `algorithms/lsb.py`. They change only the lowest byte of each sample. The samples of all channels are used in the order in which they are stored.

## Capacity

For an audio file with `n` samples (counting every channel), the largest message is:

| Algorithm | Plain | Encrypted |
| --- | --- | --- |
| `LSB` | `n / 8 - 14` bytes | `n / 8 - 54` bytes |
| `LSB_2` | `2n / 8 - 14` bytes | `2n / 8 - 54` bytes |

The division is rounded down. One character can take up to four UTF-8 bytes.

## Audio quality

These are signal-to-noise ratios for the included sample (higher is better). Results change slightly with the message.

| Algorithm | 43 B | 1 KB | 10 KB |
| --- | --- | --- | --- |
| `LSB`, plain | 101.4 dB | 89.0 dB | 79.0 dB |
| `LSB`, encrypted | 99.1 dB | 88.8 dB | 79.0 dB |
| `LSB_2`, plain | 97.3 dB | 85.1 dB | 75.2 dB |
| `LSB_2`, encrypted | 95.4 dB | 85.0 dB | 75.0 dB |
| Old Basic | 57.9 dB | 43.9 dB | 33.9 dB |
| Old Enhanced without flipping | 40.0 dB | 28.1 dB | 17.9 dB |
| Old Enhanced with flipping | 40.5 dB | 27.8 dB | 17.6 dB |

The old algorithms also changed the high byte of 16-bit samples, so the start of the file could have audible noise. Neither new algorithm is designed to resist detection.

## Container layout

The hidden bytes are written from the first sample on. Each byte starts with its most significant bit. `LSB_2` puts two bits into each sample: the first in the second lowest bit, the second in the lowest bit.

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

## Security

- Encryption hides what the message says, not that it exists. The marker makes a hidden message easy to find. The message length is not encrypted.
- Anyone can find, read, change, or replace a message that has no passphrase. The CRC only detects accidents. It is not protection against tampering.
- An encrypted message cannot be changed without an error. It can still be removed, or replaced by a plain message. With a passphrase, `decode` refuses a plain message.
- A short or common passphrase can be guessed. Use a long one that you use nowhere else.
- A lost passphrase cannot be recovered.
- Editing, compressing, or converting the audio destroys the message.

This is a learning project and has not been audited.
