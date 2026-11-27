# Use from Python

[Back to the README](../README.md)

The Python API needs only the standard library, except for encryption, which needs the `crypto` extra, and `ECHO`, which needs the `signal` extra (NumPy).

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

`decode` detects the algorithm unless you pass one. `LSB_KEYED` (from `audiosteg.algorithms.lsb_keyed`) is the exception: `encode` needs a passphrase for it, and without an algorithm, `decode` tries it only if there is a passphrase and no other message is detected. A wrong passphrase then raises `NoMessageError`, because it looks the same as no message. An edited file can raise it too. Without the crypto extra, reading a keyed message raises `MissingLibraryError`, whatever the passphrase is. A file made with `LSB_MATCHING` is read as `LSB`.

`ECHO` (from `audiosteg.algorithms.echo`) is used like the others. `encode` reads the message back before it saves anything, and raises `UnsuitableAudioError` if the sound cannot carry it. Without NumPy, using `ECHO` raises `MissingLibraryError`, and `decode` without an algorithm does not look for its messages. NumPy is imported only when it is needed.

`encode` refuses to replace an existing output file unless you pass `overwrite=True`.

Every error the package raises on purpose is a `StegoError`, except `ValueError` for a passphrase that is empty, contains a null character, or is not valid text, and `TypeError` for something that is not an algorithm:

| Error | Meaning |
| --- | --- |
| `CapacityError` | The message does not fit |
| `DamagedMessageError` | A message was found, but it was changed or cut off |
| `InvalidMessageError` | The message is not valid text |
| `MissingLibraryError` | An optional library is missing: encryption usually needs `pip install ".[crypto]"`, and `ECHO` needs `pip install ".[signal]"` |
| `NoMessageError` | No message was found, the passphrase of a keyed message is wrong, or a file with a keyed message was edited |
| `NotEncryptedError` | A passphrase was given, but the message is not encrypted |
| `PassphraseRequiredError` | The message is encrypted, or the algorithm always encrypts, and no passphrase was given |
| `UnsafeOutputError` | The output path could damage another file |
| `UnsuitableAudioError` | The sound is long enough, but the message could not be read back from it |
| `UnsupportedFormatError` | The WAV file or the message format cannot be read |
| `WrongPassphraseError` | Wrong passphrase, or the message was changed |

File problems raise the usual `OSError` types, such as `FileNotFoundError`. A null character in an input path raises `ValueError`.

## Moving from the old layout

| Old | New |
| --- | --- |
| `python cli/main.py`, `python -m cli.main` | `audiosteg`, `python -m audiosteg` |
| `from audiosteg.core.stego_file import decode` | `from audiosteg import decode` |
| One default output file per algorithm | `INPUT.stego.wav` |
| `input/original_sample.wav` | `src/audiosteg/data/sample.wav` |
| Default files in `output/` | Default files in the current folder |
