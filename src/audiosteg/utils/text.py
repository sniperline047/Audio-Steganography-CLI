"""Make untrusted text safe to print in a terminal."""


def escape_text(text: str) -> str:
    """
    Replace non-printable characters with visible escape codes.

    This covers control characters (including ESC and newlines), bidirectional
    controls, and lone surrogates.

    :param text: Any text, such as a decoded message or a file path
    :return: Text that cannot control the terminal
    """
    return "".join(
        character if character.isprintable() else character.encode("unicode_escape").decode("ascii")
        for character in text
    )
