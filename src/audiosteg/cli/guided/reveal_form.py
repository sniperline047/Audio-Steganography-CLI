"""The questions before a message is read."""

from questionary import Choice

from audiosteg.algorithms.registry import ALGORITHMS, LEGACY_ALGORITHMS
from audiosteg.cli.commands.reveal import KEYED_ALGORITHM, HiddenMessage, find_message, read_message
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
        self.detected = False
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
        self.detected = self.hidden is not None
        if self.hidden is not None and self.hidden.encrypted:
            crypto.check_available()
        return True

    def ask_undetected(self) -> bool:
        """Ask how a message may be hidden if none was detected."""
        if self.detected:
            return False
        self.prompter.view.note(
            f"No message was detected. {KEYED_ALGORITHM} or an older version may have made this file."
        )
        key = self.prompter.choose(
            "How may the message be hidden?",
            [
                Choice(
                    f"{KEYED_ALGORITHM}: {ALGORITHMS[KEYED_ALGORITHM].explanation}", value=KEYED_ALGORITHM
                ),
                *[
                    Choice(f"{name} (old files only): {known.explanation}", value=name)
                    for name, known in LEGACY_ALGORITHMS.items()
                ],
            ],
        )
        self.result = None
        if key == KEYED_ALGORITHM:
            crypto.check_available()
            self.hidden = find_message(self.file, algorithm=key)
        else:
            self.hidden = find_message(self.file, legacy=key)
        return True

    def ask_passphrase(self) -> bool:
        """Ask for the passphrase of a message that is or may be encrypted, until it opens the message."""
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
        return [self.ask_file, self.ask_undetected, self.ask_passphrase]

    def command(self, name: str) -> str | None:
        """Return the same command without the expected message and the passphrase, which it asks for."""
        words = ["audiosteg", name, path_word(self.file)]
        if self.hidden is not None and self.hidden.legacy:
            words += ["--legacy", self.hidden.algorithm]
        elif self.hidden is not None and not self.detected:
            words += ["-a", self.hidden.algorithm]
        return command_line(*words)
