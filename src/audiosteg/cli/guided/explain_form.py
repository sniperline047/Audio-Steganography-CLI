"""The questions before an algorithm is explained."""

from questionary import Choice

from audiosteg.algorithms.registry import ALGORITHMS, LEGACY_ALGORITHMS
from audiosteg.cli.commands.explain import DEFAULT_LETTER, one_character
from audiosteg.cli.errors import UsageError
from audiosteg.cli.guided.equivalent import command_line
from audiosteg.cli.guided.labels import old_label
from audiosteg.cli.guided.prompter import Prompter, Step


class ExplainForm:
    """The questions before an algorithm is explained."""

    def __init__(self, prompter: Prompter) -> None:
        """Start without any answer."""
        self.prompter = prompter
        self.algorithm = ""
        self.letter = DEFAULT_LETTER

    def ask_algorithm(self) -> bool:
        """Ask for one of the algorithms, old ones last."""
        self.algorithm = self.prompter.choose(
            "Which algorithm?",
            [
                *[Choice(f"{key}: {ALGORITHMS[key].explanation}", value=key) for key in ALGORITHMS],
                *[Choice(old_label(key), value=key) for key in LEGACY_ALGORITHMS],
            ],
        )
        return True

    def ask_letter(self) -> bool:
        """Ask for the character to hide."""
        if self.algorithm in LEGACY_ALGORITHMS:
            return False
        try:
            self.letter = one_character(self.prompter.text("Character to hide", DEFAULT_LETTER))
        except UsageError as error:
            raise ValueError("Type exactly one character. Some emoji are several characters.") from error
        return True

    def steps(self) -> list[Step]:
        """Return the questions in their order."""
        return [self.ask_algorithm, self.ask_letter]

    def command(self) -> str | None:
        """Return the same command."""
        words = ["audiosteg", "explain", self.algorithm]
        if self.algorithm in ALGORITHMS and self.letter != DEFAULT_LETTER:
            words += ["--letter", self.letter]
        return command_line(*words)
