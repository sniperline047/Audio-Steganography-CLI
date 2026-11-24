# Audio Steganography CLI

[![Test coverage](https://github.com/sniperline047/Audio-Steganography-CLI/raw/coverage_badge/coverage.svg)](https://github.com/sniperline047/Audio-Steganography-CLI/actions/workflows/tests.yml)

A learning project that hides a text message inside a WAV file and reads it back. It offers three least significant bit (LSB) algorithms through an interactive menu and needs only the Python standard library.

> **Messages are not encrypted or authenticated.** Anyone who knows the algorithm can read a hidden message, change it, or replace it. Do not use this project to protect real secrets.

## Requirements

- Python 3.11 or newer
- An uncompressed integer PCM WAV file (8, 16, 24, or 32-bit). The limit for encoding is 1 GiB. Streamed files with no stated audio size and files with padded samples are not supported.

Some PCM files use the "extensible" WAV header. Python 3.11 cannot read that header; Python 3.12 and newer can.

## Setup

```bash
git clone https://github.com/sniperline047/Audio-Steganography-CLI.git
cd Audio-Steganography-CLI
```

There is nothing to install to run the program.

## Run

```bash
python cli/main.py
```

or, from the project folder:

```bash
python -m cli.main
```

The menu has four options:

1. **Encode a message**
2. **Decode a message**
3. **Calculate accuracy**
4. **Exit**

At a path prompt, press Enter (or answer `y` or `yes`) to use the default file. Answer `n` or `no` to type another path.

The program exits with code 0 when every operation succeeded, 1 when an operation failed or the input ended in the middle of one, and 130 after Ctrl-C.

### Encode a message

1. Choose **Encode a message**, then an algorithm.
2. Type the secret message.
3. Choose the input audio file. The default is `input/original_sample.wav`.
4. Choose the output audio file. The default depends on the algorithm (see below).
5. If the output file exists, confirm that it may be overwritten. The default answer is no.

The input file is never changed. The program refuses to write to the input file or to a symbolic link. Only the audio is copied; tags and other metadata are not.

### Decode a message

1. Choose **Decode a message**, then the algorithm that was used to encode.
2. Choose the encoded audio file. The default is that algorithm's output file.

Characters that could control the terminal are shown as escape codes such as `\x1b`. This only changes the display; the hidden message stays the same. Invisible joiners are also escaped, so some combined emoji appear as separate emoji and a code such as `\u200d`.

### Calculate accuracy

1. Choose **Calculate accuracy**.
2. Type the expected message, then choose the algorithm.
3. Choose the encoded audio file.

This reads an existing file and changes nothing. The score is the number of matching character positions divided by the longer message length, so missing and extra characters lower it. The program also says whether the messages match exactly.

## Algorithms

Each algorithm first stores the message length in bits as a 32-bit number, then the message as UTF-8 text.

Older versions stored one byte per character. If a message is not valid UTF-8, it is read as Latin-1, so most old messages still decode. A few old messages with accented letters also happen to be valid UTF-8 and show different characters. The earliest files, which have no length header and are padded with `#`, are not supported.

| Menu | Algorithm | Bits per sample byte | Code | Default output |
| --- | --- | --- | --- | --- |
| 1 | Basic LSB Steganography | 1 (lowest bit) | `algorithms/basic_lsb_steganography.py` | `output/basic_lsb_encoded.wav` |
| 2 | Enhanced LSB Steganography with Bit Flipping | 2 (third and fourth lowest bits) | `algorithms/enhanced_lsb_steganography_with_flip.py` | `output/enhanced_lsb_encoded_flip.wav` |
| 3 | Enhanced LSB Steganography without Bit Flipping | 2 (third and fourth lowest bits) | `algorithms/enhanced_lsb_steganography_no_flip.py` | `output/enhanced_lsb_encoded_no_flip.wav` |

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
├── .github/            Automated checks
├── algorithms/         The three algorithms
├── cli/
│   ├── accuracy.py     Message comparison
│   ├── config.py       Default paths and algorithm list
│   ├── helpers.py      Menus and prompts
│   └── main.py         Program entry point
├── input/
│   └── original_sample.wav
├── output/             Encoded files (created when needed, not tracked by Git)
├── scripts/
│   └── generate_sample_audio.py
├── utils/
│   ├── errors.py       Error types
│   ├── message_codec.py Message and bit conversion
│   ├── output_path.py  Output path checks
│   ├── safe_write.py   One-step file writing
│   ├── stego_file.py   Shared encode and decode steps
│   ├── text.py         Safe terminal text
│   └── wav_io.py       WAV reading and writing
├── LICENSE
├── pyproject.toml
└── requirements_dev.txt
```

`input/original_sample.wav` is an original tune. Run `python scripts/generate_sample_audio.py` to create it again.

## Add an algorithm

1. Create a module in `algorithms/` with these functions:
   - `encode(input_file_path, output_file_path, secret_message, overwrite=False)`
   - `decode(input_file_path)`, which returns the message
2. Raise an error from `utils/errors.py` when an operation cannot finish.
3. Import the module in `cli/config.py` and add an entry to `ALGORITHMS`:

   ```python
   4: {
       "name": "My New Algorithm",
       "encode": my_new_algorithm.encode,
       "decode": my_new_algorithm.decode,
       "output_file": str(PROJECT_ROOT / "output" / "my_new_algorithm_encoded.wav"),
   },
   ```

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements_dev.txt
ruff check .
ruff format --check .
mypy
pip-audit -r requirements_dev.txt
pytest --cov
```

On Windows, activate the environment with `.venv\Scripts\activate`.

## Contributing

1. Fork the repository.
2. Create a branch (`git checkout -b my_new_feature`).
3. Commit your changes.
4. Push the branch and open a pull request.

## License

[MIT](LICENSE)
