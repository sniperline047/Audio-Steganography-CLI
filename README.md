# Audio Steganography CLI

[![Test coverage](https://github.com/sniperline047/Audio-Steganography-CLI/raw/coverage_badge/coverage.svg)](https://github.com/sniperline047/Audio-Steganography-CLI/actions/workflows/tests.yml)

A learning project that hides a text message inside a WAV file and reads it back. It offers three least significant bit (LSB) algorithms through an interactive menu and a small Python API, and needs only the Python standard library.

> **Messages are not encrypted or authenticated.** Anyone who knows the algorithm can read a hidden message, change it, or replace it. Do not use this project to protect real secrets.

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

## Run

After installing, run one of these from any folder:

```bash
audiosteg
python -m audiosteg
```

With [uv](https://docs.astral.sh/uv/), there is nothing to install first. From the project folder:

```bash
uv run audiosteg
```

From another folder, use `uv run --project path/to/Audio-Steganography-CLI audiosteg`.

The menu has four options:

1. **Encode a message**
2. **Decode a message**
3. **Calculate accuracy**
4. **Exit**

At a path prompt, press Enter to use the default file shown in brackets, or type another path. Spaces around a typed path are removed, so a path cannot start or end with spaces. `~` means your home folder. To use a file whose name starts with `~`, type `./` before it.

The program exits with code 0 when every operation succeeded, 1 when an operation failed or the input ended in the middle of one, and 130 after Ctrl-C. If the output is closed (for example, by a pipe such as `| head`), it stops with code 1 without starting another operation.

### Encode a message

1. Choose **Encode a message**, then an algorithm. After an invalid choice, the program asks again. Choose **Back** to return to the main menu.
2. Type the secret message.
3. Choose the input audio file. The default is the sample tune that is included in the package.
4. Choose the output audio file. The default is a file in the current folder, and its name depends on the algorithm (see below).
5. If the output file exists, confirm that it may be overwritten. The default answer is no.

The input file is never changed. The program refuses to write to the input file or to a symbolic link. Only the audio is copied; tags and other metadata are not.

### Decode a message

1. Choose **Decode a message**, then the algorithm that was used to encode.
2. Choose the encoded audio file. The default is that algorithm's output file in the current folder.

Characters that could control the terminal are shown as escape codes such as `\x1b`. This only changes the display; the hidden message stays the same. Invisible joiners are also escaped, so some combined emoji appear as separate emoji and a code such as `\u200d`.

### Calculate accuracy

1. Choose **Calculate accuracy**.
2. Type the expected message, then choose the algorithm.
3. Choose the encoded audio file.

This reads an existing file and changes nothing. The score is the number of matching character positions divided by the longer message length, so missing and extra characters lower it. The program also says whether the messages match exactly.

## Use from Python

```python
from audiosteg import NoMessageError, decode, encode
from audiosteg.algorithms.basic_lsb import BASIC_LSB

encode("input.wav", "output.wav", "Hello", BASIC_LSB)
try:
    print(decode("output.wav", BASIC_LSB))
except NoMessageError:
    print("No hidden message was found.")
```

`encode` refuses to replace an existing output file unless you pass `overwrite=True`. Every error the package raises on purpose is a `StegoError`: `CapacityError`, `InvalidMessageError`, `NoMessageError`, `UnsafeOutputError`, or `UnsupportedFormatError`. File problems raise the usual `OSError` types, such as `FileNotFoundError`. A null character in an input path raises `ValueError`.

## Algorithms

Each algorithm first stores the message length in bits as a 32-bit number, then the message as UTF-8 text.

Older versions stored one byte per character. If a message is not valid UTF-8, it is read as Latin-1, so most old messages still decode. A few old messages with accented letters also happen to be valid UTF-8 and show different characters. The earliest files, which have no length header and are padded with `#`, are not supported.

| Menu | Algorithm | Bits per sample byte | Code | Default output |
| --- | --- | --- | --- | --- |
| 1 | Basic LSB Steganography | 1 (lowest bit) | `algorithms/basic_lsb.py` | `basic_lsb_encoded.wav` |
| 2 | Enhanced LSB Steganography with Bit Flipping | 2 (third and fourth lowest bits) | `algorithms/enhanced_lsb_flip.py` | `enhanced_lsb_encoded_flip.wav` |
| 3 | Enhanced LSB Steganography without Bit Flipping | 2 (third and fourth lowest bits) | `algorithms/enhanced_lsb.py` | `enhanced_lsb_encoded_no_flip.wav` |

Algorithms 2 and 3 can read each other's files because they store the message in the same two bits. They differ only in the two lowest bits, which decoding ignores.

The with-flip version also inverts the two lowest bits of every byte whose hidden bits change.

### Capacity

For an audio file with `n` sample bytes, the largest message is:

- Basic: `(n - 32) / 8` bytes
- Enhanced: `(2n - 32) / 8` bytes

Both are rounded down. One character can take up to four UTF-8 bytes.

### Audio quality

"Enhanced" means twice the capacity, not better quality. A 1 KB message gave these signal-to-noise ratios (higher is better). Results change slightly with the message.

| Algorithm | Previous sample | Current sample |
| --- | --- | --- |
| Basic | 50.0 dB | 44.0 dB |
| Enhanced without flipping | 32.3 dB | 27.9 dB |
| Enhanced with flipping | 30.0 dB | 27.6 dB |

The message is written into sample bytes in order, including the high byte of 16-bit samples, so the start of the file can have audible noise. None of them is designed to resist detection.

## Project layout

```
Audio-Steganography-CLI/
├── .github/                Automated checks
├── scripts/
│   └── generate_sample_audio.py
├── src/audiosteg/
│   ├── algorithms/         The three algorithms, one per file
│   ├── cli/
│   │   ├── accuracy.py     Message comparison
│   │   ├── main.py         Program entry point
│   │   └── prompts.py      Menus and prompts
│   ├── core/
│   │   ├── algorithm.py    The Algorithm type
│   │   ├── message_codec.py Message and bit conversion
│   │   ├── registry.py     The numbered list of algorithms
│   │   ├── stego_file.py   encode and decode
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

Imports point one way: `cli` uses `core` and `algorithms`, and these use `utils`. `core` never imports `cli`.

`src/audiosteg/data/sample.wav` is an original tune. Run `python scripts/generate_sample_audio.py` to create it again.

## Add an algorithm

1. Create `src/audiosteg/algorithms/my_new_algorithm.py`:

   ```python
   """Hide one bit in the second lowest bit of each sample byte."""

   from audiosteg.core.algorithm import Algorithm


   def embed_bits(byte: int, bits: tuple[int, ...]) -> int:
       """Replace the second lowest bit of a sample byte."""
       return (byte & 253) | (bits[0] << 1)


   def extract_bits(byte: int) -> tuple[int, ...]:
       """Read the second lowest bit of a sample byte."""
       return ((byte >> 1) & 1,)


   MY_NEW_ALGORITHM = Algorithm(
       name="My New Algorithm",
       bits_per_byte=1,
       embed_bits=embed_bits,
       extract_bits=extract_bits,
       output_file_name="my_new_algorithm_encoded.wav",
   )
   ```

   `bits_per_byte` must be 1, 2, 4, or 8.

2. Import it in `src/audiosteg/core/registry.py` and add one line to `ALGORITHMS` with the next number:

   ```python
   4: MY_NEW_ALGORITHM,
   ```

The menu, the capacity check, and the file handling need no changes.

## Moving from the old layout

| Old | New |
| --- | --- |
| `python cli/main.py`, `python -m cli.main` | `audiosteg`, `python -m audiosteg` |
| `basic_lsb_steganography.encode(source, output, message)` | `encode(source, output, message, BASIC_LSB)` |
| `basic_lsb_steganography.decode(path)` | `decode(path, BASIC_LSB)` |
| `encode(input_file_path=…, output_file_path=…, secret_message=…)` | `encode(input_path=…, output_path=…, message=…, algorithm=…)` |
| `decode(input_file_path=…)` | `decode(path=…, algorithm=…)` |
| `encode(source, output, message, True)` | `encode(source, output, message, algorithm, overwrite=True)` |
| `algorithms.basic_lsb_steganography` | `audiosteg.algorithms.basic_lsb` (`BASIC_LSB`) |
| `algorithms.enhanced_lsb_steganography_no_flip` | `audiosteg.algorithms.enhanced_lsb` (`ENHANCED_LSB`) |
| `algorithms.enhanced_lsb_steganography_with_flip` | `audiosteg.algorithms.enhanced_lsb_flip` (`ENHANCED_LSB_FLIP`) |
| `cli.config.ALGORITHMS` | `audiosteg.core.registry.ALGORITHMS` |
| `cli.helpers` | `audiosteg.cli.prompts` |
| `utils.errors` | `audiosteg` or `audiosteg.errors` |
| `utils.message_codec`, `utils.wav_io` | `audiosteg.core.message_codec`, `audiosteg.core.wav_io` |
| `utils.stego_file` (`write_message`, `read_message`) | `audiosteg.core.stego_file` (`encode`, `decode`) |
| `utils.output_path`, `utils.safe_write`, `utils.text` | The same names in `audiosteg.utils` |
| `input/original_sample.wav` | `src/audiosteg/data/sample.wav` |
| Default files in `output/` | Default files in the current folder |

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements_dev.txt -e .
ruff check .
ruff format --check .
mypy
pip-audit -r requirements_dev.txt
pytest --cov
python -m build
```

On Windows, activate the environment with `.venv\Scripts\activate`.

## Contributing

1. Fork the repository.
2. Create a branch (`git checkout -b my_new_feature`).
3. Commit your changes.
4. Push the branch and open a pull request.

## License

[MIT](LICENSE)
