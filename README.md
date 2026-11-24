# Audio Steganography CLI

[![Test coverage](https://github.com/sniperline047/Audio-Steganography-CLI/raw/coverage_badge/coverage.svg)](https://github.com/sniperline047/Audio-Steganography-CLI/actions/workflows/tests.yml)

A learning project that hides a text message inside a WAV file and reads it back. It offers two least significant bit (LSB) algorithms through commands, a guided mode, and a small Python API. The Python API needs only the standard library. The commands also use [Rich](https://rich.readthedocs.io/) and [questionary](https://questionary.readthedocs.io/), which are installed automatically. Optional encryption needs one extra library.

> **Without a passphrase, anyone can read, change, or replace a hidden message.** Read [Security](#security) before you hide anything private.

## Requirements

- Python 3.11 or newer
- An uncompressed integer PCM WAV file (8, 16, 24, or 32-bit). The limit for encoding is 1 GiB. Streamed files with no stated audio size and files with padded samples are not supported. A truncated file (shorter than its header says) cannot be used for encoding; it can still be decoded if the whole message is there.

Some PCM files use the "extensible" WAV header. Python 3.11 cannot read that header; Python 3.12 and newer can.

## Install

```bash
git clone https://github.com/sniperline047/Audio-Steganography-CLI.git
cd Audio-Steganography-CLI
python -m venv .venv
source .venv/bin/activate
pip install .
```

On Windows, activate the environment with `.venv\Scripts\activate`.

To encrypt messages, install the `crypto` extra, which adds the [cryptography](https://cryptography.io/) library:

```bash
pip install ".[crypto]"
```

That library has ready-made packages for most systems. On others, such as Macs with Intel processors, pip has to build it and needs extra tools.

## Run

After installing, run one of these from any folder:

```bash
audiosteg
python -m audiosteg
```

With [uv](https://docs.astral.sh/uv/), there is nothing to install first. From the project folder:

```bash
uv run audiosteg
uv run --extra crypto audiosteg
```

The second command adds encryption. From another folder, use `uv run --project path/to/Audio-Steganography-CLI audiosteg`.

Without a command, this starts the [guided mode](#guided-mode).

## Commands

```bash
audiosteg hide sample -m "Hello"
audiosteg reveal sample.stego.wav
audiosteg verify sample.stego.wav -m "Hello"
audiosteg inspect sample.stego.wav
audiosteg compare sample sample.stego.wav
audiosteg explain lsb
audiosteg algorithms
audiosteg --version
```

Add `--help` to any command to see its options and examples. Help is always text, even with `--json`.

The word `sample` as the input of `hide`, `inspect`, `compare`, or `explain --file` means the tune that is included in the package. To use a file named `sample`, write `./sample`.

### hide

Hides a message in a copy of a WAV file. The input file is never changed.

```bash
audiosteg hide song.wav -m "Meet me at noon"
audiosteg hide song.wav -p
audiosteg hide song.wav -a lsb_2 -o secret.wav --message_file letter.txt
printf "Hello" | audiosteg hide song.wav
```

| Option | Meaning |
| --- | --- |
| `-m TEXT`, `--message TEXT` | The message. Other users of the computer and the shell history may see it. |
| `--message_file FILE` | Read the message from a UTF-8 text file |
| `-a`, `--algorithm` | `lsb` (default) or `lsb_2` |
| `-p`, `--passphrase` | Ask for a passphrase, twice, and encrypt the message |
| `--passphrase_file FILE` | Read the passphrase from a file |
| `-o`, `--output` | The new file. The default is the name of the input with `.stego.wav`, in the current folder. |
| `--force` | Replace an existing output file |

An option with a value can also be written as one word, such as `--message=-text`. Do not join short options: `-p` must stand alone.

Without `-m` and `--message_file`, the message is typed in a terminal, or read from a pipe. Files and pipes are hidden exactly as they are, including a newline at the end. `echo` adds such a newline; `printf` does not. Many terminals limit how long a typed line can be, so use a file for a long message.

If the output file exists, a terminal asks before replacing it; anywhere else, such as when stdin or stderr is not a terminal, `--force` is needed. The program refuses to write to the input file, the message or passphrase file, the included sample, or a symbolic link, even with `--force`. Only the audio is copied; tags and other metadata are not.

### reveal

Reads a hidden message. The algorithm is detected.

```bash
audiosteg reveal song.stego.wav
audiosteg reveal song.stego.wav > message.txt
audiosteg reveal song.stego.wav --passphrase_file key.txt
audiosteg reveal old.wav --legacy basic
```

| Option | Meaning |
| --- | --- |
| `-a`, `--algorithm` | `lsb` or `lsb_2`, instead of detecting it |
| `--legacy` | `basic`, `enhanced`, or `enhanced_flip`, for files of older versions, which are not detected |
| `-p`, `--passphrase` | Ask for the passphrase. A terminal asks without this option if the message is encrypted. |
| `--passphrase_file FILE` | Read the passphrase from a file |

Only the message goes to stdout. Everything else, such as whether the message was encrypted, goes to stderr. If you expect an encrypted message and the program says that it was not encrypted, do not trust the message. With a passphrase option, a message that is not encrypted is refused.

In a file or a pipe, the message is written exactly, as UTF-8, with nothing added at the end. A terminal shows characters that could control it as escape codes such as `\x1b`, adds a newline, and shows the line about encryption last. If only stderr is a terminal, that line starts with an empty line, so that the two do not run together. Invisible joiners are also escaped, so some combined emoji appear as separate emoji and a code such as `\u200d`.

### verify

Compares a hidden message with the expected one and changes nothing. It has the options `-m` and `--message_file` of `hide` and all options of `reveal`.

```bash
audiosteg verify song.stego.wav -m "Meet me at noon"
```

The score is the number of matching character positions divided by the longer message length, so missing and extra characters lower it. The exit code is 1 if the messages are not exactly the same.

### inspect

Describes a WAV file: its format, how much each algorithm can hide in it, and whether it holds a message. It never reads or shows a message and never asks for a passphrase.

```bash
audiosteg hide sample -m "Hello"
audiosteg inspect sample.stego.wav
```

```
What this file holds
File: sample.stego.wav
Format: 16-bit PCM WAV
Channels: 2 (stereo)
Sample rate: 22,050 Hz
Duration: 4.281 s (94,400 frames)
Room with lsb: 23,586 bytes, or 23,546 encrypted
Room with lsb_2: 47,186 bytes, or 47,146 encrypted
Hidden message: lsb, not encrypted, 5 bytes
Only the header of the message was read, so damage further on is not detected.
```

`none detected` does not mean that a file has no hidden message: files of older versions and messages of other tools cannot be detected. A header that is damaged or of an unknown version is reported. Because only the header is read, damage in the message itself is found by `reveal`, not here. The exit code is 0 in all these cases.

### compare

Measures how much a copy differs from the original. Both files need the same format and length.

```bash
audiosteg compare sample sample.stego.wav
```

```
Sounds the same? Very likely. The change is far quieter than the sound, but only listening can tell.
Quality:         Excellent (SNR: 106.2 dB)
Changed:         78 of 188,800 samples (0.04%), from 0.000 s to 0.003 s
To see every number, add --details. To listen, add --play.
```

| Option | Meaning |
| --- | --- |
| `--details` | Every metric and the waveforms, each with an explanation |
| `--show NAMES` | Only these, separated by commas: `snr`, `psnr`, `changes`, `where`, `waveform` |
| `--from`, `--to` | Only this part, in seconds. It also limits what is saved and played. |
| `--width COLUMNS` | The width of the waveforms, from 20 to 500. A terminal never gets more than fits. |
| `--play [WHAT]` | Listen to `original`, `encoded`, or `difference`. Without a value, all three in this order. |
| `--gain N` | Amplify the difference `N` times (1 or more). The default is as much as is safe. |
| `--save_difference FILE` | Write the amplified difference to a WAV file |
| `--force` | Replace an existing difference file |

`--play` never takes a file name as its value. For files named `original`, `encoded`, or `difference` after it, write `./original`.

The difference is the encoded audio minus the original. Its largest sample is at least 12 dB below the maximum (-12 dBFS), also with `--gain`. The program says how much it amplified or reduced the difference:

```
Difference saved: difference.wav
  It was amplified 8,230 times. Its loudest sample is at least 12 dB below the maximum.
```

A difference file follows the same rules as the output of `hide`: it never replaces an input, the included sample, or a link. If there is no difference, nothing is written.

Sound is played only with `--play`, by a player that the system already has: `afplay` on macOS, Windows itself, or `aplay`, `paplay`, or `ffplay` in `/usr/bin` or `/usr/local/bin` on Linux. It plays private temporary files, which are removed afterwards. Ctrl-C stops the sound and the program.

#### What the metrics mean

With `--details` (here with `--width 60`):

```
SNR: 106.2 dB
  How much stronger the sound is than the change. Higher is better. In words: Excellent.
PSNR: 124.1 dB
  How much stronger the loudest possible sound is than the change. Higher is better.
Changed samples: 78 of 188,800 samples (0.04%)
  A sample is one number of one channel. Fewer changes are harder to notice.
Largest change: 1 step (less than 0.01% of the largest possible sample)
  How far one sample moved. One step is the smallest change there is.
Where: from 0.000 s to 0.003 s
  The time of the first and the last changed sample.
Changed samples in each tenth: 78, 0, 0, 0, 0, 0, 0, 0, 0, 0
  The compared audio, cut into ten equal parts.
Waveform: original
: .    |:.     | .    |:.     |..    |:.     |..    |:.
||||||:|||||:|.||||||:|||||:|.||||||||||||:|.||||||||||||.|.
||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||
||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||
  The loudest sample at each moment, 0.000 s to 4.281 s.
Waveform: encoded
: .    |:.     | .    |:.     |..    |:.     |..    |:.
||||||:|||||:|.||||||:|||||:|.||||||||||||:|.||||||||||||.|.
||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||
||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||
  The same for the encoded file, at the same scale.
Waveform: difference
|
|
|
|
  The largest change at each moment, enlarged to fill the height.
```

A sample is a whole number where 0 is silence. 8-bit samples are stored from 0 to 255, so 128 is subtracted first. `s` is a sample of the original, `d` is the change of that sample, and all channels count together.

| Metric | Definition | Limits |
| --- | --- | --- |
| SNR | `10 * log10(sum(s^2) / sum(d^2))` dB | An average. A short loud change in a long file can hide in it. There is no SNR if the original is silent. |
| PSNR | `10 * log10(p^2 / mean(d^2))` dB, where `p` is 128, 32768, 8388608, or 2147483648 for 8, 16, 24, or 32 bits | It ignores how loud the audio really is, so quiet audio looks better than it sounds. |
| Changed samples | How many `d` are not 0 | Many tiny changes can be harder to hear than one large change. |
| Largest change | The largest `d` without its sign, also as a percentage of `p` | One step is louder in 8-bit audio than in 16-bit audio. |
| Where | The time of the first changed sample, the end of the last one, and the number of changed samples in each tenth of the audio | A time covers one frame, which is one sample of each channel. |
| Waveform | The largest sample (or change) in each column, without its sign | Very short sounds look as wide as a column. |

The words come from the SNR: Excellent from 70 dB, Good from 50 dB, Fair from 30 dB, and Poor below that or if a silent original changed. Files without any change are Identical. **These limits are this project's choice, not a hearing standard.** They do not consider which sounds cover which others, and no number here can prove what a person hears. If one change passes 1% of the largest possible sample, the summary says that it could be a click. Shown decibels are rounded down. If nothing changed, there is no noise and so no SNR and no PSNR.

### explain

Lists the algorithms, or shows how one of them hides a character in real samples. Every number is computed with the real algorithm. No file is changed.

```bash
audiosteg explain
audiosteg explain lsb
audiosteg explain lsb_2 --letter A --file song.wav
```

This is the output of `audiosteg explain lsb`:

```
LSB (1 bit per sample)
Hides 1 bit in each sample. Best sound quality.

Step 1: turn the character into bits
The character 'h' is 1 byte in UTF-8:
  0x68 = 01101000

Step 2: take real samples
8 samples of the included tune, from 0.012 s on (frame 259).
The hide command itself starts at the first sample and puts a header before the message.

Step 3: put the bits into the samples
These are the bits of the lowest byte of each sample. Changed bits are in [brackets].
  1. hide 0: 0010010[1] -> 0010010[0]  value 12581 -> 12580  -1
  2. hide 1: 1000110[0] -> 1000110[1]  value 9100 -> 9101    +1
  3. hide 1: 1001010[0] -> 1001010[1]  value 12436 -> 12437  +1
  4. hide 0: 1111000[1] -> 1111000[0]  value 8945 -> 8944    -1
  5. hide 1: 01000101   -> 01000101    value 12101 -> 12101  no change
  6. hide 0: 1110111[1] -> 1110111[0]  value 8687 -> 8686    -1
  7. hide 0: 01001000   -> 01001000    value 11592 -> 11592  no change
  8. hide 0: 1000111[1] -> 1000111[0]  value 8335 -> 8334    -1

Step 4: read the bits back
Reading the same bits gives 'h' again.
6 of 8 samples changed, by at most 1 here. This algorithm can change a sample by at most 1, out of 32,768.

Strengths
- The change is the smallest that a sample can have.
- The idea is easy to understand and fast.
Weaknesses
- It holds less than LSB_2.
- Editing, compressing, or converting the audio destroys the message.
- Anyone who looks at the lowest bits can find the message.
Try it
  audiosteg hide sample -m "Hello" -a lsb
  audiosteg compare sample sample.stego.wav --details
```

| Option | Meaning |
| --- | --- |
| `--letter CHARACTER` | The character to hide. The default is `h`. |
| `--file FILE` | Take the samples from this file instead of the included tune |
| `--step` | Wait for Enter after each step. It needs a terminal. |

For an algorithm of older versions, it says why the algorithm was replaced, and the options are not allowed.

### algorithms

Lists the names that `-a` and `--legacy` accept.

### Passphrases

A passphrase is never a value on the command line. `-p` asks for it in the terminal without showing it. A passphrase file must be a regular UTF-8 file. Exactly one newline at its end is removed. `hide` refuses a passphrase that is empty or contains a line break or another control character, because it could not be typed later; `hide` also refuses a file that starts with a byte order mark (BOM). `reveal` and `verify` use what the file holds. If other users can read the file, the program shows a warning (not on Windows).

### Output for programs

Every command accepts these options:

- `--json` writes one JSON document to stdout.
- `--plain` uses no colour and no drawing. This also happens without a terminal, with `TERM=dumb`, and where the encoding cannot show the drawing. The environment variable `NO_COLOR` turns off colour only.

The JSON document has `ok` and `command`, and:

| Result | Other fields |
| --- | --- |
| `hide` | `input`, `output`, `algorithm`, `encrypted` |
| `reveal` | `file`, `algorithm`, `legacy`, `encrypted`, `message` |
| `verify` | `file`, `algorithm`, `legacy`, `encrypted`, `exact_match`, `percentage`, `expected_length`, `found_length` |
| `inspect` | `file`, `bits`, `channels`, `sample_rate`, `frames`, `seconds`, `cannot_hide` (a reason or `null`), `capacity` (a list of `algorithm`, `plain`, `encrypted`), `messages` (a list of `algorithm`, `encrypted`, `size`, `problem`; empty if none was detected) |
| `compare` | `original`, `encoded`, `first_frame`, `frames`, `identical`, `quality`, the numbers below, `difference` (`file` and `gain`, or `null`) |
| `explain` | Without a name, like `algorithms`. With one, `key`, `name`, `bits_per_byte`, `explanation`, `legacy`, and for an old algorithm `replaced_because`, for others `letter`, `utf_8`, `file`, `first_frame`, `silent`, `samples`, `read_back`, `largest_possible_change`, `strengths`, `weaknesses` |
| `algorithms` | `algorithms` and `legacy`: lists of `key`, `name`, `bits_per_byte`, `explanation` |
| `--version` | `version` (`command` is `null`) |
| Error | `error`: `type`, `message`, `hint` (or `null`), `exit_code` |

The numbers of `compare` are `snr_db` and `snr_note`, `psnr_db` and `psnr_note`, then `samples`, `changed_samples`, `changed_percentage`, `largest_change`, `largest_change_percentage`, then `first_changed_frame`, `last_changed_frame`, `changed_by_tenth`. `--show` limits them to its names, in the order `snr`, `psnr`, `changes`, `where`. `waveform` needs `--details` or `--show waveform`; its numbers are from 0 to 1, where 1 is the largest possible sample. A number that does not exist is `null`, and its note says why: `identical` or `silent_original`. `--play` and `--step` cannot be used with `--json`.

`ok` says whether the command finished. If `verify` finds a difference, `ok` is `true`, `exact_match` is `false`, and the exit code is 1. Paths in these fields are as given, except `output`, which is absolute, and the input `sample`, which is shown as the path of the included file. Only `reveal` shows a message. A passphrase is never shown.

The error types are `usage`, `cancelled`, `interrupted`, `input_ended`, `out_of_memory`, `file`, `file_exists`, `file_not_found`, `invalid_value`, `capacity`, `damaged_message`, `invalid_message`, `missing_library`, `no_message`, `not_encrypted`, `passphrase_required`, `unsafe_output`, `unsupported_algorithm`, `unsupported_format`, and `wrong_passphrase`.

### Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Failure, or `verify` found a difference |
| 2 | Wrong usage |
| 130 | Ctrl-C |

If the output is closed (for example, by a pipe such as `| head`), the code is 1. A wrong command line is explained without repeating its words, because one of them may be a secret.

## Guided mode

`audiosteg` without a command shows a menu to hide, reveal, and verify messages, to inspect and compare files, and to explain and list the algorithms. It asks for everything it needs:

- The arrow keys and Enter choose from a menu. Enter at a text question accepts the default in brackets.
- Back, or the Esc key, returns to the question before.
- Ctrl-C leaves with code 130. Ctrl-D at the main menu leaves like Exit. Ctrl-D at any other question leaves with code 1; at a text question, only if nothing is typed yet.
- An empty message and replacing a file must be confirmed: type `y` and Enter.
- A message that does not fit is refused at once, and only algorithms that can hold it are offered.
- Compare asks whether to show three lines, everything, or what you choose. It then offers to play the sounds, if the system has a player.
- After each action, it shows the command that does the same. The message and the passphrase are never part of it. A command is not shown if a file name has characters that a shell could change.

Spaces around a typed path are removed, and `~` means your home folder. The exit code is 1 if an action failed. The guided mode needs a terminal for stdin, stdout, and stderr; without one, the program shows the help and exits with code 2.

### Moving from the numbered menu

The numbered menu of earlier versions is gone, so scripts that typed its numbers must use the commands:

| Menu | Command |
| --- | --- |
| 1) Encode a message | `audiosteg hide` |
| 2) Decode a message | `audiosteg reveal` |
| 3) Calculate accuracy | `audiosteg verify` |
| An algorithm number | `-a lsb` or `-a lsb_2` |
| An old algorithm number | `--legacy basic`, `enhanced_flip`, or `enhanced` |
| `message_encoded.wav` | `INPUT.stego.wav` |

## Use from Python

```python
from audiosteg import NoMessageError, decode, encode
from audiosteg.algorithms.lsb import LSB

encode("input.wav", "output.wav", "Hello", LSB)
try:
    print(decode("output.wav"))
except NoMessageError:
    print("No hidden message was found.")

encode("input.wav", "private.wav", "Hello", LSB, passphrase="correct horse battery staple")
print(decode("private.wav", passphrase="correct horse battery staple"))
```

`decode` detects the algorithm unless you pass one. `encode` refuses to replace an existing output file unless you pass `overwrite=True`.

Every error the package raises on purpose is a `StegoError`, except `ValueError` for a passphrase that is empty, contains a null character, or is not valid text, and `TypeError` for something that is not an algorithm:

| Error | Meaning |
| --- | --- |
| `CapacityError` | The message does not fit |
| `DamagedMessageError` | A message was found, but it was changed or cut off |
| `InvalidMessageError` | The message is not valid text |
| `MissingLibraryError` | Encryption is not available; it usually needs `pip install ".[crypto]"` |
| `NoMessageError` | No message was found |
| `NotEncryptedError` | A passphrase was given, but the message is not encrypted |
| `PassphraseRequiredError` | The message is encrypted and no passphrase was given |
| `UnsafeOutputError` | The output path could damage another file |
| `UnsupportedAlgorithmError` | The algorithm cannot hide new messages |
| `UnsupportedFormatError` | The WAV file or the message format cannot be read |
| `WrongPassphraseError` | Wrong passphrase, or the message was changed |

File problems raise the usual `OSError` types, such as `FileNotFoundError`. A null character in an input path raises `ValueError`.

### Read files from older versions

Files made by older versions are not detected. Choose how they were encoded:

```python
from audiosteg import decode
from audiosteg.algorithms.legacy import BASIC_LSB

print(decode("old.wav", BASIC_LSB))
```

The other choices are `ENHANCED_LSB_FLIP` and `ENHANCED_LSB`, which read each other's files. These algorithms cannot hide new messages.

The oldest of these files stored one byte per character. If a message is not valid UTF-8, it is read as Latin-1, so most old messages still decode. A few old messages with accented letters also happen to be valid UTF-8 and show different characters. The earliest files, which have no length header and are padded with `#`, are not supported.

## Algorithms

| Name | Algorithm | Bits per sample | Largest change to a sample |
| --- | --- | --- | --- |
| `lsb` | `LSB` | 1 (lowest bit) | 1 |
| `lsb_2` | `LSB_2` | 2 (two lowest bits) | 3 |

Both are in `algorithms/lsb.py`. They change only the lowest byte of each sample. The samples of all channels are used in the order in which they are stored.

### Capacity

For an audio file with `n` samples (counting every channel), the largest message is:

| Algorithm | Plain | Encrypted |
| --- | --- | --- |
| `LSB` | `n / 8 - 14` bytes | `n / 8 - 54` bytes |
| `LSB_2` | `2n / 8 - 14` bytes | `2n / 8 - 54` bytes |

The division is rounded down. One character can take up to four UTF-8 bytes.

### Audio quality

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

### Container layout

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

## Project layout

```
Audio-Steganography-CLI/
├── .github/                Automated checks
├── scripts/
│   └── generate_sample_audio.py
├── src/audiosteg/
│   ├── algorithms/
│   │   ├── detection.py    Detection and decode
│   │   ├── legacy.py       Reading files from older versions
│   │   ├── lsb.py          The two algorithms
│   │   └── registry.py     The names of the algorithms
│   ├── analysis/
│   │   ├── difference.py   The amplified difference
│   │   ├── inspection.py   What a file is and holds
│   │   ├── quality.py      The metrics
│   │   ├── samples.py      Samples as numbers, block by block
│   │   ├── walkthrough.py  One character in real samples
│   │   └── waveform.py     The numbers behind a waveform
│   ├── cli/
│   │   ├── commands/       One file per command
│   │   ├── accuracy.py     Message comparison
│   │   ├── compare_view.py Text and JSON of compare
│   │   ├── explain_view.py Text and JSON of explain
│   │   ├── guided/         Guided mode: menu, forms, questions
│   │   ├── errors.py       Plain explanations of errors
│   │   ├── inspect_view.py Text and JSON of inspect
│   │   ├── logo.py         The logo
│   │   ├── main.py         Program entry point
│   │   ├── message_input.py Messages from options, files, and pipes
│   │   ├── options.py      Options that commands share
│   │   ├── parser.py       The command line
│   │   ├── passphrase.py   Passphrases from prompts and files
│   │   ├── player.py       Playing sound
│   │   ├── questions.py    Questions of the commands
│   │   ├── results.py      What the commands found or did
│   │   ├── views.py        Text and JSON output
│   │   └── waveform_view.py Drawing a waveform
│   ├── core/
│   │   ├── algorithm.py    The Algorithm type
│   │   ├── crypto.py       Optional encryption
│   │   ├── header.py       The container around a message
│   │   ├── message_codec.py Message and bit conversion
│   │   ├── stego_file.py   Hiding and reading with one algorithm
│   │   └── wav_io.py       WAV reading and writing
│   ├── data/
│   │   └── sample.wav
│   ├── utils/
│   │   ├── output_path.py  Output path checks
│   │   ├── safe_write.py   One-step file writing
│   │   └── text.py         Safe terminal text
│   ├── __main__.py         Runs python -m audiosteg
│   └── errors.py           Error types
├── tests/                  Same folders as src/audiosteg/
├── LICENSE
├── pyproject.toml
└── requirements_dev.txt
```

Imports point one way: `cli` uses `analysis`, `analysis` uses `algorithms`, `algorithms` uses `core`, and `core` uses `utils`. A folder may also use any folder further along that chain, but never one before it.

`src/audiosteg/data/sample.wav` is an original tune. Run `python scripts/generate_sample_audio.py` to create it again.

## Add an algorithm

A normal `pip install .` copies the code, so later edits have no effect. While you work on the code, install the project in editable mode, or run it with `uv run audiosteg`:

```bash
pip install -e .
```

1. Create `src/audiosteg/algorithms/my_new_algorithm.py`:

   ```python
   """Hide one bit in the second lowest bit of each sample."""

   from audiosteg.core.algorithm import Algorithm


   def embed_bits(byte: int, bits: tuple[int, ...]) -> int:
       """Replace the second lowest bit of a byte."""
       return (byte & 253) | (bits[0] << 1)


   def extract_bits(byte: int) -> tuple[int, ...]:
       """Read the second lowest bit of a byte."""
       return ((byte >> 1) & 1,)


   MY_NEW_ALGORITHM = Algorithm(
       name="My New Algorithm",
       bits_per_byte=1,
       embed_bits=embed_bits,
       extract_bits=extract_bits,
       explanation="Explains the idea in one line.",
       strengths=("Says what it is good at.",),
       weaknesses=("Says what it is bad at.",),
   )
   ```

   The functions get only the lowest byte of each sample. `bits_per_byte` must be 1, 2, 4, or 8. `strengths` and `weaknesses` are optional and shown by `explain`, which computes everything else with the two functions.

2. Import it in `src/audiosteg/algorithms/registry.py` and add one line to `ALGORITHMS`, with the name for the command line:

   ```python
   "my_new_algorithm": MY_NEW_ALGORITHM,
   ```

The commands, the guided mode, detection, the capacity check, and the file handling need no changes.

Detection tries the algorithms in order and stops at the first message. If the input audio already holds a message from an algorithm earlier in the list, that old message can be found instead of the new one. To avoid this, pass the algorithm to `decode`, or use `-a`.

## Moving from the old layout

| Old | New |
| --- | --- |
| `python cli/main.py`, `python -m cli.main` | `audiosteg`, `python -m audiosteg` |
| `basic_lsb_steganography.encode(source, output, message)` | `encode(source, output, message, LSB)` |
| `basic_lsb_steganography.decode(path)` | `decode(path)` for new files, `decode(path, BASIC_LSB)` for old files |
| `from algorithms import basic_lsb_steganography` | `from audiosteg.algorithms.legacy import BASIC_LSB` (read only) |
| `from algorithms import enhanced_lsb_steganography_no_flip` | `from audiosteg.algorithms.legacy import ENHANCED_LSB` (read only) |
| `from algorithms import enhanced_lsb_steganography_with_flip` | `from audiosteg.algorithms.legacy import ENHANCED_LSB_FLIP` (read only) |
| `encode(source, output, message, BASIC_LSB)` | `encode(source, output, message, LSB)` |
| `encode(source, output, message, ENHANCED_LSB)`, `encode(source, output, message, ENHANCED_LSB_FLIP)` | `encode(source, output, message, LSB_2)` |
| `from audiosteg.algorithms.basic_lsb import BASIC_LSB` | `from audiosteg.algorithms.legacy import BASIC_LSB` (read only) |
| `from audiosteg.algorithms.enhanced_lsb import ENHANCED_LSB` | `from audiosteg.algorithms.legacy import ENHANCED_LSB` (read only) |
| `from audiosteg.algorithms.enhanced_lsb_flip import ENHANCED_LSB_FLIP` | `from audiosteg.algorithms.legacy import ENHANCED_LSB_FLIP` (read only) |
| `from audiosteg.core.stego_file import decode` | `from audiosteg import decode` |
| One default output file per algorithm | `INPUT.stego.wav` |
| `input/original_sample.wav` | `src/audiosteg/data/sample.wav` |
| Default files in `output/` | Default files in the current folder |

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements_dev.txt -e ".[crypto]"
ruff check .
ruff format --check .
mypy
pip-audit --skip-editable
pytest --cov
python -m build
```

On Windows, activate the environment with `.venv\Scripts\activate`.

Mark a test that needs the `crypto` extra with `@pytest.mark.needs_crypto`. It is skipped when the library is missing, unless the environment variable `AUDIOSTEG_REQUIRE_CRYPTO` is set. The automated checks run the tests with and without the extra, and set that variable when the extra is installed.

## Contributing

1. Fork the repository.
2. Create a branch (`git checkout -b my_new_feature`).
3. Commit your changes.
4. Push the branch and open a pull request.

## License

[MIT](LICENSE)
