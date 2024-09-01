import wave
from utils.logging_util import setup_logger
import struct  # For packing and unpacking the message length

logger = setup_logger(__name__)

def encode(input_file_path, output_file_path, secret_message):
    """
    Encodes a secret message into an audio file using basic LSB steganography with message length.

    :param input_file_path: Path to the input audio file
    :param output_file_path: Path to the output encoded audio file
    :param secret_message: The message to be encoded
    """
    try:
        logger.info("Encoding starts...")
        audio = wave.open(input_file_path, mode="rb")
        frame_bytes = bytearray(list(audio.readframes(audio.getnframes())))

        logger.info(f"Secret message: {secret_message}")
        # Convert the secret message to bits
        secret_message_bits = ''.join([bin(ord(i)).lstrip('0b').rjust(8, '0') for i in secret_message])
        message_length = len(secret_message_bits)

        # Pack the length of the message into 4 bytes (32 bits)
        length_bytes = struct.pack('>I', message_length)  # '>I' is big-endian unsigned int

        # Convert the length bytes to bits
        length_bits = ''.join([bin(byte).lstrip('0b').rjust(8, '0') for byte in length_bytes])

        # Combine length bits and message bits
        full_bits = length_bits + secret_message_bits

        # Ensure the message fits into the frame bytes
        if len(full_bits) > len(frame_bytes):
            raise ValueError("The secret message is too large to fit in the audio file.")

        # Encode the full bits into the frame bytes
        for i, bit in enumerate(full_bits):
            frame_bytes[i] = (frame_bytes[i] & 254) | int(bit)

        frame_modified = bytes(frame_bytes)

        # Write the modified bytes to the new audio file
        with wave.open(output_file_path, 'wb') as new_audio:
            new_audio.setparams(audio.getparams())
            new_audio.writeframes(frame_modified)

        audio.close()
        logger.info(f"Successfully encoded into {output_file_path}")
    except Exception as e:
        logger.error(f"Error during encoding: {e}")

def decode(input_file_path):
    """
    Decodes a secret message from an audio file using basic LSB steganography with message length.

    :param input_file_path: Path to the encoded audio file
    :return: The decoded secret message
    """
    try:
        logger.info("Decoding starts...")
        audio = wave.open(input_file_path, mode='rb')
        frame_bytes = bytearray(list(audio.readframes(audio.getnframes())))

        # Extract the first 32 bits to determine the message length
        length_bits = ''.join([str((frame_bytes[i] & 1)) for i in range(32)])
        message_length = struct.unpack('>I', int(length_bits, 2).to_bytes(4, byteorder='big'))[0]

        logger.info(f"Extracted message length: {message_length} bits")

        # Now extract the message bits using the extracted length
        if message_length > len(frame_bytes) * 8:
            raise ValueError("The extracted message length is larger than the available audio data.")

        message_bits = ''.join([str((frame_bytes[i + 32] & 1)) for i in range(message_length)])

        # Convert bits back to characters
        decoded_message = ''.join(chr(int(message_bits[i:i + 8], 2)) for i in range(0, len(message_bits), 8))

        logger.info(f"Successfully decoded: {decoded_message}")
        audio.close()
        return decoded_message

    except Exception as e:
        logger.error(f"Error during decoding: {e}")
        return None
