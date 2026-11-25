# Use from Python

[Back to the README](../README.md)

The Python API needs only the standard library, except for encryption, which needs the `crypto` extra.

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

`decode` detects the algorithm unless you pass one. `LSB_KEYED` (from `audiosteg.algorithms.lsb_keyed`) is the exception: `encode` needs a passphrase for it, and without an algorithm, `decode` tries it only if there is a passphrase and no other message is detected. A wrong passphrase then raises `NoMessageError`, because it looks the same as no message. A file made with `LSB_MATCHING` is read as `LSB`.

`encode` refuses to replace an existing output file unless you pass `overwrite=True`.

Every error the package raises on purpose is a `StegoError`, except `ValueError` for a passphrase that is empty, contains a null character, or is not valid text, and `TypeError` for something that is not an algorithm:

| Error | Meaning |
| --- | --- |
| `CapacityError` | The message does not fit |
| `DamagedMessageError` | A message was found, but it was changed or cut off |
| `InvalidMessageError` | The message is not valid text |
| `MissingLibraryError` | Encryption is not available; it usually needs `pip install ".[crypto]"` |
| `NoMessageError` | No message was found, or the passphrase of a keyed message is wrong |
| `NotEncryptedError` | A passphrase was given, but the message is not encrypted |
| `PassphraseRequiredError` | The message is encrypted, or the algorithm always encrypts, and no passphrase was given |
| `UnsafeOutputError` | The output path could damage another file |
| `UnsupportedAlgorithmError` | The algorithm cannot hide new messages |
| `UnsupportedFormatError` | The WAV file or the message format cannot be read |
| `WrongPassphraseError` | Wrong passphrase, or the message was changed |

File problems raise the usual `OSError` types, such as `FileNotFoundError`. A null character in an input path raises `ValueError`.

## Read files from older versions

Files made by older versions are not detected. Choose how they were encoded:

```python
from audiosteg import decode
from audiosteg.algorithms.legacy import BASIC_LSB

print(decode("old.wav", BASIC_LSB))
```

The other choices are `ENHANCED_LSB_FLIP` and `ENHANCED_LSB`, which read each other's files. These algorithms cannot hide new messages.

The oldest of these files stored one byte per character. If a message is not valid UTF-8, it is read as Latin-1, so most old messages still decode. A few old messages with accented letters also happen to be valid UTF-8 and show different characters. The earliest files, which have no length header and are padded with `#`, are not supported.

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
