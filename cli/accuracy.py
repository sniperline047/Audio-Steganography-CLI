from utils.logging_util import setup_logger

logger = setup_logger(__name__)

def calculate_accuracy(original_message, algorithm, input_file_path, output_file_path):
    """
    Calculates the accuracy of the decoded message compared to the original message.

    :param original_message: The original secret message that was encoded
    :param algorithm: The algorithm object containing encode and decode methods
    :param input_file_path: Path to the input audio file used for encoding
    :param output_file_path: Path to the output audio file used for decoding
    :return: The accuracy of the decoded message as a percentage
    """
    try:
        # Validate inputs
        if not all([original_message, algorithm, input_file_path, output_file_path]):
            raise ValueError("One or more input parameters are missing.")

        # Encode the message into the audio file
        algorithm['encode'](input_file_path, output_file_path, original_message)

        # Decode the message from the output audio file
        decoded_message = algorithm['decode'](output_file_path)

        if decoded_message is None:
            logger.error("Decoded message is None.")
            return 0.0

        if not decoded_message:
            logger.error("Decoded message is empty.")
            return 0.0

        # Calculate the accuracy of the decoded message
        matches = sum(a == b for a, b in zip(original_message, decoded_message))
        accuracy = (matches / len(original_message)) * 100

        logger.info(f"Accuracy of decoded message: {accuracy:.2f}%")
        print(f"Accuracy of decoded message: {accuracy:.2f}%")
        return accuracy

    except Exception as e:
        logger.error(f"Error during accuracy calculation: {e}")
        return 0.0
