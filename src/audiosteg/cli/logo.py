"""The logo of the welcome screen: a cassette with a hidden key."""

from rich.text import Text

COLOURS = {
    "b": "#b5432f",
    "o": "#ee6c4d",
    "c": "#fff1d6",
    "s": "#d9c6a0",
    "t": "#2a9d8f",
    "n": "#2b2d42",
    "y": "#ffd166",
}

PIXELS = (
    ".bbbbbbbbbbbbbbbbbbbbbbbbbbbb.",
    "boooooooooooooooooooooooooooob",
    "boottttttttttttttttttttttttoob",
    "boottttttttttttttttttttttttoob",
    "booccccccccccccccccccccccccoob",
    "booccnnnnnnnnnnnnnnnnnnnnccoob",
    "booccnnyyyynnnnnnnnnnnnnnccoob",
    "booccnynnnnynnnnnnnnnnnnnccoob",
    "booccnynccnyyyyyyyyyyyynnccoob",
    "booccnynnnnynnnnnnnynnynnccoob",
    "booccnnyyyynnnnnnnnynnynnccoob",
    "booccnnnnnnnnnnnnnnnnnnnnccoob",
    "booccssssssssssssssssssssccoob",
    "booccccccccccccccccccccccccoob",
    "booccccccccccccccccccccccccoob",
    "booooooobbbbbbbbbbbbbbooooooob",
    "booooooobbbbbbbbbbbbbbooooooob",
    "bobooooobbcbbbccbbbcbbooooobob",
    "boooooobbbbbbbbbbbbbbbboooooob",
    ".bbbbbbbbbbbbbbbbbbbbbbbbbbbb.",
)

NAME = "Audio Steganography CLI"
SLOGAN = "Hide messages in sound, and see how it works"
TEXT_ROWS = {3: NAME, 4: SLOGAN}
MINIMUM_WIDTH = 80


def draw_cell(top: str, bottom: str) -> tuple[str, str]:
    """Return the character and the style that show two pixels, one above the other."""
    if top in COLOURS and bottom in COLOURS:
        return "▀", f"{COLOURS[top]} on {COLOURS[bottom]}"
    if top in COLOURS:
        return "▀", COLOURS[top]
    if bottom in COLOURS:
        return "▄", COLOURS[bottom]
    return " ", ""


def draw_logo() -> Text:
    """Draw the logo next to the program name. It needs 24-bit colour and 80 columns."""
    rows = []
    for number, (upper, lower) in enumerate(zip(PIXELS[::2], PIXELS[1::2], strict=True)):
        cells = [draw_cell(top, bottom) for top, bottom in zip(upper, lower, strict=True)]
        rows.append(Text.assemble("  ", *cells, "   ", TEXT_ROWS.get(number, "")))
    return Text("\n").join(rows)


def plain_title() -> str:
    """Return the text that replaces the logo."""
    return f"{NAME}\n{SLOGAN}"
