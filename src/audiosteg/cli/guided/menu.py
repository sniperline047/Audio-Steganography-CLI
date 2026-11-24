"""The main menu of the guided mode."""

from collections.abc import Callable

from questionary import Choice

from audiosteg.cli.commands.hide import hide
from audiosteg.cli.commands.verify import verify
from audiosteg.cli.errors import OutputClosedError
from audiosteg.cli.guided.hide_form import HideForm
from audiosteg.cli.guided.prompter import EXPECTED_ERRORS, GoBack, Prompter
from audiosteg.cli.guided.reveal_form import RevealForm
from audiosteg.cli.views import View

TIP = "Enter accepts, arrow keys move, Esc goes back, Ctrl-C leaves."
EXIT = Choice("Exit", value="Exit")


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
        if not self.prompter.run(form.steps()) or (result := form.read()) is None:
            return
        self.show_command(form.command("reveal"))
        self.view.show_reveal(result)

    def verify(self) -> None:
        """Ask for a file and the expected message, and compare them."""
        form = RevealForm(self.prompter, self.last_output)
        if not self.prompter.run([*form.steps(), form.ask_expected]) or (revealed := form.read()) is None:
            return
        result = verify(revealed, form.expected)
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
