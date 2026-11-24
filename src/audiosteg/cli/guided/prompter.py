"""Ask questions with the same keys and colours everywhere."""

import os
import sys
from collections.abc import Callable
from typing import Any

import questionary
from prompt_toolkit.application import get_app_session
from prompt_toolkit.key_binding import KeyBindings, KeyPressEvent, merge_key_bindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.output import ColorDepth
from questionary import Choice, Question, Style

from audiosteg.cli.errors import OutputClosedError
from audiosteg.cli.views import View
from audiosteg.errors import StegoError
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

CONSOLE_ERRORS: tuple[type[Exception], ...] = ()
if sys.platform == "win32":
    from prompt_toolkit.output.win32 import NoConsoleScreenBufferError

    CONSOLE_ERRORS = (NoConsoleScreenBufferError,)


class GoBack(Exception):
    """The person wants to go back one question."""


BACK = Choice("Back", value=GoBack)


def can_show_menus() -> bool:
    """Say whether menus can be shown. Some Windows terminals are not a console, which menus need."""
    try:
        return get_app_session().output is not None
    except CONSOLE_ERRORS:
        return False


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
        if not path.strip():
            path = default
        if not path:
            raise ValueError("The path is empty.")
        if path == default:
            return path
        expanded = os.path.expanduser(path.strip())
        if expanded.startswith("~"):
            raise FileNotFoundError(f"No home folder was found for this path: {path}")
        return expanded

    def hidden(self, question: str) -> str:
        """Ask for a passphrase. The characters are shown as stars."""
        return str(self.ask(questionary.password(f"{question}:", **self.look)))

    def confirm(self, question: str) -> bool:
        """Ask a yes or no question. Enter means no."""
        confirmation = questionary.confirm(question, default=False, auto_enter=False, **self.look)
        return bool(self.ask(confirmation, end_with_ctrl_d=True))

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
