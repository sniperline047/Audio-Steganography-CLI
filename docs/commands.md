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
| `-a`, `--algorithm` | `lsb` (default), `lsb_2`, `lsb_4`, `lsb_matching`, `lsb_parity`, `lsb_keyed`, or `echo`. See [Algorithms](file_format.md). |
| `-p`, `--passphrase` | Ask for a passphrase, twice, and encrypt the message. `lsb_keyed` always asks in a terminal. Anywhere else it needs `--passphrase_file`. |
| `--passphrase_file FILE` | Read the passphrase from a file |
| `-o`, `--output` | The new file. The default is the name of the input with `.stego.wav`, in the current folder. |
| `--force` | Replace an existing output file |

An option with a value can also be written as one word, such as `--message=-text`. Do not join short options: `-p` must stand alone.

Without `-m` and `--message_file`, the message is typed in a terminal, or read from a pipe. Files and pipes are hidden exactly as they are, including a newline at the end. `echo` adds such a newline; `printf` does not. Many terminals limit how long a typed line can be, so use a file for a long message.

If the output file exists, a terminal asks before replacing it; anywhere else, such as when stdin or stderr is not a terminal, `--force` is needed. The program refuses to write to the input file, the message or passphrase file, the included sample, or a symbolic link, even with `--force`. Only the audio is copied; tags and other metadata are not.

`echo` needs the `signal` extra (`pip install ".[signal]"`). It holds very little, changes how the file sounds, and does not work with every sound: before anything is saved, `hide` reads the message back from its own result, and refuses the file if that fails. Then use another file or another algorithm. A sound that would become too loud is made quieter as a whole, and `hide` says by how much. The included sample is too short for it. With `echo`, a message of 5 bytes needs at least 9.5 seconds at 44,100 Hz, and an encrypted one about 23. See [echo](file_format.md#echo).

## reveal

Reads a hidden message. The algorithm is detected.

```bash
audiosteg reveal song.stego.wav
audiosteg reveal song.stego.wav > message.txt
audiosteg reveal song.stego.wav --passphrase_file key.txt
```

| Option | Meaning |
| --- | --- |
| `-a`, `--algorithm` | The algorithm, instead of detecting it |
| `-p`, `--passphrase` | Ask for the passphrase. A terminal asks without this option if the message is encrypted. |
| `--passphrase_file FILE` | Read the passphrase from a file |

Only the message goes to stdout. Everything else, such as whether the message was encrypted, goes to stderr. If you expect an encrypted message and the program says that it was not encrypted, do not trust the message. With a passphrase option, a message that is not encrypted is refused.

A message of `lsb_keyed` cannot be detected. If no other message is detected and there is a passphrase option, the passphrase is tried on `lsb_keyed`. With `-a lsb_keyed`, nothing else is tried, and a terminal asks for the passphrase. A wrong passphrase looks the same as a file without a message or an edited file, so the error is the same too.

A message of `echo` is detected only where NumPy is installed, and only if no other algorithm finds one. Elsewhere, the program says that it could not look for one. Detecting it comes before a passphrase is tried on `lsb_keyed`, so a `lsb_keyed` message in a file with an older `echo` message needs `-a lsb_keyed`, which the error suggests.

A message of `lsb_matching` is the same as one of `lsb` to a reader, so it is always reported as `lsb`, even with `-a lsb_matching`.

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
Room with lsb_4: 94,386 bytes, or 94,346 encrypted
Room with lsb_matching: 23,586 bytes, or 23,546 encrypted
Room with lsb_parity: 2,936 bytes, or 2,896 encrypted
Room with lsb_keyed: 23,546 bytes, always encrypted
Room with echo: none, the sound is too short
Hidden message: lsb, not encrypted, 5 bytes
Only the header of the message was read, so damage further on is not detected. A message hidden with lsb_matching looks the same as one hidden with lsb.
```

The room of `echo` is what may fit. The sound decides whether it really does, so it is no promise.

`none detected` does not mean that a file has no hidden message: messages of `lsb_keyed` and messages of other tools cannot be detected. A message of `lsb_matching` is shown as `lsb`. Without NumPy, messages of `echo` are not looked for, and the program says so if it finds no other message. A header that is damaged or of an unknown version is reported. Because only the header is read, damage in the message itself is found by `reveal`, not here. The exit code is 0 in all these cases.

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

`lsb_parity` shows the lowest bits of each group of 8 samples, their parity, and the sample that was chosen. `lsb_matching` shows how whole samples move by +1 or -1. Both choose at random, so the output differs from run to run. `lsb_keyed` shows scattered samples, counted from 0 across all channels. Their order comes from a fixed demo seed that is shown, never from a passphrase.

`echo` hides the character in blocks of sound. It shows the delay of each echo, and the numbers that the message is read from. The picture is the cepstrum of the block with the clearest echo, before and after. The weakest echo that gives every bit is used, or the strongest if none does, so bits can be shown as wrong. Real messages have error correction, which a single character does not. The last digits of the numbers can differ a little between computers. This is the output of `audiosteg explain echo`:

```
Echo (1 bit per block of 1,024 frames)
Hides 1 bit in each block as a short echo. Audible.

Step 1: turn the character into bits
The character 'h' is 1 byte in UTF-8:
  0x68 = 01101000

Step 2: take real sound
8 blocks of 1,024 frames of the included tune, from 0.01175 s on (frame 259).
One block is 46.44 ms long and carries one bit.
The hide command itself starts at the first frame, and adds a header and error correction to the message.

Step 3: add an echo to each block
Each block gets a quiet echo of itself. A short delay means 0, and a longer one means 1.
  1. hide 0: echo after 25 frames (1.13 ms)
  2. hide 1: echo after 50 frames (2.27 ms)
  3. hide 1: echo after 50 frames (2.27 ms)
  4. hide 0: echo after 25 frames (1.13 ms)
  5. hide 1: echo after 50 frames (2.27 ms)
  6. hide 0: echo after 25 frames (1.13 ms)
  7. hide 0: echo after 25 frames (1.13 ms)
  8. hide 0: echo after 25 frames (1.13 ms)
The echo is 40% as strong as the sound. Between blocks it changes smoothly.

Step 4: look for the echoes
An echo makes waves in the spectrum, the list of how loud each pitch is. The cepstrum shows these waves: it is high at the delay of the echo.
The cepstrum of block 2 before, at delays from 15 to 60 frames:
  |                                              
  |                                              
  |     .                         .   |          
  |...::| :|. ...:.          . .::|:..||..::     
             ^25                      ^50
The cepstrum of block 2 after, at delays from 15 to 60 frames:
  |                                   |          
  |                                   |          
  |     .                         .   |          
  |  .:.| :|.  .....        .. .::|..:||...:     
             ^25                      ^50
The higher of the two numbers decides the bit:
  1. at 25:  0.278   at 50:  0.256   read 0, right
  2. at 25: -0.056   at 50:  0.716   read 1, right
  3. at 25: -0.282   at 50:  0.480   read 1, right
  4. at 25:  0.166   at 50: -0.377   read 0, right
  5. at 25: -0.235   at 50:  0.083   read 1, right
  6. at 25:  0.198   at 50: -0.256   read 0, right
  7. at 25:  0.102   at 50: -0.343   read 0, right
  8. at 25:  0.147   at 50: -0.331   read 0, right
8 of 8 bits read right, which gives 'h'.
Every bit was read right. In a whole message, error correction repairs some wrong bits.

Strengths
- The bits are in the sound itself and not in the lowest bits of the samples.
- Error correction repairs some bits that are read wrong.
Weaknesses
- The echo can be heard, like a small room or a slightly metallic sound.
- It holds very little: a minute of CD audio holds about 140 bytes.
- It does not work with every sound, such as silence or pure tones.
- Anyone who looks for echoes can find the message.
Try it
  audiosteg hide song.wav -m "Hello" -a echo
  audiosteg compare song.wav song.stego.wav --details
The file song.wav is one of yours. At 44,100 frames a second, this message needs 9.5 s of it, so the tune sample is too short.
```

## algorithms

Lists the names that `-a` accepts, each with the full name of the algorithm, such as `Enhanced LSB (2 bit)` for `lsb_2`, and one line about it.

## Passphrases

A passphrase is never a value on the command line. `-p` asks for it in the terminal without showing it. A passphrase file must be a regular UTF-8 file. Exactly one newline at its end is removed. `hide` refuses a passphrase that is empty or contains a line break or another control character, because it could not be typed later; `hide` also refuses a file that starts with a byte order mark (BOM). `reveal` and `verify` use what the file holds. If other users can read the file, the program shows a warning (not on Windows).

## Output for programs

Every command accepts these options:

- `--json` writes one JSON document to stdout.
- `--plain` uses no colour and no drawing. This also happens without a terminal, with `TERM=dumb`, and where the encoding cannot show the drawing. The environment variable `NO_COLOR` turns off colour only.

The JSON document has `ok` and `command`, and:

| Result | Other fields |
| --- | --- |
| `hide` | `input`, `output`, `algorithm`, `encrypted`, `gain` (below 1 if the whole file was made quieter, which only `echo` does) |
| `reveal` | `file`, `algorithm`, `encrypted`, `message` |
| `verify` | `file`, `algorithm`, `encrypted`, `exact_match`, `percentage`, `expected_length`, `found_length` |
| `inspect` | `file`, `bits`, `channels`, `sample_rate`, `frames`, `seconds`, `cannot_hide` (a reason or `null`), `capacity` (a list of `algorithm`, `plain`, `encrypted`, `always_encrypted` (if it is `true`, `plain` is 0), and `at_most` (if it is `true`, the sound decides how much really fits)), `messages` (a list of `algorithm`, `encrypted`, `size`, `problem`; empty if none was detected), `not_checked` (the algorithms whose messages could not be looked for without NumPy) |
| `compare` | `original`, `encoded`, `first_frame`, `frames`, `total_frames`, `identical`, `quality`, the numbers below, `difference` (`file`, which is absolute, `gain`, and `capped`, or `null`) |
| `explain` | Without a name, like `algorithms`. With one, `key`, `name`, `bits_per_byte`, `explanation`, `samples_per_group`, `needs_passphrase`, `reads_like`, `frames_per_bit`, `letter`, `utf_8`, `file`, `first_frame`, `silent`, `how`, `demo_seed`, `samples`, `groups`, `read_back`, `largest_possible_change`, `strengths`, `weaknesses`. For `echo` also `delays`, `level`, `gain`, `blocks` |
| `algorithms` | `algorithms`: a list of `key`, `name`, `bits_per_byte`, `explanation`, `samples_per_group`, `needs_passphrase`, `reads_like` (the algorithm that its messages are reported as, or `null`), and `frames_per_bit` (`null` unless whole blocks of sound carry the bits) |
| `--version` | `version` (`command` is `null`) |
| Error | `error`: `type`, `message`, `hint` (or `null`), `exit_code` |

The numbers of `compare` are `snr_db` and `snr_note`, `psnr_db` and `psnr_note`, then `samples`, `changed_samples`, `changed_percentage`, `largest_change`, `largest_change_percentage`, then `first_changed_frame`, `last_changed_frame`, `changed_by_tenth`. `--show` limits them to its names, in the order `snr`, `psnr`, `changes`, `where`. `waveform` needs `--details` or `--show waveform`; it has 80 columns, or `--width`, or fewer for very short audio, whatever the terminal is. Its numbers are shares of the largest possible sample: 0 to 1, and up to almost 2 for the difference. A number that does not exist is `null`, and its note says why: `identical` or `silent_original`. `--play` and `--step` cannot be used with `--json`.

`bits_per_byte` is the number of bits in each group of `samples_per_group` samples. In `explain`, every item of `samples` has `hidden_bits` (of its whole group), `low_byte_before`, `low_byte_after`, `value_before`, `value_after`, `change`, `position` (counted from 0 across all channels), and `group` (from 1). `groups` is empty unless the groups carry a parity (`lsb_parity`). Every item has `group`, `hidden_bits`, `lowest_bits_before`, `lowest_bits_after`, and `changed_sample` (its first changed sample, counted from 1 in the group, or `null`). `demo_seed` is `null` for algorithms without a passphrase. `first_frame` is the earliest frame used.

With `echo`, `samples_per_group` counts the samples of one channel, `samples` and `groups` are empty, and `demo_seed` and `largest_possible_change` are `null`. `read_back` is `null` if the bits that are read are no character. `delays` are the delays for 0 and 1 in frames, `level` is how strong the echo is, and `gain` is below 1 if everything was made quieter. Every item of `blocks` has `block` (from 1), `hidden_bit`, `delay`, `peaks_before` and `peaks_after` (the cepstrum at both delays), and `read_bit`.

`ok` says whether the command finished. If `verify` finds a difference, `ok` is `true`, `exact_match` is `false`, and the exit code is 1. Paths in these fields are as given, except `output` and the file of `difference`, which are absolute, and the input `sample`, which is shown as the path of the included file. Only `reveal` shows a message. A passphrase is never shown.

The error types are `usage`, `cancelled`, `interrupted`, `input_ended`, `out_of_memory`, `file`, `file_exists`, `file_not_found`, `invalid_value`, `capacity`, `damaged_message`, `invalid_message`, `missing_library`, `no_message`, `not_encrypted`, `passphrase_required`, `unsafe_output`, `unsuitable_audio`, `unsupported_format`, and `wrong_passphrase`.

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
- `lsb_keyed` always asks for a passphrase. If no message is detected in a file, Reveal and Verify offer another file or `lsb_keyed`. After a passphrase that finds nothing, try another or go back.
- If a passphrase does not open an `echo` message, try another or look for a `lsb_keyed` message in the same file.
- `echo` is offered if the file is long enough. If not, the program says that the sound is too short. Without NumPy, the menus say `needs NumPy` next to it, and choosing it says how to install it.
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
| `message_encoded.wav` | `INPUT.stego.wav` |

## Audio files

- An uncompressed integer PCM WAV file (8, 16, 24, or 32-bit). The limit for encoding is 1 GiB. Streamed files with no stated audio size and files with padded samples are not supported. A truncated file (shorter than its header says) cannot be used for encoding; it can still be decoded if the whole message is there.

Some PCM files use the "extensible" WAV header. Python 3.11 cannot read that header; Python 3.12 and newer can.
