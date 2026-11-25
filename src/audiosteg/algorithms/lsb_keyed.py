"""Hide one bit in each sample, encrypted and scattered over the file by a passphrase."""

from audiosteg.algorithms.lsb import embed_one_bit, extract_one_bit
from audiosteg.core.algorithm import Algorithm

LSB_KEYED = Algorithm(
    name="LSB keyed (1 bit per sample, scattered)",
    bits_per_byte=1,
    embed_bits=embed_one_bit,
    extract_bits=extract_one_bit,
    explanation="Encrypted and scattered with a passphrase.",
    strengths=(
        "Nothing in the file says that there is a message, so inspect finds none.",
        "The message is always encrypted, and a change to it is noticed.",
    ),
    weaknesses=(
        "Without the passphrase, nobody can find the message again, and it cannot be recovered.",
        "Statistics can still show that lowest bits were changed, most of all in silent or very clean audio.",
        "Editing, compressing, or converting the audio destroys the message.",
    ),
    how="A key decides which samples are used, and in which order.",
    keyed=True,
)
