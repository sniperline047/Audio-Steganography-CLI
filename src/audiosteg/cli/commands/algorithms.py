"""The algorithms command."""

import argparse

from audiosteg.cli.views import View

HELP = "list the algorithms"
EXAMPLES = """examples:
  audiosteg algorithms
  audiosteg algorithms --json
"""


def run(args: argparse.Namespace, view: View) -> int:
    """Run the command. Return the exit code."""
    view.show_algorithms()
    return 0


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the options of this command, which has none."""
