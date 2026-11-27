<div align="center">

<img src="docs/logo.svg" alt="An 8-bit cassette with a key hidden in its tape" width="300">

# Audio Steganography CLI

**Hide messages in sound, and see how it works.**

[![Test coverage](https://github.com/sniperline047/Audio-Steganography-CLI/raw/coverage_badge/coverage.svg)](https://github.com/sniperline047/Audio-Steganography-CLI/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-ee6c4d.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-2a9d8f.svg)](https://www.python.org/)

[Install](#install) · [Interactive mode](#interactive-mode) · [Commands](#commands) · [Arguments](#arguments) · [Explain mode](#explain-mode) · [Go deeper](#go-deeper)

</div>

> *"I solemnly swear that I am up to no good."*

Say that to the Marauder's Map and blank parchment turns into a secret map of Hogwarts. This project does something similar with sound: to most ears it's a little tune, but you know it's hiding a message.

```bash
audiosteg hide sample -m "I solemnly swear that I am up to no good." -o map.wav
audiosteg reveal map.wav
```

```
I solemnly swear that I am up to no good.
```

**How is that possible?** Digital sound is a long list of numbers, called samples. Changing a number from 12,581 to 12,580 makes a difference so small that you are very unlikely to hear it. Make many of those tiny changes and you can spell out a message. Hiding a message inside something ordinary is called **steganography**. No wand needed.

With it you can:

- 🤫 **Hide** a message in a WAV file, and **reveal** it again
- 🔐 **Lock** it with a passphrase
- 🔍 **Inspect** a file for hidden messages
- 🎧 **Compare** the original with the copy, by numbers or by ear
- 🎓 **Learn** how it works, bit by bit

> [!WARNING]
> **Without a passphrase, anyone can read, change, or replace your message.** This is a learning project that has not been audited, so don't trust it with real secrets. See [Security](docs/file_format.md#security).

## Install

You need [Git](https://git-scm.com/) and [Python](https://www.python.org/downloads/) 3.11 or newer. Download the project first:

```bash
git clone https://github.com/sniperline047/Audio-Steganography-CLI.git
cd Audio-Steganography-CLI
```

Then pick **one** way to install it.

### With uv (easiest)

With [uv](https://docs.astral.sh/uv/getting-started/installation/), the `audiosteg` command works from any folder:

```bash
uv tool install --editable ".[crypto]"
audiosteg --version
```

If your terminal can't find `audiosteg`, run `uv tool update-shell` and open a new terminal. Keep the downloaded folder: the command runs from it.

### With pip

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install ".[crypto]"
audiosteg --version
```

On Windows, use `py -m venv .venv` and `.venv\Scripts\activate` for the first two lines. With pip, activate the environment again in every new terminal.

<details>
<summary><b>Good to know</b></summary>

- `".[crypto,signal]"` adds the `echo` algorithm too, through [NumPy](https://numpy.org/). Everything else works without it.
- `[crypto]` adds encryption through the [cryptography](https://cryptography.io/) library. If it won't install, for example on a Mac with an Intel processor, use `.` instead of `".[crypto]"`. Everything except passphrases still works.
- To try it without installing, from the project folder: `uv run --extra crypto audiosteg`.
- With pip, `python -m audiosteg` does the same as `audiosteg`.

</details>

## Interactive mode

New here? Start with this. No spells to memorise:

```bash
audiosteg
```

A menu opens and asks for everything it needs:

```
What would you like to do?
  Hide a message
  Reveal a message
  Verify a message
  Inspect a file
  Compare two files
  Explain an algorithm
  List the algorithms
  Exit
```

| Key | What it does |
| --- | --- |
| ↑ ↓ | Move through the menu |
| Enter | Choose, or accept the answer in brackets |
| Esc | Go back one question |
| Ctrl-C | Leave (mischief managed) |

After most actions, the menu shows **the command that does the same**, so you learn the commands as you go. Your message and passphrase are never part of it.

To see the cassette on the welcome screen, use a terminal with 24-bit colour and at least 80 columns.

## Commands

Know what you want? Skip the menu. Each command does one job and exits.

`sample` is a tune that comes with the project. Use your own `.wav` file in its place whenever you like.

### 1. Hide a message

```bash
audiosteg hide sample -m "I solemnly swear that I am up to no good." -o map.wav
```

`map.wav` is a new file in the folder you are in. The original is never changed.

### 2. Reveal it

```bash
audiosteg reveal map.wav
```

```
I solemnly swear that I am up to no good.
```

The program also reminds you that the message was not encrypted.

### 3. Lock it with a passphrase

Now anyone who tries your map without the passphrase is turned away:

```bash
audiosteg hide sample -m "I solemnly swear that I am up to no good." -o locked.wav -p
audiosteg reveal locked.wav
```

Both commands ask for the passphrase and don't show it while you type. `mischief-managed` is fun for practice, but pick a long one of your own for anything else: the whole internet knows that one. A lost passphrase can't be recovered.

The passphrase hides what the message says, not that there is one. Anyone can still find it with `inspect`, remove it, or replace it with another. (`inspect` can't find messages hidden with `-a lsb_keyed`.)

### 4. Check it arrived unchanged

```bash
audiosteg verify map.wav -m "I solemnly swear that I am up to no good."
```

### 5. Look for a hidden message

```bash
audiosteg inspect map.wav
```

```
What this file holds
File: map.wav
Format: 16-bit PCM WAV
Channels: 2 (stereo)
Sample rate: 22,050 Hz
Duration: 4.2812 s (94,400 frames)
Room with lsb: 23,586 bytes, or 23,546 encrypted
Room with lsb_2: 47,186 bytes, or 47,146 encrypted
Room with lsb_4: 94,386 bytes, or 94,346 encrypted
Room with lsb_matching: 23,586 bytes, or 23,546 encrypted
Room with lsb_parity: 2,936 bytes, or 2,896 encrypted
Room with lsb_keyed: 23,546 bytes, always encrypted
Room with echo: none, the sound is too short
Hidden message: lsb, not encrypted, 41 bytes
Only the header of the message was read, so damage further on is not detected. A message hidden with lsb_matching looks the same as one hidden with lsb.
```

### 6. Compare the two sounds

```bash
audiosteg compare sample map.wav
```

```
Sounds the same? Very likely. The change is far quieter than the sound, but only listening can tell.
Quality:         Excellent (SNR: 101.7 dB)
Changed:         218 of 188,800 samples (0.11%), from 0.000 s to 0.010 s
To see every number, add --details. To listen, add --play.
```

Want to hear it? `--play` plays the original, the copy, and then the difference between them, made louder:

```bash
audiosteg compare sample map.wav --play
```

> [!TIP]
> Share the file as a WAV. Converting it to MP3, editing it, or sending it through an app that compresses audio wipes the map clean.

## Arguments

These are the ones you'll use most. Add `--help` to any command to see them all, or read the [full command reference](docs/commands.md).

| Command | Argument | What it does |
| --- | --- | --- |
| `hide`, `verify` | `-m "TEXT"` | The message, or the one you expect |
| `hide`, `verify` | `--message_file FILE` | Take the message from a text file |
| `hide` | `-o FILE` | The name of the new file |
| `hide` | `--force` | Replace a file that already exists |
| `hide`, `reveal`, `verify` | `-a lsb` | Choose the algorithm, by a name from the table below. `reveal` and `verify` usually find it themselves. |
| `hide`, `reveal`, `verify` | `-p` | Ask for a passphrase |
| `hide`, `reveal`, `verify` | `--passphrase_file FILE` | Take the passphrase from a file |
| `compare` | `--details` | Show and explain every number, with waveforms |
| `compare` | `--show snr,where` | Show only what you choose |
| `compare` | `--from 0 --to 0.2` | Look at one part, in seconds |
| `compare` | `--play` | Listen |
| `compare` | `--save_difference FILE` | Save the difference as a sound |
| `explain` | `--letter M` | The character to hide |
| `explain` | `--file FILE` | Use samples from your own file |
| `explain` | `--step` | Go one step at a time |
| any | `--json` | Output for other programs |
| any | `--plain` | No colour, no drawing |

`-m` can end up in your shell history. For anything private, leave it out, and `hide` asks you to type the message instead.

**Which algorithm?**

| Name | What it does | Choose it for |
| --- | --- | --- |
| `lsb` (default) | Hides 1 bit in each sample | The best sound |
| `lsb_2` | Hides 2 bits in each sample | Longer messages, with a little more noise |
| `lsb_4` | Hides 4 bits in each sample | The longest messages, with the most noise |
| `lsb_matching` | Adds or subtracts 1 instead of replacing a bit | Leaving less of a pattern. It is read as `lsb`. |
| `lsb_parity` | Hides 1 bit in each group of 8 samples | Short messages, with the changes spread out |
| `lsb_keyed` | Encrypts the message and scatters its bits with your passphrase | A map that `inspect` can't even find. Add `-p` to read it. |
| `echo` | Hides 1 bit in each block of 1,024 frames, as a short echo you can hear | Seeing how sound itself can carry a message. Very little room; needs `[signal]` and your own longer file. |

## Explain mode

Welcome to class. `explain` takes one letter and hides it in real samples in front of you. Let's use **M**, for Marauder:

```bash
audiosteg explain lsb --letter M --step
```

Press Enter to move to the next step. The letter first becomes eight bits, `01001101`, and then each bit goes into a sample:

```
Step 3: put the bits into the samples
These are the bits of the lowest byte of each sample. Changed bits are in [brackets].
  1. hide 0: 0010010[1] -> 0010010[0]  value 12581 -> 12580  -1
  2. hide 1: 1000110[0] -> 1000110[1]  value 9100 -> 9101    +1
  3. hide 0: 10010100   -> 10010100    value 12436 -> 12436  no change
  4. hide 0: 1111000[1] -> 1111000[0]  value 8945 -> 8944    -1
  5. hide 1: 01000101   -> 01000101    value 12101 -> 12101  no change
  6. hide 1: 11101111   -> 11101111    value 8687 -> 8687    no change
  7. hide 0: 01001000   -> 01001000    value 11592 -> 11592  no change
  8. hide 1: 10001111   -> 10001111    value 8335 -> 8335    no change

Step 4: read the bits back
Reading the same bits gives 'M' again.
3 of 8 samples changed, by at most 1 here. This algorithm can change a sample by at most 1, out of 32,768.
```

Read line 1 like this: the bit to hide is `0`, but the sample ends in `1`. So its last bit changes to `0`, and the value drops from 12,581 to 12,580. In line 3 the last bit is already right, so nothing changes.

**Homework:**

```bash
audiosteg explain
audiosteg explain lsb_2 --letter M
audiosteg explain basic
```

They list every algorithm, show how two bits fit in each sample, and tell you why the project's first algorithm was retired.

## Go deeper

| Page | What's in it |
| --- | --- |
| [Commands](docs/commands.md) | Every option, the menu, JSON, exit codes, supported audio files |
| [Metrics](docs/metrics.md) | What SNR and the other numbers mean, and what they can't tell you |
| [Algorithms and file format](docs/file_format.md) | How much fits, sound quality, every byte of the format, security |
| [Use from Python](docs/python_api.md) | The Python API, files from older versions, moving from the old layout |
| [Contributing](CONTRIBUTING.md) | Project layout, development, adding your own algorithm |

## License

[MIT](LICENSE) © 2019-2026 sniperline047. This is a learning project with no connection to Harry Potter or its owners.

*Mischief managed.*
