import os
import sys
from tqdm import tqdm

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(project_root)
from utils.logging_util import setup_logger
from cli.helpers import display_menu, get_user_choice, get_file_path, display_algorithm_menu
from cli.config import ALGORITHMS
from cli.accuracy import calculate_accuracy

logger = setup_logger(__name__)

def handle_algorithm_choice(encode=True):
    """Handles the user's choice of algorithm for encoding or decoding."""
    display_algorithm_menu()
    
    algo_choice = get_user_choice(len(ALGORITHMS))
    if algo_choice is None or algo_choice not in ALGORITHMS:
        logger.warning("Invalid algorithm choice.")
        print("\nInvalid algorithm choice!")
        return

    if encode:
        secret_message = input("Enter the secret message to encode: ")
        logger.info(f"Secret message to encode: {secret_message}")
        input_file = get_file_path(algo_choice, is_input=True)
        output_file = get_file_path(algo_choice, is_input=False)
        handle_encode(algo_choice, input_file, output_file, secret_message)
    else:
        output_file = get_file_path(algo_choice, is_input=False)
        handle_decode(algo_choice, output_file)

def handle_encode(algo_choice, input_file, output_file, secret_message):
    """Encodes a message using the chosen algorithm."""
    algorithm = ALGORITHMS[algo_choice]
    logger.info(f"Encoding using {algorithm['name']}. Output file will be: {output_file}")
    
    # Example of using tqdm for encoding progress
    for _ in tqdm(range(1), desc="Encoding Progress"):
        algorithm['encode'](input_file, output_file, secret_message)

def handle_decode(algo_choice, output_file):
    """Decodes a message using the chosen algorithm."""
    algorithm = ALGORITHMS[algo_choice]
    logger.info(f"Decoding using {algorithm['name']} and output file: {output_file}")
    
    # Example of using tqdm for decoding progress
    for _ in tqdm(range(1), desc="Decoding Progress"):
        decoded_message = algorithm['decode'](output_file)
    
    if decoded_message:
        print(f"Decoded message: {decoded_message}")
    else:
        print("Failed to decode the message.")

def handle_accuracy_check():
    """Calculates and displays the accuracy of the decoded message."""
    original_message = input("Enter the original secret message for accuracy calculation: ")

    display_algorithm_menu()
    algo_choice = get_user_choice(len(ALGORITHMS))

    if algo_choice is None or algo_choice not in ALGORITHMS:
        logger.warning("Invalid algorithm choice.")
        print("\nInvalid algorithm choice!")
        return

    input_file = get_file_path(algo_choice, is_input=True)
    output_file = get_file_path(algo_choice, is_input=False)

    algorithm = ALGORITHMS[algo_choice]
    
    # Example of using tqdm for accuracy calculation
    for _ in tqdm(range(1), desc="Accuracy Calculation Progress"):
        calculate_accuracy(original_message, algorithm, input_file_path=input_file, output_file_path=output_file)

def handle_main_choice(choice):
    """Handles the user's main menu choice."""
    logger.info(f"User selected main menu choice: {choice}")
    if choice == 1:
        handle_algorithm_choice(encode=True)
    elif choice == 2:
        handle_algorithm_choice(encode=False)
    elif choice == 3:
        handle_accuracy_check()
    elif choice == 4:
        logger.info("Exiting the program.")
        sys.exit(0)
    else:
        logger.warning("Invalid choice entered by user.")
        print("\nEnter a valid choice!")

def main():
    """Main function to run the CLI program."""
    while True:
        display_menu(["Encode a message", "Decode a message", "Calculate accuracy", "Exit"], "Select an option")
        choice = get_user_choice(4)
        if choice is not None:
            handle_main_choice(choice)

if __name__ == "__main__":
    main()
