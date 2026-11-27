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
| `echo` | `ECHO` | 1 in each block of 1,024 frames | up to the loudness of the sound |

`LSB` and `LSB_2` are in `algorithms/lsb.py`, `LSB_4` in `algorithms/lsb_four.py`, and each other one in a file with its name. The samples of all channels are used in the order in which they are stored, except by `LSB_KEYED`. All of them change only the lowest byte of a sample, except `LSB_MATCHING`.

`LSB_MATCHING` adds or subtracts 1 at random if the lowest bit of a sample is wrong. It counts the whole sample as one number (unsigned for 8 bits, signed and little-endian for more), so higher bytes can change too. The smallest number only moves up, and the largest only down. The lowest bits are the same as with `LSB`, so **a reader cannot tell them apart**: `inspect` and `reveal` call such a message `lsb`.

`LSB_PARITY` takes 8 samples in a row for each bit. The bit is 1 if an odd number of their lowest bits is 1, and 0 if not. If it is wrong, the lowest bit of one randomly chosen sample of the group is flipped. Samples left over at the end are not used.

`LSB_KEYED` and `ECHO` are described [below](#lsb_keyed). Everything on this page about samples and their lowest bytes is about the others; `ECHO` changes whole blocks of sound.

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
| `ECHO` | see [below](#echo) | see [below](#echo) |

The division is rounded down. One character can take up to four UTF-8 bytes.

## Audio quality

These are signal-to-noise ratios for the included sample (higher is better). The plain rows hide the 43 characters `Hello Peter. I have been waiting for you...`, repeated without a space and cut to 43, 1,024, or 10,240 bytes. The numbers are rounded down. Encrypted messages are random, so their rows are averages of five runs and change a little every time, and so does `LSB_PARITY`. The old algorithms cannot hide messages anymore; their rows were measured with an earlier version and another message may have been used.

| Algorithm | 43 B | 1 KB | 10 KB |
| --- | --- | --- | --- |
| `LSB`, plain | 101.4 dB | 88.9 dB | 79.0 dB |
| `LSB`, encrypted | 99.1 dB | 88.8 dB | 79.0 dB |
| `LSB_2`, plain | 97.9 dB | 85.5 dB | 75.5 dB |
| `LSB_2`, encrypted | 95.4 dB | 85.0 dB | 75.0 dB |
| `LSB_4`, plain | 88.2 dB | 75.9 dB | 66.0 dB |
| `LSB_4`, encrypted | 85.5 dB | 75.5 dB | 65.7 dB |
| `LSB_MATCHING`, plain | 101.4 dB | 88.9 dB | 79.0 dB |
| `LSB_MATCHING`, encrypted | 99.2 dB | 88.8 dB | 79.0 dB |
| `LSB_PARITY`, plain | 101.5 dB | 88.9 dB | does not fit |
| `LSB_PARITY`, encrypted | 99.2 dB | 88.8 dB | does not fit |
| `LSB_KEYED`, encrypted | 99.3 dB | 88.8 dB | 79.0 dB |
| Old Basic | 57.9 dB | 43.9 dB | 33.9 dB |
| Old Enhanced without flipping | 40.0 dB | 28.1 dB | 17.9 dB |
| Old Enhanced with flipping | 40.5 dB | 27.8 dB | 17.6 dB |

The old algorithms also changed the high byte of 16-bit samples, so the start of the file could have audible noise. `LSB_PARITY` changes as many samples as `LSB` for the same message, but spreads them over 8 times as many. No algorithm is proven to resist detection by statistics.

## Container layout

The hidden bytes are written from the first sample on, except by `LSB_KEYED` and `ECHO`. Each byte starts with its most significant bit. `LSB_2` puts two bits into each sample: the first in the second lowest bit, the second in the lowest bit. `LSB_4` puts four bits into each sample, the first in the fourth lowest bit and the last in the lowest bit.

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
5. The order key decides a permutation `P` of the numbers from 0 to `N - 1`, with `N = n - 128`, which is at most `2^32`, as described below.
6. The container without its salt (header, nonce, encrypted message, tag) is a row of bits, most significant bit of each byte first. Bit `i` is the lowest bit of sample `128 + P(i)`.
7. The header is the first 80 bits. If it does not start with the marker, the passphrase is wrong or there is no message. The version must be 1 and the flags must be 1 (encrypted, all other bits 0), and `m + 54` must be at most `n / 8`, rounded down.
8. The nonce (12 bytes), the encrypted message (`m` bytes), and the tag (16 bytes) follow. The encryption is AES-256-GCM with the encryption key and the header as associated data.

The permutation is a Feistel network with 10 rounds that walks in cycles:

- `w` is the smallest whole number, at least 1, with `4^w >= N`.
- Round `r` (from 0 to 9) has a table of `2^w` entries. It is made from the first `2 * 2^w` bytes of SHAKE-256 of the order key (32 bytes), `N` (8 bytes, big-endian), and `r` (1 byte). Each 2 bytes are one big-endian number, and its `w` lowest bits are the entry.
- To find `P(i)`, start with `x = i`. Split `x` into `left` (its upper `w` bits) and `right` (its lower `w` bits). In each round, the new `left` is the old `right`, and the new `right` is the old `left` XOR entry number `right` (the old one) of the table. After the last round, `x = left * 2^w + right`.
- If `x` is `N` or more, do all rounds again with this `x`. Otherwise it is `P(i)`.

The salt and the nonce are random for every message, so the places differ every time. The tables need at most 1.3 MB, however large the file is.

Without the passphrase, the salt looks like any other random bits and nothing else has a known place. **This only means that no marker, length, or text can be read.** Comparing with the original shows every change. Statistics can show that lowest bits were replaced, most of all in silence, in very clean audio, or with a long message, and the first 128 lowest bits are always random. Compared with the original, the number of changed samples shows roughly how long the message is: about half of its container bits change a sample. Adding or removing samples, even at the end, makes the message unreadable.

**Use a cover that never held a message.** `LSB_KEYED` changes only lowest bits. An old `LSB_4` message leaves its three upper bits of each sample behind, and about 1 time in 256 its marker too. Such a file seems to hold an `LSB_4` message, mostly one that cannot be read, so `LSB_KEYED` is not tried, and the message must be read with `-a lsb_keyed`.

## echo

`ECHO` adds an echo to each block of sound. The delay of the echo is the bit, so the message is in the sound itself and not in the lowest bits. It needs NumPy (the `signal` extra). **The echo can be heard**, like a small room or a slightly metallic sound, most of all in speech and clear tones.

### Blocks and bits

A frame is one sample of every channel. Block `k` is the frames from `1024 k` to `1024 k + 1023`, counted from 0. Blocks that are not complete carry nothing, and the sample rate does not matter. Block `k` carries bit `k` of the bytes below, most significant bit of each byte first.

| Bytes | Content |
| --- | --- |
| 10 | The header of the container above |
| 16 | Parity bytes of the header |
| `L` | The rest of the container: `L = m + 4`, or `m + 44` if it is encrypted |
| `C * P` | Parity bytes of the rest |

With `C = ceil(L / 120)` and `P = max(16, ceil(L / C))`, byte `i` of the rest (from 0) belongs to codeword `i mod C`. The parity bytes are stored in turns: the first one of every codeword, then the second one of every codeword, and so on. So neighbouring bytes belong to different codewords, and a lost part of the sound is spread over all of them.

### Error correction

A codeword is some data bytes followed by its parity bytes, at most 255 together. The code is a Reed-Solomon code over GF(256):

- Numbers are bytes. Adding is XOR. Multiplying is multiplying polynomials over GF(2), modulo `x^8 + x^4 + x^3 + x^2 + 1` (`0x11D`).
- The generator polynomial with `P` parity bytes is the product of `(x - 2^j)` for `j` from 0 to `P - 1`.
- The codeword is a polynomial, its first byte at the highest power. The parity bytes are the remainder after dividing the data, multiplied by `x^P`, by the generator.

`P` parity bytes correct up to `P / 2` wrong bytes, rounded down, wherever they are: 8 of the 26 bytes of the header, and about a quarter of every codeword of a long message. With more wrong bytes, correcting mostly fails. If it does not, the marker, and the CRC or the AES-GCM tag of the container, decide whether the message is accepted, so a wrong text is not shown as right.

A reader corrects the header first. If that fails, or the marker is wrong, there is no message. Random bytes pass the correction and the marker with a chance of about 1 in 5 * 10^22. The same rules as above apply to the version and the flags. The rest must fit in the complete blocks of the file.

### Hiding

Samples are numbers `x` where 0 is silence (128 is subtracted from 8-bit samples). With the bits `b`, each channel becomes

`y[n] = x[n] + a * (z[n] * x[n - 25] + o[n] * x[n - 50])`

where samples before the first one are 0. `o` is how much the echo for 1 is wanted, and `z` the same for 0:

- `w[0] = 0`, `w[k + 1] = b[k]` for `o` (`1 - b[k]` for `z`), and one 0 after the last bit.
- `k` and `t` are the quotient and the remainder of `(n + 128) / 1024`.
- `f = 0.5 - 0.5 cos(pi * min(t, 256) / 256)`, and the result is `w[k] * (1 - f) + w[k + 1] * f`.

So the echo changes smoothly within 256 frames around each edge of a block, and ends 128 frames after the last block. Everything else stays as it is, with two exceptions, the next one and old markers (below): if a result is too large for a sample, every sample of the file is multiplied by the same number below 1, and `hide` says so. Results are rounded to the nearest whole number.

The strength `a` is the first of 0.2, 0.3, 0.4, and 0.5 with which `hide` can read the message back from its own result with at most half of the wrong bytes that every codeword can correct. If there is none, 0.5 is used if the message can be read back at all. Otherwise the file is refused and nothing is saved. A reader does not need to know `a`.

If the result would still show the marker of an older `LSB`, `LSB_2`, `LSB_4`, or `LSB_PARITY` message (the first samples can be silent), the lowest bit of the first sample is flipped (or that of another of the first 8 samples, or of two of them, if that would show another such marker), so that the old message is not found first.

### Reading

The channels are added together. Each block is multiplied by the window `0.5 - 0.5 cos(2 pi i / 1024)` for `i` from 0 to 1023. With its discrete Fourier transform `X`, the cepstrum is the inverse transform of `ln(|X|^2 + 1)`. The bit is 1 if the cepstrum at 50 is larger than at 25, and 0 if not. Channels that cancel each other when added cannot be read and are refused when hiding.

### Capacity and quality

With `B` complete blocks, the largest message is the largest `m` with `8 * (26 + L + C * P) <= B`. This is what may fit; the sound decides whether it does.

| Sound | Plain | Encrypted |
| --- | --- | --- |
| The included sample (4.28 s at 22,050 Hz) | too short | too short |
| The shortest for an empty message at 44,100 Hz | 8.5 s | 21.2 s |
| 1 minute at 44,100 Hz | 144 bytes | 104 bytes |
| 4 minutes at 44,100 Hz | 626 bytes | 586 bytes |

The included sample holds 92 blocks, and the smallest plain message needs 368. No choice of blocks and delays makes it useful: with blocks of 512 frames, which would give 184 bits, 3 to 20% of its bits were read wrong with the loud echo of 0.5, depending on the delays, because it is made of pure tones.

These numbers were measured with artificial sounds made by a program: 10 of each (1 tone, 1 silence), each just long enough for a plain message of 20 bytes, which differs in each. "Wrong bits" is the share of wrong bits before error correction, for the strengths 0.2, 0.3, 0.4, and 0.5. "Hidden" counts the files that were accepted.

| Sound | Format | Wrong bits (%) | Hidden | Strengths used |
| --- | --- | --- | --- | --- |
| White noise | 16-bit, 44,100 Hz | 0.3 / 0.0 / 0.0 / 0.0 | 10 of 10 | 0.2 |
| Pink noise | 16-bit, 44,100 Hz | 0.3 / 0.0 / 0.0 / 0.0 | 10 of 10 | 0.2 |
| Like speech | 16-bit, 44,100 Hz | 3.2 / 0.2 / 0.0 / 0.0 | 10 of 10 | 0.2 to 0.3 |
| Like speech | 16-bit, 8,000 Hz | 2.0 / 1.2 / 0.8 / 0.5 | 10 of 10 | 0.2 to 0.5 |
| Like speech | 8-bit, 44,100 Hz | 17.6 / 10.2 / 8.3 / 7.3 | 7 of 10 | 0.5 |
| Like music | 16-bit, 44,100 Hz | 2.1 / 0.6 / 0.3 / 0.2 | 10 of 10 | 0.2 to 0.3 |
| Like music | 24-bit, 48,000 Hz | 2.3 / 0.4 / 0.1 / 0.1 | 10 of 10 | 0.2 to 0.3 |
| Like music | 16-bit, 22,050 Hz | 7.2 / 2.2 / 0.5 / 0.1 | 10 of 10 | 0.3 to 0.4 |
| Like music | 16-bit, 8,000 Hz | 11.3 / 5.5 / 2.7 / 1.4 | 10 of 10 | 0.4 to 0.5 |
| Like music | 8-bit, 44,100 Hz | 4.7 / 1.0 / 0.2 / 0.2 | 10 of 10 | 0.3 to 0.4 |
| A steady chord | 16-bit, 44,100 Hz | 39.8 / 25.3 / 9.7 / 7.6 | 0 of 10 | none |
| A pure tone | 16-bit, 22,050 Hz | 49.2 / 49.2 / 48.8 / 49.2 | 0 of 1 | none |
| Silence | any | about 50 | 0 of 1 | none |
| The included sample, 5 times in a row | 16-bit, 22,050 Hz | 24.6 / 18.7 / 10.7 / 5.7 | 5 bytes: 1 of 1 | 0.5 |

Real recordings were not measured. The blocks, delays, and strengths were chosen by such measurements: blocks of 256 frames read music and the sample much worse; 2,048 frames are a little better and hold half as much. Delays of 25 and 50 frames were the best or close to it for speech and music at every rate. Strengths below 0.2 were not tried.

| Strength | SNR where the echo is |
| --- | --- |
| 0.2 | 14.1 dB |
| 0.3 | 10.6 dB |
| 0.4 | 8.1 dB |
| 0.5 | 6.2 dB |

The SNR was nearly the same for every sound, also for the included sample with random bits in its 92 blocks. So `compare` calls every such file Poor. SNR counts an echo as noise, although it follows the sound, so this is stricter than the ear, but the echo is far from hidden.

**Nothing is promised about editing, compressing, or converting the audio.** It was not measured. Anyone who looks for echoes can find and read a message that is not encrypted.

Hiding a short message in a file of 1 GiB needs about 2 GiB of memory, and filling such a file with a message about 3.3 GiB. Reading needs little memory, whatever the size of the file. Only the first 208 blocks are read to detect a message.

## Security

- Encryption hides what the message says, not that it exists. The marker makes a hidden message easy to find. The message length is not encrypted. With `LSB_KEYED`, the marker and the length have secret places, but statistics can still show that something is there.
- Anyone can find, read, change, or replace a message that has no passphrase. The CRC only detects accidents. It is not protection against tampering.
- An encrypted message cannot be changed without an error. It can still be removed, or replaced by a plain message. With a passphrase, `decode` refuses a plain message. Hiding another message in a file can destroy an earlier one, also one of `LSB_KEYED`.
- A short or common passphrase can be guessed. Use a long one that you use nowhere else.
- A lost passphrase cannot be recovered.
- Editing, compressing, or converting the audio destroys the message.

This is a learning project and has not been audited.
