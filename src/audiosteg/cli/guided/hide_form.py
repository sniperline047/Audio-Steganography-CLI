"""The questions before a message is hidden."""

from questionary import Choice

from audiosteg.algorithms.registry import ALGORITHMS
from audiosteg.cli.commands.hide import (
    SAMPLE_FILE,
    SAMPLE_WORD,
    HideRequest,
    check_output,
    default_output,
    find_input,
    fitting_algorithms,
    largest_message,
)
from audiosteg.cli.guided.equivalent import command_line, path_word
from audiosteg.cli.guided.labels import algorithm_choice
from audiosteg.cli.guided.prompter import GoBack, Prompter, Step
from audiosteg.cli.passphrase import ask_new_passphrase
from audiosteg.cli.views import display_path
from audiosteg.core import crypto
from audiosteg.core.message_codec import message_to_bytes
from audiosteg.core.signal_algorithm import SignalAlgorithm, check_library
from audiosteg.core.wav_io import AudioSize, measure_input
from audiosteg.errors import CapacityError, MissingLibraryError
from audiosteg.utils.text import escape_text


class HideForm:
    """The questions before a message is hidden."""

    def __init__(self, prompter: Prompter) -> None:
        """Start without any answer."""
        self.prompter = prompter
        self.input_word = SAMPLE_WORD
        self.input_file = SAMPLE_FILE
        self.size = AudioSize(0, 1, 1)
        self.output_word = ""
        self.output_file = ""
        self.message = ""
        self.algorithm = ""
        self.encrypted = False
        self.passphrase: str | None = None
        self.overwrite = False

    def ask_source(self) -> bool:
        """Ask whether to use the sample."""
        self.input_word = self.prompter.choose(
            "Which audio file?",
            [
                Choice("The included sample (good for a first try)", value=SAMPLE_WORD),
                Choice("A WAV file of mine", value=""),
            ],
        )
        self.input_file = find_input(self.input_word)
        if self.input_word == SAMPLE_WORD:
            self.size = measure_input(self.input_file)
        return True

    def ask_input(self) -> bool:
        """Ask for the input file if the sample is not used."""
        if self.input_word == SAMPLE_WORD:
            return False
        path = self.prompter.file("Path of the WAV file")
        self.size = measure_input(path)
        self.input_file = path
        self.input_word = path_word(path)
        return True

    def ask_message(self) -> bool:
        """Ask for a message that the file can hold."""
        message = self.prompter.text("Message to hide")
        length, limit = len(message_to_bytes(message)), largest_message(self.size, encrypted=False)
        if not fitting_algorithms(message, self.size, encrypted=False):
            raise CapacityError(
                f"The message is too large: it needs {length} bytes and the audio file can hold "
                f"{limit} bytes. Type a shorter message, or go back and choose a longer audio file."
            )
        self.message = message
        return True

    def ask_empty(self) -> bool:
        """Ask before an empty message is hidden. No returns to the message."""
        if self.message:
            return False
        if not self.prompter.confirm("The message is empty. Hide an empty message?"):
            raise GoBack
        return True

    def fitting(self, encrypted: bool) -> list[str]:
        """Return the names of the algorithms that can hold the message."""
        return fitting_algorithms(self.message, self.size, encrypted)

    def too_short(self) -> list[str]:
        """Return the names of the algorithms that need a longer sound for any message."""
        usable = fitting_algorithms("", self.size, encrypted=False)
        return [
            key
            for key, known in ALGORITHMS.items()
            if isinstance(known, SignalAlgorithm) and key not in usable
        ]

    def ask_algorithm(self) -> bool:
        """Ask for one of the algorithms that can hold the message."""
        keys = self.fitting(encrypted=False)
        short = self.too_short()
        if len(keys) + len(short) < len(ALGORITHMS):
            self.prompter.view.note(
                f"The message is too large for some algorithms. These can hold it: {', '.join(keys)}."
            )
        elif short:
            self.prompter.view.note(f"The sound is too short for {', '.join(short)}.")
        self.algorithm = self.prompter.choose(
            "Which algorithm? If you are not sure, use the first.",
            [algorithm_choice(key) for key in keys],
        )
        check_library(ALGORITHMS[self.algorithm])
        if self.is_keyed():
            crypto.check_available()
        return True

    def is_keyed(self) -> bool:
        """Say whether the chosen algorithm always encrypts."""
        return ALGORITHMS[self.algorithm].keyed

    def ask_encryption(self) -> bool:
        """Ask whether to encrypt the message, if this system can and the algorithm does not decide it."""
        self.encrypted = self.is_keyed()
        if self.encrypted:
            return False
        try:
            crypto.check_available()
        except MissingLibraryError as error:
            self.prompter.view.note(f"The message will not be encrypted. {error}")
            return False
        self.encrypted = self.prompter.choose(
            "Encrypt the message?",
            [
                Choice("No, anyone with the file can read it", value=False),
                Choice("Yes, with a passphrase (it cannot be recovered)", value=True),
            ],
        )
        if self.encrypted:
            self.check_encrypted_size()
        return True

    def check_encrypted_size(self) -> None:
        """Say how the message could be encrypted if encryption makes it too large."""
        keys = self.fitting(encrypted=True)
        if self.algorithm in keys:
            return
        advice = f"choose {keys[0]}" if keys else "type a shorter message"
        raise CapacityError(
            f"Encryption makes the message too large for {self.algorithm}. "
            f"Do not encrypt it, or go back and {advice}."
        )

    def ask_passphrase(self) -> bool:
        """Ask for a passphrase twice if the message should be encrypted."""
        self.passphrase = None
        if not self.encrypted:
            return False
        self.passphrase = ask_new_passphrase(
            lambda: self.prompter.hidden("Passphrase"), self.repeat_passphrase, self.prompter.view.note
        )
        return True

    def repeat_passphrase(self) -> str | None:
        """Ask for the passphrase again. Going back means starting with the passphrase."""
        try:
            return self.prompter.hidden("Repeat the passphrase")
        except GoBack:
            return None

    def ask_output(self) -> bool:
        """Ask for the output file."""
        self.output_word = self.prompter.file("Output file", default_output(self.input_file))
        self.output_file, self.overwrite = check_output(self.input_file, self.output_word)
        return True

    def ask_overwrite(self) -> bool:
        """Ask before replacing a file. No returns to the output file."""
        if not self.overwrite:
            return False
        if not self.prompter.confirm(
            f"{escape_text(display_path(self.output_file))} already exists. Overwrite it?"
        ):
            raise GoBack
        return True

    def steps(self) -> list[Step]:
        """Return the questions in their order."""
        return [
            self.ask_source,
            self.ask_input,
            self.ask_message,
            self.ask_empty,
            self.ask_algorithm,
            self.ask_encryption,
            self.ask_passphrase,
            self.ask_output,
            self.ask_overwrite,
        ]

    def command(self) -> str | None:
        """Return the same command without the message and the passphrase, which it asks for."""
        words = [
            "audiosteg",
            "hide",
            self.input_word,
            "-a",
            self.algorithm,
            "-o",
            path_word(self.output_word),
        ]
        if self.passphrase is not None:
            words.append("-p")
        if self.overwrite:
            words.append("--force")
        return command_line(*words)

    def request(self) -> HideRequest:
        """Return what to hide."""
        return HideRequest(
            self.input_file, self.output_file, self.message, self.algorithm, self.passphrase, self.overwrite
        )
