"""The questions before and after two files are compared."""

from questionary import Choice

from audiosteg.cli.commands.compare import (
    EVERY_SOUND,
    METRICS,
    SOUNDS,
    CompareRequest,
    check_pair,
    in_order,
    metric_list,
)
from audiosteg.cli.commands.hide import find_input
from audiosteg.cli.errors import UsageError
from audiosteg.cli.guided.equivalent import command_line, option_safe
from audiosteg.cli.guided.inspect_form import SAMPLE_HELP
from audiosteg.cli.guided.prompter import GoBack, Prompter, Step
from audiosteg.cli.player import can_play

DEFAULT_METRICS = "snr,changes"
SIMPLE, DETAILED, CHOOSE = "simple", "detailed", "choose"


class CompareForm:
    """The questions before and after two files are compared."""

    def __init__(self, prompter: Prompter, default_original: str, default_encoded: str) -> None:
        """Start without any answer."""
        self.prompter = prompter
        self.default_original = default_original
        self.default_encoded = default_encoded
        self.original = ""
        self.encoded = ""
        self.level = SIMPLE
        self.metrics: tuple[str, ...] = ()
        self.sound = ""

    def ask_original(self) -> bool:
        """Ask for the original file."""
        self.original = option_safe(self.prompter.file(f"Original ({SAMPLE_HELP})", self.default_original))
        return True

    def ask_encoded(self) -> bool:
        """Ask for the other file, and check that both can be compared."""
        self.encoded = option_safe(self.prompter.file("Copy with the hidden message", self.default_encoded))
        check_pair(self.request())
        return True

    def ask_level(self) -> bool:
        """Ask how much to show."""
        self.level = self.prompter.choose(
            "How much do you want to see?",
            [
                Choice("Simple: three lines", value=SIMPLE),
                Choice("Detailed: every metric, explained", value=DETAILED),
                Choice("Choose what to show", value=CHOOSE),
            ],
        )
        self.metrics = METRICS if self.level == DETAILED else ()
        return True

    def ask_metrics(self) -> bool:
        """Ask which metrics to show."""
        if self.level != CHOOSE:
            return False
        names = self.prompter.text(f"Names from {', '.join(METRICS)}, with commas", DEFAULT_METRICS)
        try:
            self.metrics = in_order(metric_list(names.replace(" ", "")))
        except UsageError as error:
            raise ValueError(f"Choose from: {', '.join(METRICS)}.") from error
        return True

    def ask_play(self) -> bool:
        """Ask whether to play the files, if there is a player. Return whether to play."""
        if not can_play():
            return False
        try:
            self.sound = self.prompter.choose(
                "Listen to them? Ctrl-C stops the sound and leaves.",
                [
                    Choice("No", value=""),
                    Choice("All three", value=EVERY_SOUND),
                    *[Choice(f"Only the {name} sound", value=name) for name in SOUNDS],
                ],
            )
        except GoBack:
            return False
        return self.sound != ""

    def steps(self) -> list[Step]:
        """Return the questions in their order."""
        return [self.ask_original, self.ask_encoded, self.ask_level, self.ask_metrics]

    def request(self) -> CompareRequest:
        """Return what to compare."""
        return CompareRequest(find_input(self.original), find_input(self.encoded), self.metrics)

    def command(self) -> str | None:
        """Return the same command."""
        words = ["audiosteg", "compare", self.original, self.encoded]
        if self.level == DETAILED:
            words.append("--details")
        if self.level == CHOOSE:
            words += [word for name in self.metrics for word in ("--show", name)]
        if self.sound:
            words += ["--play"] if self.sound == EVERY_SOUND else ["--play", self.sound]
        return command_line(*words)
