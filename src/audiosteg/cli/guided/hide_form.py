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
)
from audiosteg.cli.guided.equivalent import command_line, path_word
from audiosteg.cli.guided.prompter import GoBack, Prompter, Step
from audiosteg.cli.passphrase import ask_new_passphrase
from audiosteg.core import crypto
from audiosteg.core.wav_io import count_input_samples
from audiosteg.errors import MissingLibraryError
from audiosteg.utils.text import escape_text


class HideForm:
    """The questions before a message is hidden."""

    def __init__(self, prompter: Prompter) -> None:
        """Start without any answer."""
        self.prompter = prompter
        self.input_word = SAMPLE_WORD
        self.input_file = SAMPLE_FILE
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
            count_input_samples(self.input_file)
        return True

    def ask_input(self) -> bool:
        """Ask for the input file if the sample is not used."""
        if self.input_word == SAMPLE_WORD:
            return False
        path = self.prompter.file("Path of the WAV file")
        count_input_samples(path)
        self.input_file = path
        self.input_word = path_word(path)
        return True

    def ask_message(self) -> bool:
        """Ask for the message."""
        self.message = self.prompter.text("Message to hide")
        return True

    def ask_algorithm(self) -> bool:
        """Ask for the algorithm."""
        self.algorithm = self.prompter.choose(
            "Which algorithm? If you are not sure, use the first.",
            [Choice(f"{key}: {known.explanation}", value=key) for key, known in ALGORITHMS.items()],
        )
        return True

    def ask_encryption(self) -> bool:
        """Ask whether to encrypt the message, if this system can."""
        self.encrypted = False
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
        return True

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
        if not self.prompter.confirm(f"{escape_text(self.output_file)} already exists. Overwrite it?"):
            raise GoBack
        return True

    def steps(self) -> list[Step]:
        """Return the questions in their order."""
        return [
            self.ask_source,
            self.ask_input,
            self.ask_message,
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
