# Audio Steganography CLI

Audio Steganography is a technique used to hide secret messages within audio files. This project provides a command-line interface (CLI) for encoding and decoding messages in audio files using various steganography algorithms. Additionally, it provides a method to calculate the accuracy of the decoded message against the original secret message.

## Contents

- **Original Audio Sample**: `input/original_sample.wav`
- **Supported Algorithms**:
  - Standard LSB Steganography
  - Enhanced LSB Steganography (without flipping)
  - Enhanced LSB Steganography (with flipping)

## Algorithms Overview

### 1. Standard LSB Steganography

This algorithm hides the secret message in the least significant bits (LSB) of the audio file. It modifies the LSB of each byte in the audio data to encode the secret message. This method is simple and has minimal impact on audio quality but is relatively easy to detect.

- **Code File**: `algorithms/basic_lsb_steganography.py`
- **Output Audio File**: `output/basic_lsb_encoded.wav`

### 2. Enhanced LSB Steganography (without flipping)

This algorithm improves upon the standard LSB by encoding two bits per byte without flipping them unnecessarily. It uses more sophisticated bit manipulation techniques to minimize the detectability of the encoded message while maintaining better audio quality.

- **Code File**: `algorithms/enhanced_lsb_steganography_no_flip.py`
- **Output Audio File**: `output/enhanced_lsb_encoded_no_flip.wav`

### 3. Enhanced LSB Steganography (with flipping)

This algorithm further enhances the LSB steganography by using flipping techniques to reduce the pattern detectability. It checks and flips bits as needed to ensure that the encoded data is less detectable and maintains high audio quality.

- **Code File**: `algorithms/enhanced_lsb_steganography_with_flip.py`
- **Output Audio File**: `output/enhanced_lsb_encoded_with_flip.wav`

## Setup

To run this project, ensure you have Python installed (version 3.6 or higher).

1. **Clone the repository:**
   ```bash
   git clone https://github.com/yourusername/audio-steganography.git
   cd audio-steganography
   ```

2. **Install required dependencies:**
   If there are any dependencies listed in a `requirements.txt` file, install them using pip:
   ```bash
   pip install -r requirements.txt
   ```

3. **Directory Structure:**

   Ensure the following directory structure:

   ```
   audio-steganography/
   ├── cli/
   │   ├── config.py
   │   ├── helpers.py
   │   ├── main.py
   │   ├── accuracy.py
   ├── algorithms/
   │   ├── basic_lsb_steganography.py
   │   ├── enhanced_lsb_steganography_no_flip.py
   │   ├── enhanced_lsb_steganography_with_flip.py
   ├── utils/
   │   ├── logging_util.py
   ├── input/
   │   ├── original_sample.wav
   ├── output/
   ├── README.md
   └── requirements.txt
   ```

## Running the Application

The application is run through a command-line interface (CLI).

### Start the CLI

To start the CLI, run the following command in your terminal or command prompt:

```bash
python cli/main.py
```

### Options in the CLI

Once the CLI is running, you will see a menu with the following options:

1. **Encode a Message**: Select this option to encode a secret message into an audio file.
2. **Decode a Message**: Select this option to decode a secret message from an audio file.
3. **Calculate Accuracy**: Select this option to calculate the accuracy of the decoded message compared to the original secret message.
4. **Exit**: Exit the application.

### Encoding a Message

1. Choose the "Encode a Message" option.
2. Select the desired algorithm:
   - Standard LSB Steganography
   - Enhanced LSB Steganography (without flipping)
   - Enhanced LSB Steganography (with flipping)
3. Choose the input audio file (default is `original_sample.wav` or a custom file).
4. Enter the secret message you wish to encode.
5. The encoded audio will be saved to the output directory specified in `cli/config.py`.

### Decoding a Message

1. Choose the "Decode a Message" option.
2. Select the desired algorithm used for encoding.
3. Choose the input encoded audio file (default or a custom file).
4. The decoded message will be displayed in the terminal.

### Calculating Accuracy

1. Choose the "Calculate Accuracy" option.
2. Enter the original secret message used for encoding.
3. Choose the input audio file and output audio file (press Enter to use standard files).
4. Select the algorithm used for encoding and decoding.
5. The accuracy of the decoded message will be calculated and displayed in the terminal.

## Adding a New Algorithm

To add a new algorithm to the CLI, follow these steps:

1. **Create a new Python file** in the `algorithms/` directory for your new algorithm. For example, `my_new_algorithm.py`.

2. **Define `encode` and `decode` functions** in your new Python file:
   - `encode(input_file_path, output_file_path, secret_message)`: Encodes the secret message into the audio file.
   - `decode(input_file_path)`: Decodes the secret message from the audio file and returns it.

3. **Update `cli/config.py`** to include your new algorithm:

   ```python
   from algorithms import (
       basic_lsb_steganography,
       enhanced_lsb_steganography_no_flip,
       enhanced_lsb_steganography_with_flip,
       my_new_algorithm  # Import your new algorithm module
   )

   # Add your new algorithm to the ALGORITHMS dictionary
   ALGORITHMS = {
       1: {
           "name": "Basic LSB Steganography",
           "encode": basic_lsb_steganography.encode,
           "decode": basic_lsb_steganography.decode,
           "output_file": "output/basic_lsb_encoded.wav"
       },
       2: {
           "name": "Enhanced LSB Steganography (no flip)",
           "encode": enhanced_lsb_steganography_no_flip.encode,
           "decode": enhanced_lsb_steganography_no_flip.decode,
           "output_file": "output/enhanced_lsb_encoded_no_flip.wav"
       },
       3: {
           "name": "Enhanced LSB Steganography (with flip)",
           "encode": enhanced_lsb_steganography_with_flip.encode,
           "decode": enhanced_lsb_steganography_with_flip.decode,
           "output_file": "output/enhanced_lsb_encoded_with_flip.wav"
       },
       4: {
           "name": "My New Algorithm",  # Add a descriptive name for your algorithm
           "encode": my_new_algorithm.encode,
           "decode": my_new_algorithm.decode,
           "output_file": "output/my_new_algorithm_encoded.wav"
       }
   }
   ```

4. **Run the CLI**: Your new algorithm should now appear in the list of algorithms when encoding or decoding a message.

## Contributing

Feel free to contribute to this project by adding more features or improving the existing code. Follow the standard GitHub flow for contributions:

1. Fork the repository.
2. Create a new branch (`git checkout -b feature/my-new-feature`).
3. Commit your changes (`git commit -am 'Add new feature'`).
4. Push to the branch (`git push origin feature/my-new-feature`).
5. Create a new Pull Request.

---
