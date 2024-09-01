from utils.logging_util import setup_logger
from cli.config import ALGORITHMS, STANDARD_INPUT_FILE_PATH

logger = setup_logger(__name__)

def display_menu(options, header):
    """Displays a menu with a header and a list of options."""
    logger.info(f"Displaying {header} menu to the user.")
    print(f"\n{header}:")
    for idx, option in enumerate(options, 1):
        print(f"{idx}) {option}")

def get_user_choice(num_options):
    """Gets a validated user choice for a menu."""
    try:
        choice = int(input("\nChoice: "))
        if 1 <= choice <= num_options:
            return choice
        else:
            logger.warning("Choice out of range.")
            print("\nInvalid choice, please select a valid option.")
    except ValueError:
        logger.error("Invalid input; not a number.")
        print("\nPlease enter a valid number!")
    return None

def get_file_path(algo_choice, is_input=True):
    """Gets the file path from the user or uses the standard path."""
    if is_input:
        prompt = "input audio file: "
        standard_path = STANDARD_INPUT_FILE_PATH
    else:
        prompt = "output audio file: "
        standard_path = ALGORITHMS[algo_choice]["output_file"]

    use_standard = input(f"\nUse standard file path ({standard_path}) for the {prompt} file? (y/n): ")
    if use_standard.lower() == "y":
        logger.info(f"Using standard file path: {standard_path}")
        return standard_path

    file_path = input(f"Enter the path to the custom {prompt}")
    logger.info(f"User entered file path: {file_path}")
    return file_path

def display_algorithm_menu():
    """Displays the algorithm selection menu based on the ALGORITHMS dictionary."""
    options = [algo["name"] for algo in ALGORITHMS.values()]
    display_menu(options, "Select an algorithm")
