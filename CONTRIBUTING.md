# Contributing

Thanks for helping! Start with the [README](README.md) to see what the project does.

## Send a change

1. Fork the repository.
2. Create a branch (`git checkout -b my_new_feature`).
3. Set up the project and run the checks in [Development](#development).
4. Commit your changes.
5. Push the branch and open a pull request.

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

Mark a test that needs the `crypto` extra with `@pytest.mark.needs_crypto`. It is skipped when the library is missing, unless the environment variable `AUDIOSTEG_REQUIRE_CRYPTO` is set. The automated checks run the tests with and without the extra, and set that variable when the extra is installed. They run on Linux and Windows for every pull request, and on macOS once a week or when started by hand.

Test coverage must stay at 90% or more. A code file has at most one test file, in the same folder under `tests/` as under `src/audiosteg/`. Some tests compare the examples in `docs/` with the real output.

## Project layout

```
Audio-Steganography-CLI/
├── .github/                Automated checks
├── docs/                   Reference pages and the logo
├── scripts/
│   └── generate_sample_audio.py
├── src/audiosteg/
│   ├── algorithms/
│   │   ├── detection.py    Detection and decode
│   │   ├── legacy.py       Reading files from older versions
│   │   ├── lsb.py          lsb and lsb_2
│   │   ├── lsb_four.py     Four bits per sample
│   │   ├── lsb_keyed.py    Scattered by a passphrase
│   │   ├── lsb_matching.py Whole samples by +1 or -1
│   │   ├── lsb_parity.py   One bit per 8 samples
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
│   │   ├── change_view.py  Changed samples of explain
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
│   │   ├── keyed.py        Containers scattered by a key
│   │   ├── message_codec.py Message and bit conversion
│   │   ├── scatter.py      A random order of numbers
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
├── CONTRIBUTING.md
├── LICENSE
├── README.md
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

   The functions get only the lowest byte of each sample. `bits_per_byte` must be 1, 2, 4, or 8. `strengths` and `weaknesses` are optional and shown by `explain`, which computes everything else with the two functions. `how` is optional too: `explain` shows it where the bits are changed.

2. Import it in `src/audiosteg/algorithms/registry.py` and add one line to `ALGORITHMS`, with the name for the command line:

   ```python
   "my_new_algorithm": MY_NEW_ALGORITHM,
   ```

If an algorithm needs more than the lowest byte of one sample, make a subclass of `Algorithm` and replace its methods:

- `embed_group(samples, sample_width, bits)` gets whole samples as they are stored and returns as many changed bytes. `lsb_matching.py` uses it to move whole samples.
- `extract_group(low_bytes)` gets the lowest byte of each sample of a group and returns the bits.
- `samples_per_group` says how many samples carry `bits_per_byte` bits together. `lsb_parity.py` uses 8 and both methods.
- `parity=True` makes `explain` show the parity of the lowest bits of each group. Without it, `explain` shows the lowest byte of every sample.

Random choices use `secrets` through a field that tests can replace, such as `choose`. Two more fields need no subclass:

- `keyed=True` encrypts every message and scatters it over the samples by the passphrase. It needs groups of one sample. Such a message is not detected, and the program tries only one keyed algorithm by itself: `lsb_keyed`. Name any other with `-a`, or pass it to `decode`.
- `reads_like=LSB` says that another algorithm reads the messages, so that they are not detected twice.

The commands, the guided mode, detection, the capacity check, and the file handling need no changes.

Detection tries the algorithms in order and stops at the first message. If the input audio already holds a message from an algorithm earlier in the list, that old message can be found instead of the new one. To avoid this, pass the algorithm to `decode`, or use `-a`.
