import wave
from utils.logging_util import setup_logger
import struct  # For packing and unpacking the message length

logger = setup_logger(__name__)

def check_flip(data, a, b):
    """
    Checks and flips bits if necessary to match the secret message.

    :param data: The byte to check
    :param a: First bit of the secret message
    :param b: Second bit of the secret message
    :return: The potentially modified byte
    """
    store = data & 12
    if store == 0 and (a == 0 and b == 0):
        return data
    elif store == 4 and (a == 0 and b == 1):
        return data
    elif store == 8 and (a == 1 and b == 0):
        return data
    elif store == 12 and (a == 1 and b == 1):
        return data
    else:
        # Flip the two least significant bits
        return data ^ 3

def encode(input_file_path, output_file_path, secret_message):
    """
    Encodes a secret message into an audio file using enhanced LSB steganography with flipping.

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
        if len(full_bits) > len(frame_bytes) * 4:  # Each frame can store 2 bits (4 frames needed per byte)
            raise ValueError("The secret message is too large to fit in the audio file.")

        # Encode the message into the frame bytes
        j = 0
        for i in range(0, len(full_bits), 2):
            a = int(full_bits[i])
            b = int(full_bits[i + 1])
            frame_bytes[j] = check_flip(frame_bytes[j], a, b)
            frame_bytes[j] = frame_bytes[j] & 243  # Clear the 3rd and 4th LSB
            if a == 0 and b == 1:
                frame_bytes[j] += 4
            elif a == 1 and b == 0:
                frame_bytes[j] += 8
            elif a == 1 and b == 1:
                frame_bytes[j] += 12
            j += 1

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
    Decodes a secret message from an audio file using enhanced LSB steganography with flipping.

    :param input_file_path: Path to the encoded audio file
    :return: The decoded secret message
    """
    try:
        logger.info("Decoding starts...")
        audio = wave.open(input_file_path, mode='rb')
        frame_bytes = bytearray(list(audio.readframes(audio.getnframes())))

        # Extract the first 32 bits to determine the message length
        length_bits = ''.join([str((frame_bytes[i] & 4) >> 2) + str((frame_bytes[i] & 8) >> 3) for i in range(16)])
        message_length = struct.unpack('>I', int(length_bits, 2).to_bytes(4, byteorder='big'))[0]

        logger.info(f"Extracted message length: {message_length} bits")

        # Now extract the message bits using the extracted length
        if message_length > len(frame_bytes) * 4:
            raise ValueError("The extracted message length is larger than the available audio data.")

        extracted = []
        for i in range(16, 16 + (message_length // 2)):
            byte = frame_bytes[i] & 12
            if byte == 0:
                extracted.extend([0, 0])
            elif byte == 4:
                extracted.extend([0, 1])
            elif byte == 8:
                extracted.extend([1, 0])
            elif byte == 12:
                extracted.extend([1, 1])

        # Convert bits back to characters
        decoded_message = ''.join(chr(int(''.join(map(str, extracted[i:i + 8])), 2)) for i in range(0, len(extracted), 8))

        logger.info(f"Successfully decoded: {decoded_message}")
        audio.close()
        return decoded_message
    except Exception as e:
        logger.error(f"Error during decoding: {e}")
        return None
