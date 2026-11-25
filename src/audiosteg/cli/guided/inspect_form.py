"""The question before a file is inspected."""

from audiosteg.cli.commands.hide import SAMPLE_WORD
from audiosteg.cli.guided.equivalent import command_line, option_safe
from audiosteg.cli.guided.prompter import Prompter, Step

SAMPLE_HELP = f"{SAMPLE_WORD} means the included tune"


class InspectForm:
    """The question before a file is inspected."""

    def __init__(self, prompter: Prompter, default_file: str) -> None:
        """Start without any answer."""
        self.prompter = prompter
        self.default_file = default_file
        self.word = ""

    def ask_file(self) -> bool:
        """Ask for the file."""
        self.word = option_safe(self.prompter.file(f"WAV file ({SAMPLE_HELP})", self.default_file))
        return True

    def steps(self) -> list[Step]:
        """Return the questions in their order."""
        return [self.ask_file]

    def command(self) -> str | None:
        """Return the same command."""
        return command_line("audiosteg", "inspect", self.word)
