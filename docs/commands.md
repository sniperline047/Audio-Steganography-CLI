# Commands

[Back to the README](../README.md)

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

## hide

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

## reveal

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

## verify

Compares a hidden message with the expected one and changes nothing. It has the options `-m` and `--message_file` of `hide` and all options of `reveal`.

```bash
audiosteg verify song.stego.wav -m "Meet me at noon"
```

The score is the number of matching character positions divided by the longer message length, so missing and extra characters lower it. The exit code is 1 if the messages are not exactly the same.

## inspect

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
Duration: 4.2812 s (94,400 frames)
Room with lsb: 23,586 bytes, or 23,546 encrypted
Room with lsb_2: 47,186 bytes, or 47,146 encrypted
Hidden message: lsb, not encrypted, 5 bytes
Only the header of the message was read, so damage further on is not detected.
```

`none detected` does not mean that a file has no hidden message: files of older versions and messages of other tools cannot be detected. A header that is damaged or of an unknown version is reported. Because only the header is read, damage in the message itself is found by `reveal`, not here. The exit code is 0 in all these cases.

## compare

Measures how much a copy differs from the original. Both files need the same format and length.

```bash
audiosteg compare sample sample.stego.wav
```

```
Sounds the same? Very likely. The change is far quieter than the sound, but only listening can tell.
Quality:         Excellent (SNR: 106.2 dB)
Changed:         78 of 188,800 samples (0.04%), from 0.000 s to 0.00345 s
To see every number, add --details. To listen, add --play.
```

| Option | Meaning |
| --- | --- |
| `--details` | Every metric and the waveforms, each with an explanation |
| `--show NAMES` | Only these, separated by commas or with several `--show`: `snr`, `psnr`, `changes`, `where`, `waveform` |
| `--from`, `--to` | Only this part, in seconds. It also limits what is saved and played. The result then names the part. |
| `--width COLUMNS` | The width of the waveforms, from 20 to 500. A terminal never gets more than fits. |
| `--play [WHAT]` | Listen to `original`, `encoded`, or `difference`. Without a value, all three in this order. |
| `--gain N` | Amplify the difference `N` times (1 or more). The default is as much as is safe. |
| `--save_difference FILE` | Write the amplified difference to a WAV file |
| `--force` | Replace an existing difference file |

`--play` never takes a file name as its value. For files named `original`, `encoded`, or `difference` after it, write `./original`.

The difference is the encoded audio minus the original. Its largest sample is at least 12 dB below the maximum (-12 dBFS), also with `--gain`, and a larger gain is capped. The program says how much it amplified or reduced the difference:

```
Difference saved: difference.wav
  It was amplified 8,230 times. Its loudest sample is at least 12 dB below the maximum.
```

A difference file follows the same rules as the output of `hide`: it never replaces an input, the included sample, or a link. If there is no difference, nothing is written.

Sound is played only with `--play`, by a player that the system already has: `afplay` on macOS, Windows itself, or `aplay`, `paplay`, or `ffplay` in `/usr/bin` or `/usr/local/bin` on Linux. It plays private temporary files, which are removed afterwards. Ctrl-C stops the sound and the program. If the program is asked to end while it plays (SIGTERM or SIGHUP), it stops the sound, removes the file, and exits with 143 or 129.

The numbers are explained in [What the metrics mean](metrics.md).

## explain

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
8 samples of the included tune, from 0.01175 s on (frame 259).
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

## algorithms

Lists the names that `-a` and `--legacy` accept.

## Passphrases

A passphrase is never a value on the command line. `-p` asks for it in the terminal without showing it. A passphrase file must be a regular UTF-8 file. Exactly one newline at its end is removed. `hide` refuses a passphrase that is empty or contains a line break or another control character, because it could not be typed later; `hide` also refuses a file that starts with a byte order mark (BOM). `reveal` and `verify` use what the file holds. If other users can read the file, the program shows a warning (not on Windows).

## Output for programs

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
| `compare` | `original`, `encoded`, `first_frame`, `frames`, `total_frames`, `identical`, `quality`, the numbers below, `difference` (`file`, which is absolute, `gain`, and `capped`, or `null`) |
| `explain` | Without a name, like `algorithms`. With one, `key`, `name`, `bits_per_byte`, `explanation`, `legacy`, and for an old algorithm `replaced_because`, for others `letter`, `utf_8`, `file`, `first_frame`, `silent`, `samples`, `read_back`, `largest_possible_change`, `strengths`, `weaknesses` |
| `algorithms` | `algorithms` and `legacy`: lists of `key`, `name`, `bits_per_byte`, `explanation` |
| `--version` | `version` (`command` is `null`) |
| Error | `error`: `type`, `message`, `hint` (or `null`), `exit_code` |

The numbers of `compare` are `snr_db` and `snr_note`, `psnr_db` and `psnr_note`, then `samples`, `changed_samples`, `changed_percentage`, `largest_change`, `largest_change_percentage`, then `first_changed_frame`, `last_changed_frame`, `changed_by_tenth`. `--show` limits them to its names, in the order `snr`, `psnr`, `changes`, `where`. `waveform` needs `--details` or `--show waveform`; it has 80 columns, or `--width`, or fewer for very short audio, whatever the terminal is. Its numbers are shares of the largest possible sample: 0 to 1, and up to almost 2 for the difference. A number that does not exist is `null`, and its note says why: `identical` or `silent_original`. `--play` and `--step` cannot be used with `--json`.

`ok` says whether the command finished. If `verify` finds a difference, `ok` is `true`, `exact_match` is `false`, and the exit code is 1. Paths in these fields are as given, except `output` and the file of `difference`, which are absolute, and the input `sample`, which is shown as the path of the included file. Only `reveal` shows a message. A passphrase is never shown.

The error types are `usage`, `cancelled`, `interrupted`, `input_ended`, `out_of_memory`, `file`, `file_exists`, `file_not_found`, `invalid_value`, `capacity`, `damaged_message`, `invalid_message`, `missing_library`, `no_message`, `not_encrypted`, `passphrase_required`, `unsafe_output`, `unsupported_algorithm`, `unsupported_format`, and `wrong_passphrase`.

## Exit codes

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
- After each action, it shows the command that does the same. The message and the passphrase are never part of it. A command is not shown if a file name or another answer has characters that a shell could change.

Spaces around a typed path are removed, and `~` means your home folder. The exit code is 1 if an action failed. The guided mode needs a terminal for stdin, stdout, and stderr; without one, the program shows the help and exits with code 2.

## Moving from the numbered menu

The numbered menu of earlier versions is gone, so scripts that typed its numbers must use the commands:

| Menu | Command |
| --- | --- |
| 1) Encode a message | `audiosteg hide` |
| 2) Decode a message | `audiosteg reveal` |
| 3) Calculate accuracy | `audiosteg verify` |
| An algorithm number | `-a lsb` or `-a lsb_2` |
| An old algorithm number | `--legacy basic`, `enhanced_flip`, or `enhanced` |
| `message_encoded.wav` | `INPUT.stego.wav` |

## Audio files

- Python 3.11 or newer
- An uncompressed integer PCM WAV file (8, 16, 24, or 32-bit). The limit for encoding is 1 GiB. Streamed files with no stated audio size and files with padded samples are not supported. A truncated file (shorter than its header says) cannot be used for encoding; it can still be decoded if the whole message is there.

Some PCM files use the "extensible" WAV header. Python 3.11 cannot read that header; Python 3.12 and newer can.
