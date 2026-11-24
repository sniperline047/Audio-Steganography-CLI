"""The guided mode: menus that ask for everything a command needs."""

import os
import shlex
import subprocess
from collections.abc import Callable
from typing import Any

import questionary
from prompt_toolkit.key_binding import KeyBindings, KeyPressEvent, merge_key_bindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.output import ColorDepth
from questionary import Choice, Question, Style

from audiosteg.algorithms.registry import ALGORITHMS, LEGACY_ALGORITHMS
from audiosteg.cli.commands.hide import (
    SAMPLE_FILE,
    SAMPLE_WORD,
    HideRequest,
    check_output,
    default_output,
    find_input,
    hide,
)
from audiosteg.cli.commands.reveal import HiddenMessage, find_message, read_message
from audiosteg.cli.commands.verify import verify
from audiosteg.cli.errors import OutputClosedError
from audiosteg.cli.views import View
from audiosteg.core import crypto
from audiosteg.core.wav_io import check_regular_file
from audiosteg.errors import MissingLibraryError, NoMessageError, StegoError
from audiosteg.utils.text import escape_text

Step = Callable[[], bool]
EXPECTED_ERRORS = (StegoError, OSError, ValueError, MemoryError)
COLOURS = Style(
    [
        ("qmark", "fg:#2a9d8f bold"),
        ("question", "bold"),
        ("answer", "fg:#2a9d8f bold"),
        ("pointer", "fg:#ee6c4d bold"),
        ("highlighted", "fg:#ee6c4d bold"),
    ]
)
NO_COLOURS = Style(
    [(name, "noinherit") for name in ("qmark", "question", "answer", "pointer", "highlighted", "selected")]
)
TIP = "Enter accepts, arrow keys move, Esc goes back, Ctrl-C leaves."


class GoBack(Exception):
    """The person wants to go back one question."""


BACK = Choice("Back", value=GoBack)
EXIT = Choice("Exit", value="Exit")


class Prompter:
    """Ask questions with the same keys and colours everywhere."""

    def __init__(self, view: View) -> None:
        """Remember how to show questions."""
        self.view = view
        self.look: dict[str, Any] = {
            "qmark": "?",
            "style": COLOURS if view.out.coloured else NO_COLOURS,
            "color_depth": None if view.out.coloured else ColorDepth.DEPTH_1_BIT,
        }

    def ask(self, question: Question, end_with_ctrl_d: bool = False) -> Any:
        """Ask a question. Esc goes back, and Ctrl-C and the end of input are never lost."""
        keys = KeyBindings()

        @keys.add(Keys.Escape)
        def go_back(event: KeyPressEvent) -> None:
            event.app.exit(exception=GoBack())

        @keys.add(Keys.SIGINT)
        def interrupt(event: KeyPressEvent) -> None:
            event.app.exit(exception=KeyboardInterrupt())

        def end(event: KeyPressEvent) -> None:
            event.app.exit(exception=EOFError())

        if end_with_ctrl_d:
            keys.add(Keys.ControlD)(end)
        application = question.application
        application.timeoutlen = 0.2
        application.ttimeoutlen = 0.1
        application.key_bindings = merge_key_bindings([application.key_bindings or KeyBindings(), keys])
        try:
            return question.unsafe_ask()
        except OSError as error:
            raise OutputClosedError("The terminal was closed.") from error

    def choose(self, question: str, choices: list[Choice], last: Choice = BACK) -> Any:
        """Ask for one choice of a menu."""
        menu = questionary.select(
            question, [*choices, last], pointer=">", instruction="(arrow keys, then Enter)", **self.look
        )
        answer = self.ask(menu, end_with_ctrl_d=True)
        if answer is GoBack:
            raise GoBack
        return answer

    def text(self, question: str, default: str = "") -> str:
        """Ask for a line of text. Enter means the default."""
        shown = f"{question} [{escape_text(default)}]:" if default else f"{question}:"
        answer = str(self.ask(questionary.text(shown, **self.look)))
        return answer or default

    def file(self, question: str, default: str = "") -> str:
        """Ask for a path. Spaces around it are removed, and ~ means the home folder."""
        path = self.text(question, default)
        if path == default or not path.strip():
            return default
        expanded = os.path.expanduser(path.strip())
        if expanded.startswith("~"):
            raise FileNotFoundError(f"No home folder was found for this path: {path}")
        return expanded

    def hidden(self, question: str) -> str:
        """Ask for a passphrase. The characters are shown as stars."""
        return str(self.ask(questionary.password(f"{question}:", **self.look)))

    def confirm(self, question: str) -> bool:
        """Ask a yes or no question. Enter means no."""
        return bool(self.ask(questionary.confirm(question, default=False, **self.look)))

    def run(self, steps: list[Step]) -> bool:
        """
        Ask every question. Back returns to the question before, and an error asks again.

        :param steps: Functions that ask, and return whether they asked anything
        :return: False if the person went back from the first question
        """
        asked: list[int] = []
        position = 0
        while position < len(steps):
            try:
                if steps[position]():
                    asked.append(position)
                position += 1
            except GoBack:
                if not asked:
                    return False
                position = asked.pop()
            except EXPECTED_ERRORS as error:
                self.view.show_error(error, None, 1)
        return True


def command_line(*words: str) -> str | None:
    """Return a command for the terminal, or None if a word cannot be shown."""
    if any(not word.isprintable() for word in words):
        return None
    return subprocess.list2cmdline(words) if os.name == "nt" else shlex.join(words)


def path_word(path: str) -> str:
    """Return a path that cannot be mistaken for an option or for the sample."""
    return os.path.join(".", path) if path.startswith("-") or path == SAMPLE_WORD else path


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
        return True

    def ask_input(self) -> bool:
        """Ask for the input file if the sample is not used."""
        if self.input_word == SAMPLE_WORD:
            return False
        path = self.prompter.file("Path of the WAV file")
        check_regular_file(path)
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

    def ask_passphrase(self) -> bool:
        """Ask for a passphrase if this system can encrypt."""
        self.passphrase = None
        try:
            crypto.check_available()
        except MissingLibraryError as error:
            self.prompter.view.note(f"The message will not be encrypted. {error}")
            return False
        if self.prompter.choose(
            "Encrypt the message?",
            [
                Choice("No, anyone with the file can read it", value=False),
                Choice("Yes, with a passphrase (it cannot be recovered)", value=True),
            ],
        ):
            self.passphrase = self.ask_new_passphrase()
        return True

    def ask_new_passphrase(self) -> str:
        """Ask for a passphrase twice, until both match and it is not empty."""
        while True:
            passphrase = self.prompter.hidden("Passphrase")
            if not passphrase:
                self.prompter.view.note("The passphrase is empty. Please try again.")
            elif self.prompter.hidden("Repeat the passphrase") == passphrase:
                return passphrase
            else:
                self.prompter.view.note("The passphrases do not match. Please try again.")

    def ask_output(self) -> bool:
        """Ask for the output file, and before replacing a file."""
        while True:
            self.output_word = self.prompter.file("Output file", default_output(self.input_file))
            self.output_file, self.overwrite = check_output(self.input_file, self.output_word)
            if not self.overwrite or self.prompter.confirm(
                f"{escape_text(self.output_file)} already exists. Overwrite it?"
            ):
                return True

    def steps(self) -> list[Step]:
        """Return the questions in their order."""
        return [
            self.ask_source,
            self.ask_input,
            self.ask_message,
            self.ask_algorithm,
            self.ask_passphrase,
            self.ask_output,
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


class RevealForm:
    """The questions before a message is read."""

    def __init__(self, prompter: Prompter, default_file: str) -> None:
        """Start without any answer."""
        self.prompter = prompter
        self.default_file = default_file
        self.file = ""
        self.hidden: HiddenMessage | None = None
        self.passphrase: str | None = None
        self.expected = ""

    def ask_file(self) -> bool:
        """Ask for the file and look for a message."""
        path = self.prompter.file("WAV file with the hidden message", self.default_file)
        check_regular_file(path)
        self.file, self.passphrase = path, None
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
        """Ask for the passphrase of an encrypted message."""
        if self.hidden is None or not self.hidden.encrypted:
            return False
        self.passphrase = self.prompter.hidden("Passphrase") or None
        return True

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


class Guide:
    """The main menu."""

    def __init__(self, view: View) -> None:
        """Start the menu."""
        self.view = view
        self.prompter = Prompter(view)
        self.last_output = ""
        self.failed = False

    def show_command(self, command: str | None) -> None:
        """Show the command that does the same."""
        if command is None:
            self.view.note("The same command cannot be shown: a file name has unusual characters.")
        else:
            self.view.note(f"The same as a command: {command}")

    def hide(self) -> None:
        """Ask for a message and hide it."""
        form = HideForm(self.prompter)
        if not self.prompter.run(form.steps()):
            return
        self.view.progress("Hiding the message...")
        result = hide(form.request())
        self.last_output = form.output_word
        self.view.show_hide(result)
        self.show_command(form.command())

    def reveal(self) -> None:
        """Ask for a file and show its message."""
        form = RevealForm(self.prompter, self.last_output)
        if not self.prompter.run(form.steps()) or form.hidden is None:
            return
        result = read_message(form.hidden, form.passphrase)
        self.show_command(form.command("reveal"))
        self.view.show_reveal(result)

    def verify(self) -> None:
        """Ask for a file and the expected message, and compare them."""
        form = RevealForm(self.prompter, self.last_output)
        if not self.prompter.run([*form.steps(), form.ask_expected]) or form.hidden is None:
            return
        result = verify(read_message(form.hidden, form.passphrase), form.expected)
        self.view.show_verify(result)
        self.show_command(form.command("verify"))

    def algorithms(self) -> None:
        """Show every algorithm."""
        self.view.show_algorithms()
        self.show_command("audiosteg algorithms")

    def choose_action(self) -> Callable[[], None] | None:
        """Ask what to do. Return None to leave."""
        choices = [
            Choice("Hide a message", value=self.hide),
            Choice("Reveal a message", value=self.reveal),
            Choice("Verify a message", value=self.verify),
            Choice("Learn about the algorithms", value=self.algorithms),
        ]
        while True:
            try:
                action: Callable[[], None] | str = self.prompter.choose(
                    "What would you like to do?", choices, EXIT
                )
            except GoBack:
                continue
            except EOFError:
                return None
            return None if isinstance(action, str) else action

    def run(self) -> int:
        """Show the menu until the person leaves. Return the exit code."""
        self.view.show_welcome()
        self.view.note(TIP)
        while action := self.choose_action():
            try:
                action()
            except OutputClosedError:
                raise
            except EXPECTED_ERRORS as error:
                self.failed = True
                self.view.show_error(error, None, 1)
            self.view.note("")
        return 1 if self.failed else 0


def run(view: View) -> int:
    """Run the guided mode. Return the exit code."""
    return Guide(view).run()
