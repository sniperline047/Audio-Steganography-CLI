"""The questions before a message is read."""

from questionary import Choice

from audiosteg.algorithms.registry import LEGACY_ALGORITHMS
from audiosteg.cli.commands.reveal import HiddenMessage, find_message, read_message
from audiosteg.cli.guided.equivalent import command_line, path_word
from audiosteg.cli.guided.prompter import Prompter, Step
from audiosteg.cli.results import RevealResult
from audiosteg.core import crypto
from audiosteg.errors import NoMessageError


class RevealForm:
    """The questions before a message is read."""

    def __init__(self, prompter: Prompter, default_file: str) -> None:
        """Start without any answer."""
        self.prompter = prompter
        self.default_file = default_file
        self.file = ""
        self.hidden: HiddenMessage | None = None
        self.result: RevealResult | None = None
        self.expected = ""

    def ask_file(self) -> bool:
        """Ask for the file and look for a message."""
        path = self.prompter.file("WAV file with the hidden message", self.default_file)
        self.file, self.result = path, None
        try:
            self.hidden = find_message(path)
        except NoMessageError:
            self.hidden = None
        if self.hidden is not None and self.hidden.encrypted:
            crypto.check_available()
        return True

    def ask_legacy(self) -> bool:
        """Ask for an old algorithm if no message was found."""
        if self.hidden is not None and not self.hidden.legacy:
            return False
        self.prompter.view.note("No message was found. An older version may have made this file.")
        legacy = self.prompter.choose(
            "How did the older version hide the message?",
            [Choice(f"{key}: {known.explanation}", value=key) for key, known in LEGACY_ALGORITHMS.items()],
        )
        self.hidden = find_message(self.file, legacy=legacy)
        return True

    def ask_passphrase(self) -> bool:
        """Ask for the passphrase of an encrypted message, until it opens the message."""
        if self.hidden is None or not self.hidden.encrypted:
            return False
        passphrase = self.prompter.hidden("Passphrase")
        self.result = read_message(self.hidden, passphrase)
        return True

    def read(self) -> RevealResult | None:
        """Return the message, or None if no question was answered."""
        if self.result is None and self.hidden is not None:
            self.result = read_message(self.hidden, None)
        return self.result

    def ask_expected(self) -> bool:
        """Ask for the expected message."""
        self.expected = self.prompter.text("Expected message")
        return True

    def steps(self) -> list[Step]:
        """Return the questions in their order."""
        return [self.ask_file, self.ask_legacy, self.ask_passphrase]

    def command(self, name: str) -> str | None:
        """Return the same command without the expected message and the passphrase, which it asks for."""
        words = ["audiosteg", name, path_word(self.file)]
        if self.hidden is not None and self.hidden.legacy:
            words += ["--legacy", self.hidden.algorithm]
        return command_line(*words)
