import os
import sys
import json
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import PyPDF2
from PIL import Image
import mimetypes
import hashlib
import csv
import time
import base64
from dotenv import load_dotenv
import logging

# Load environment variables
load_dotenv()

# Ensure the llm package is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from llm import get_provider

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.StreamHandler(sys.stdout),  # Output to console
        logging.FileHandler('initial_organize.log', mode='w')  # Output to file, overwrite each run
    ]
)
logger = logging.getLogger('initial_organizer')

# Add a handler to ensure we see all logs
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# Set the root logger level to DEBUG
logging.getLogger().setLevel(logging.DEBUG)

# Token and call limits
TOKEN_LIMIT = 30000
CALL_LIMIT = 10
total_tokens_used = 0
total_api_calls = 0
start_time = None
last_update_time = None

def update_token_usage(tokens, operation_name):
    """Update token usage and check limits"""
    global total_tokens_used, total_api_calls, start_time, last_update_time

    # Initialize timing if first call
    if start_time is None:
        start_time = time.time()
        last_update_time = start_time

    # Update counters
    total_tokens_used += tokens
    total_api_calls += 1

    # Calculate current rate
    current_time = time.time()
    time_since_last = current_time - last_update_time
    last_update_time = current_time

    # Check limits
    if total_tokens_used >= TOKEN_LIMIT:
        logger.warning(f"Token limit reached! Used {total_tokens_used} tokens out of {TOKEN_LIMIT}")
        print(f"TOKEN_LIMIT_REACHED:{total_tokens_used}")
        return False

    if total_api_calls >= CALL_LIMIT:
        logger.warning(f"Call limit reached! Made {total_api_calls} calls out of {CALL_LIMIT}")
        print(f"CALL_LIMIT_REACHED:{total_api_calls}")
        return False

    # Log usage
    logger.info(f"Token usage update - Operation: {operation_name}")
    logger.info(f"Total tokens used: {total_tokens_used}/{TOKEN_LIMIT}")
    logger.info(f"Total API calls: {total_api_calls}/{CALL_LIMIT}")
    logger.info(f"Time since last call: {time_since_last:.2f}s")

    # Send usage to frontend
    print(f"TOKEN_USAGE:{total_tokens_used}")
    print(f"CALL_USAGE:{total_api_calls}")

    return True

FILE_PROMPT = """
You are an AI assistant tasked with organizing files based on their summaries. You will be provided with a list of source files and a summary of their contents. Your goal is to organize these files by adding ONE category subfolder to their existing path structure.

Rules for organizing:
1. The dst_path MUST preserve the original file path
2. Add ONLY ONE new subfolder under the original path to categorize the file
3. Use consistent naming conventions with underscores
4. Categories should be simple like: Academic, Research, Images, Documents, etc.
5. Do not create deep nested folders

Please return your response as a JSON object matching the following schema:

```json
{
  "files": [
    {
      "src_path": "original file path",
      "dst_path": "original_path/category/filename"
    }
  ]
}
```

For example, if a file is at "/Users/john/Documents/paper.pdf", and it's an academic paper,
the dst_path should be "/Users/john/Documents/Academic/paper.pdf"

IMPORTANT:
- The dst_path must preserve the original path structure
- Add only ONE new subfolder for categorization
- Do not create multiple nested category folders
""".strip()

def is_image_file(file_path):
    """Check if a file is an image based on its mimetype"""
    mime_type, _ = mimetypes.guess_type(file_path)
    return mime_type and mime_type.startswith('image/')

def log_mode_usage(function_name, online_mode):
    """Log the mode being used in a function"""
    mode_str = 'ONLINE (OpenAI)' if online_mode else 'OFFLINE (Local)'
    logger.info(f"Function {function_name} using {mode_str} mode, value={online_mode}, type={type(online_mode)}")
    print(f"Function {function_name} using {mode_str} mode, value={online_mode}, type={type(online_mode)}")
    return online_mode

def classify_image(file_path, online_mode=False):
    """Classify the contents of an image file using the provider's vision capability"""
    online_mode = log_mode_usage("classify_image", online_mode)
    try:
        # Check limits before making API call
        if not update_token_usage(0, "classify_image_precheck"):
            logger.warning("Token or call limit reached")
            return f"Image file from {os.path.basename(file_path)}"

        provider = get_provider(online_mode)

        with open(file_path, "rb") as image_file:
            image_bytes = image_file.read()

        prompt = "Describe what you see in this image concisely for file organization purposes."
        response = provider.vision(image_bytes, prompt, max_tokens=300)

        if response.tokens_used:
            if not update_token_usage(response.tokens_used, "classify_image"):
                logger.warning("Token limit reached during image classification")
                return None

        summary = response.content.strip()
        if summary:
            logger.info(f"Vision Summary: {summary}")
            return f"Image containing {summary.lower()}"

        # If vision returned nothing, fall back to basic image info
        logger.info(f"Vision returned empty, using basic image analysis for: {file_path}")
        image = Image.open(file_path)
        width, height = image.size
        format_name = image.format
        return f"Image ({width}x{height} {format_name})"

    except Exception as e:
        logger.error(f"Error analyzing image: {str(e)}")
        return f"Image file from {os.path.basename(file_path)}"

def generate_file_name(summary, online_mode=False, max_length=30):
    """Generate a very concise file name based on the file summary"""
    prompt = {
        "task": "filename_generation",
        "instruction": "You are given the summary of the contents of a file. Generate an extremely concise filename (2-4 words maximum) with underscores between words. Use general naming conventions. Do not include the file extension.",
        "parameters": {
            "max_length": max_length,
            "format": "lowercase_with_underscores",
            "max_words": 3,
            "special_characters": "none",
            "word_separator": "_"
        },
        "summary": summary
    }

    # Check limits before making API call
    if not update_token_usage(0, "generate_file_name_precheck"):
        logger.warning("Token or call limit reached")
        return None

    provider = get_provider(online_mode)
    logger.info(f"Using {provider.name} for filename generation")

    response = provider.chat(
        [{"role": "user", "content": json.dumps(prompt)}],
        temperature=0,
        max_tokens=50,
    )

    if response.tokens_used:
        if not update_token_usage(response.tokens_used, "generate_file_name"):
            logger.warning("Token limit reached during filename generation")
            return None

    filename = response.content.strip()

    words = [word.strip().lower() for word in filename.split() if word.strip()]
    filename = '_'.join(words)
    filename = ''.join(c for c in filename if c.isalnum() or c == '_')

    if '_' not in filename and len(filename) > 3:
        new_filename = ''
        for i, char in enumerate(filename):
            if i > 0 and char.isupper():
                new_filename += '_' + char.lower()
            else:
                new_filename += char.lower()
        filename = new_filename

    while '__' in filename:
        filename = filename.replace('__', '_')

    filename = filename.strip('_')
    logger.info(f"Generated filename: {filename}")
    return filename

def get_file_summary(file_path, online_mode=False):
    """Get summary for a single file using the provider layer"""
    online_mode = log_mode_usage("get_file_summary", online_mode)
    try:
        if is_image_file(file_path):
            return classify_image(file_path, online_mode=online_mode)
        else:
            text = ""
            if file_path.lower().endswith('.pdf'):
                with open(file_path, 'rb') as file:
                    reader = PyPDF2.PdfReader(file)
                    for page in reader.pages:
                        page_text = page.extract_text()
                        if page_text:
                            text += page_text
                            if len(text) >= 1000:
                                text = text[:1000]
                                break
            else:
                with open(file_path, 'r', encoding='utf-8') as file:
                    text = file.read(1000)

            if text:
                prompt = """
You will be provided with the contents of a file along with its metadata. Provide a summary of the contents. The purpose of the summary is to organize files based on their content. To this end provide a concise but informative summary. Make the summary as specific to the file as possible.

Write your response a JSON object with the following schema:

```json
{
    "file_path": "path to the file including name",
    "summary": "summary of the content"
}
```
""".strip()

                file_content = {
                    "file_path": file_path,
                    "content": text
                }

                # Check limits before making API call
                if not update_token_usage(0, "get_file_summary_precheck"):
                    logger.warning("Token or call limit reached")
                    return None

                provider = get_provider(online_mode)
                logger.info(f"Using {provider.name} for file summary: {file_path}")

                response = provider.chat(
                    [
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": json.dumps(file_content)},
                    ],
                    temperature=0,
                    max_tokens=256,
                )

                if response.tokens_used:
                    if not update_token_usage(response.tokens_used, "get_file_summary"):
                        logger.warning("Token limit reached during file summary")
                        return None

                response_content = response.content

                try:
                    json_start = response_content.find('{')
                    json_end = response_content.rfind('}') + 1
                    if json_start >= 0 and json_end > json_start:
                        json_str = response_content[json_start:json_end]
                        result = json.loads(json_str)
                        logger.info(f"Summary: {result['summary']}")
                        return result["summary"]
                    else:
                        logger.info(f"Summary: {response_content.strip()}")
                        return response_content.strip()
                except Exception as e:
                    logger.error(f"Error parsing JSON response: {str(e)}")
                    logger.info(f"Using raw response as summary: {response_content.strip()}")
                    return response_content.strip()
            else:
                return None
    except Exception as e:
        logger.error(f"Error processing {file_path}: {str(e)}")
        return None

def get_file_hash(file_path):
    """Calculate SHA-256 hash of a file"""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def print_separator():
    print("\n" + "=" * 80)

def analyze_directory(directory_path, online_mode=False):
    """Analyze the directory and return the file structure data"""
    online_mode = log_mode_usage("analyze_directory", online_mode)
    logger.info(f"Starting directory analysis in {'ONLINE' if online_mode else 'OFFLINE'} mode")

    provider = get_provider(online_mode)

    if online_mode:
        logger.info("ONLINE MODE: Using OpenAI API for file analysis and organization")
        print("ONLINE MODE: Using OpenAI API for file analysis and organization")

        # Check limits before making API call
        if not update_token_usage(0, "analyze_directory_precheck"):
            logger.warning("Token or call limit reached, switching to offline mode")
            online_mode = False
            provider = get_provider(online_mode)
            print("MODE_SWITCH:offline")

        if online_mode:
            # Test connectivity
            try:
                print("Testing API connectivity...")
                test_response = provider.chat(
                    [{"role": "user", "content": "Respond with OK if you receive this message."}],
                    max_tokens=10,
                )
                test_result = test_response.content.strip()
                print(f"API test result: {test_result}")
                logger.info(f"API test successful: {test_result}")

                if test_response.tokens_used:
                    if not update_token_usage(test_response.tokens_used, "analyze_directory_test"):
                        logger.warning("Token limit reached during directory analysis test")
                        online_mode = False
                        provider = get_provider(online_mode)
                        print("MODE_SWITCH:offline")
            except Exception as e:
                print(f"API test failed: {str(e)}")
                logger.error(f"API test failed: {str(e)}")
                online_mode = False
                provider = get_provider(online_mode)
                print("MODE_SWITCH:offline")
    else:
        logger.info("OFFLINE MODE: Using Local LLM (Ollama) for file analysis and organization")
        print("OFFLINE MODE: Using Local LLM (Ollama) for file analysis and organization")

    files_to_process = []

    for root, _, files in os.walk(directory_path):
        for file in files:
            file_path = os.path.join(root, file)
            if file.lower().endswith(('.pdf', '.txt')) or is_image_file(file_path):
                files_to_process.append(file_path)

    print_separator()
    logger.info(f"Found {len(files_to_process)} files to process")
    print(f"Found {len(files_to_process)} files to process")
    print_separator()

    file_summaries = []

    print("GENERATING FILE SUMMARIES:")
    max_workers = 5 if online_mode else 3
    total = len(files_to_process)
    progress_lock = threading.Lock()
    progress_counter = [0]  # mutable container for closure

    def summarize_file(file_path):
        print(f"\nAnalyzing: {file_path}")
        summary = get_file_summary(file_path, online_mode=online_mode)
        with progress_lock:
            progress_counter[0] += 1
            done = progress_counter[0]
        print(f"PROGRESS:{json.dumps({'file': os.path.basename(file_path), 'done': done, 'total': total})}", flush=True)
        if summary:
            print(f"Summary: {summary}")
            return {"file_path": file_path, "summary": summary}
        return None

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = executor.map(summarize_file, files_to_process)

    file_summaries = [r for r in results if r is not None]

    # Signal that all file summaries are complete
    print(f"PROGRESS:{json.dumps({'file': 'all', 'done': total, 'total': total})}", flush=True)

    if file_summaries:
        formatted_input = []
        for summary in file_summaries:
            formatted_input.append({
                "file_path": summary["file_path"],
                "summary": summary["summary"]
            })

        print_separator()
        print("SENDING TO LLM:")
        print("\nSystem Prompt:")
        print(FILE_PROMPT)
        print("\nFormatted Input:")
        print(json.dumps(formatted_input, indent=2))
        print_separator()

        # Add explicit JSON formatting instruction
        messages = [
            {"role": "system", "content": "You must respond with ONLY valid JSON. No other text or explanations. The JSON must follow the schema: {\"files\": [{\"src_path\": \"path\", \"dst_path\": \"original_path/category/filename\"}]}"},
            {"role": "system", "content": FILE_PROMPT},
            {"role": "user", "content": json.dumps(formatted_input)}
        ]

        logger.info(f"Using {provider.name} for file structure generation")
        print(f"\nSENDING REQUEST TO {provider.name.upper()} FOR FILE STRUCTURE GENERATION")

        try:
            structure_response = provider.chat(
                messages,
                temperature=0,
                max_tokens=2048,
            )
            response_content = structure_response.content.strip()
            logger.info(f"RECEIVED RESPONSE FROM {provider.name.upper()} FOR FILE STRUCTURE")
            print(f"RECEIVED RESPONSE FROM {provider.name.upper()} FOR FILE STRUCTURE")
        except Exception as e:
            logger.error(f"ERROR USING {provider.name.upper()} FOR FILE STRUCTURE: {str(e)}")
            print(f"ERROR USING {provider.name.upper()} FOR FILE STRUCTURE: {str(e)}")
            return {"files": []}

        try:
            # First try to parse the entire response as JSON
            try:
                result = json.loads(response_content)
                logger.info("Successfully parsed JSON response")
            except json.JSONDecodeError:
                # If that fails, try to extract JSON from the response
                logger.warning("Failed to parse full response as JSON, attempting to extract JSON portion")
                json_start = response_content.find('{')
                json_end = response_content.rfind('}') + 1
                if json_start >= 0 and json_end > json_start:
                    json_str = response_content[json_start:json_end]
                    result = json.loads(json_str)
                    logger.info("Successfully extracted and parsed JSON from response")
                else:
                    logger.error("Response is not in JSON format")
                    return {"files": []}

            if "files" in result and isinstance(result["files"], list):
                logger.info(f"Successfully generated file structure with {len(result['files'])} files")
                return result
            else:
                logger.error("Invalid structure in LLM response - missing 'files' array")
                return {"files": []}
        except Exception as e:
            logger.error(f"Error parsing response: {str(e)}")
            return {"files": []}

    logger.warning("No valid file summaries found")
    return {"files": []}

if __name__ == "__main__":
    # Test logging
    logger.debug("Debug test message")
    logger.info("Info test message")
    logger.warning("Warning test message")
    logger.error("Error test message")

    if len(sys.argv) < 2:
        logger.error("Missing configuration file path")
        print("Error: Missing configuration file path")
        sys.exit(1)

    config_path = sys.argv[1]

    try:
        with open(config_path, 'r') as config_file:
            config = json.load(config_file)
            directory = config.get('directory')
            online_mode = config.get('online_mode', True)  # Default to online mode if not specified

            # Debug the configuration that's being received
            logger.debug("="*50)
            logger.debug("RECEIVED CONFIG:")
            logger.debug(json.dumps(config, indent=2))
            logger.debug(f"PARSED ONLINE MODE: {online_mode}")
            logger.debug(f"ONLINE MODE TYPE: {type(online_mode)}")
            logger.debug("="*50)

            # Force conversion to bool in case we get a string
            if isinstance(online_mode, str):
                online_mode = online_mode.lower() == 'true'

            # Add more explicit logging for debugging
            logger.info("-" * 50)
            logger.info("STARTING FILE ORGANIZATION")
            logger.info(f"MODE: {'ONLINE (Using OpenAI API)' if online_mode else 'OFFLINE (Using Local Models)'}")
            logger.info(f"DIRECTORY: {directory}")
            logger.info("-" * 50)

            if not directory or not os.path.isdir(directory):
                logger.error(f"Invalid directory path: {directory}")
                print("Error: Invalid directory path")
                sys.exit(1)

            # Make sure we pass online_mode explicitly
            logger.info(f"Explicitly passing online_mode={online_mode} to analyze_directory")
            result = analyze_directory(directory, online_mode=online_mode)
            print(json.dumps(result))

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        print(f"Error: {str(e)}")
        sys.exit(1)
