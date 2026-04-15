import os
import sys
import json
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import PyPDF2
from ollama import Client
from openai import OpenAI
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

# Initialize OpenAI client (will be used only in online mode)
openai_client = None
try:
    openai_api_key = os.getenv('OPENAI_API_KEY')
    if openai_api_key:
        openai_client = OpenAI(api_key=openai_api_key)
        logger.info("OpenAI client initialized successfully")
    else:
        logger.warning("OPENAI_API_KEY not found in environment variables. Online mode will not be available.")
except Exception as e:
    logger.error(f"Failed to initialize OpenAI client: {str(e)}")

# Initialize Ollama client (will be used only in offline mode)
ollama_client = None
try:
    ollama_client = Client(host="http://localhost:11434")
    logger.info("Ollama client initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize Ollama client: {str(e)}")

# Initialize Moondream model for image analysis
moondream_model = None
try:
    # Only import moondream if we're going to use it
    import moondream as md
    model_path = "/Users/sharans/Downloads/moondream-0_5b-int8.mf"
    if os.path.exists(model_path):
        moondream_model = md.vl(model=model_path)
        logger.info("Moondream model initialized successfully")
    else:
        logger.warning(f"Moondream model file not found at: {model_path}")
except ImportError:
    logger.warning("Moondream package not installed. Simple image analysis will be used for offline mode.")
except Exception as e:
    logger.error(f"Failed to initialize Moondream model: {str(e)}")

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
    logger.info(f"✅ Function {function_name} using {mode_str} mode, value={online_mode}, type={type(online_mode)}")
    print(f"✅ Function {function_name} using {mode_str} mode, value={online_mode}, type={type(online_mode)}")
    return online_mode

def classify_image(file_path, online_mode=False):
    """Classify the contents of an image file using Moondream model or OpenAI Vision"""
    online_mode = log_mode_usage("classify_image", online_mode)
    try:
        if online_mode and openai_client:
            # Check limits before making API call
            if not update_token_usage(0, "classify_image_precheck"):
                logger.warning("Token or call limit reached, switching to offline mode")
                online_mode = False
                print("MODE_SWITCH:offline")
            
            if online_mode:
                # Use OpenAI Vision API
                logger.info(f"Using OpenAI Vision API for image: {file_path}")
                with open(file_path, "rb") as image_file:
                    base64_image = base64.b64encode(image_file.read()).decode("utf-8")
                
                response = openai_client.chat.completions.create(
                    model="gpt-4-vision-preview",
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": "Describe what you see in this image concisely for file organization purposes."},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/jpeg;base64,{base64_image}"
                                    }
                                }
                            ]
                        }
                    ],
                    max_tokens=300
                )
                
                # Update token usage
                if hasattr(response, 'usage'):
                    if not update_token_usage(response.usage.total_tokens, "classify_image"):
                        logger.warning("Token limit reached during image classification")
                        return None
                
                summary = response.choices[0].message.content.strip()
                logger.info(f"OpenAI Vision Summary: {summary}")
                return f"Image containing {summary.lower()}"
        
        # Fallback to offline mode if online mode failed or limits reached
        logger.info("Using Moondream model for image classification")
        # First try Moondream if available
        if moondream_model:
            logger.info(f"Using Moondream for image: {file_path}")
            image = Image.open(file_path)
            caption = moondream_model.caption(image)["caption"]
            
            if caption:
                # Use the caption with local LLM to generate a more structured summary
                if ollama_client:
                    prompt = f"""Based on this image caption: "{caption}"
Generate a concise summary suitable for file organization. Focus on the main subject and context.
Return ONLY the summary text, no additional formatting or explanations."""
                    
                    response = ollama_client.chat(
                        model='mistral',
                        messages=[{'role': 'user', 'content': prompt}],
                        options={"temperature": 0, "num_predict": 100}
                    )
                    
                    summary = response['message']['content'].strip()
                    logger.info(f"Moondream Summary: {summary}")
                    return f"Image containing {summary.lower()}"
                else:
                    # No Ollama available, just use the caption directly
                    return f"Image containing {caption.lower()}"
        
        # If Moondream is not available or failed, use basic image analysis
        logger.info(f"Using basic image analysis for: {file_path}")
        try:
            image = Image.open(file_path)
            width, height = image.size
            format_name = image.format
            mode = image.mode
            
            # Very basic image info without ML analysis
            image_summary = f"Image ({width}x{height} {format_name})"
            
            # If Ollama is available, try to use it for a better description based on this basic info
            if ollama_client:
                try:
                    filename = os.path.basename(file_path)
                    prompt = f"""Based on these image details: {width}x{height} {format_name} image named '{filename}',
generate a very concise description that might help organize the file. Focus on what could be in this image based on the filename."""
                    
                    response = ollama_client.chat(
                        model='mistral',
                        messages=[{'role': 'user', 'content': prompt}],
                        options={"temperature": 0, "num_predict": 100}
                    )
                    
                    summary = response['message']['content'].strip()
                    return f"Image possibly containing {summary.lower()}"
                except Exception as inner_e:
                    logger.error(f"Error using Ollama for image description: {str(inner_e)}")
            
            return image_summary
        except Exception as img_e:
            logger.error(f"Error in basic image analysis: {str(img_e)}")
            return f"Image file from {os.path.basename(file_path)}"
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
    
    if online_mode:
        # Check limits before making API call
        if not update_token_usage(0, "generate_file_name_precheck"):
            logger.warning("Token or call limit reached, switching to offline mode")
            online_mode = False
            print("MODE_SWITCH:offline")
        
        if online_mode:
            logger.info("Using OpenAI for filename generation")
            response = openai_client.chat.completions.create(
                model="gpt-4-turbo-preview",
                messages=[{"role": "user", "content": json.dumps(prompt)}],
                temperature=0,
                max_tokens=50
            )
            
            # Update token usage
            if hasattr(response, 'usage'):
                if not update_token_usage(response.usage.total_tokens, "generate_file_name"):
                    logger.warning("Token limit reached during filename generation")
                    return None
            
            filename = response.choices[0].message.content.strip()
        else:
            logger.info("Using Ollama for filename generation")
            response = ollama_client.chat(
                model='mistral',
                messages=[{'role': 'user', 'content': json.dumps(prompt)}]
            )
            filename = response['message']['content'].strip()
    else:
        logger.info("Using Ollama for filename generation")
        response = ollama_client.chat(
            model='mistral',
            messages=[{'role': 'user', 'content': json.dumps(prompt)}]
        )
        filename = response['message']['content'].strip()
    
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
    """Get summary for a single file using OpenAI or local models"""
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
                
                if online_mode:
                    # Check limits before making API call
                    if not update_token_usage(0, "get_file_summary_precheck"):
                        logger.warning("Token or call limit reached, switching to offline mode")
                        online_mode = False
                        print("MODE_SWITCH:offline")
                    
                    if online_mode:
                        logger.info(f"Using OpenAI for file summary: {file_path}")
                        try:
                            response = openai_client.responses.create(
                                model="gpt-4-turbo-preview",
                                input=[
                                    {"role": "system", "content": prompt},
                                    {"role": "user", "content": json.dumps(file_content)}
                                ],
                                temperature=0,
                                max_tokens=256
                            )
                            response_content = response.output_text
                            
                            # Update token usage
                            if hasattr(response, 'usage'):
                                if not update_token_usage(response.usage.total_tokens, "get_file_summary"):
                                    logger.warning("Token limit reached during file summary")
                                    return None
                        except Exception as e:
                            logger.error(f"Error using OpenAI responses API: {str(e)}")
                            # Fallback to chat completions if responses API fails
                            response = openai_client.chat.completions.create(
                                model="gpt-4-turbo-preview",
                                messages=[
                                    {"role": "system", "content": prompt},
                                    {"role": "user", "content": json.dumps(file_content)}
                                ],
                                temperature=0,
                                max_tokens=256
                            )
                            response_content = response.choices[0].message.content
                            
                            # Update token usage
                            if hasattr(response, 'usage'):
                                if not update_token_usage(response.usage.total_tokens, "get_file_summary_fallback"):
                                    logger.warning("Token limit reached during file summary fallback")
                                    return None
                else:
                    logger.info(f"Using Ollama for file summary: {file_path}")
                    summary_response = ollama_client.chat(
                        model='mistral',
                        messages=[
                            {"role": "system", "content": prompt},
                            {"role": "user", "content": json.dumps(file_content)}
                        ],
                        options={"temperature": 0, "num_predict": 256}
                    )
                    response_content = summary_response['message']['content']
                
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
    
    # Add more explicit logging for debugging
    if online_mode:
        logger.info("🌐 ONLINE MODE: Using OpenAI API for file analysis and organization")
        print("🌐 ONLINE MODE: Using OpenAI API for file analysis and organization")
        
        # Check limits before making API call
        if not update_token_usage(0, "analyze_directory_precheck"):
            logger.warning("Token or call limit reached, switching to offline mode")
            online_mode = False
            print("MODE_SWITCH:offline")
        
        if online_mode:
            # Test OpenAI connectivity
            try:
                print("🧪 Testing OpenAI API connectivity...")
                test_response = openai_client.responses.create(
                    model="gpt-3.5-turbo",
                    input=[{"role": "user", "content": "Respond with OK if you receive this message."}],
                    max_tokens=10
                )
                test_result = test_response.output_text.strip()
                print(f"🧪 OpenAI API test result: {test_result}")
                logger.info(f"OpenAI API test successful: {test_result}")
                
                # Update token usage
                if hasattr(test_response, 'usage'):
                    if not update_token_usage(test_response.usage.total_tokens, "analyze_directory_test"):
                        logger.warning("Token limit reached during directory analysis test")
                        online_mode = False
                        print("MODE_SWITCH:offline")
            except Exception as e:
                print(f"❌ OpenAI API test failed: {str(e)}")
                logger.error(f"OpenAI API test failed: {str(e)}")
                online_mode = False
                print("MODE_SWITCH:offline")
    else:
        logger.info("🖥️ OFFLINE MODE: Using Local LLM (Ollama) for file analysis and organization")
        print("🖥️ OFFLINE MODE: Using Local LLM (Ollama) for file analysis and organization")
    
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
        
        if online_mode:
            logger.info("Using OpenAI for file structure generation")
            logger.info("📤 SENDING REQUEST TO OPENAI API FOR FILE STRUCTURE GENERATION")
            print("\n" + "*" * 80)
            print("📤 SENDING REQUEST TO OPENAI API FOR FILE STRUCTURE GENERATION")
            print("*" * 80)
            
            try:
                structure_response = openai_client.responses.create(
                    model="gpt-4-turbo-preview",
                    input=messages,
                    temperature=0,
                    max_tokens=2048
                )
                logger.info("📥 RECEIVED RESPONSE FROM OPENAI API FOR FILE STRUCTURE")
                print("\n" + "*" * 80)
                print("📥 RECEIVED RESPONSE FROM OPENAI API FOR FILE STRUCTURE")
                print("*" * 80)
                response_content = structure_response.output_text.strip()
            except Exception as e:
                logger.error(f"❌ ERROR USING OPENAI API FOR FILE STRUCTURE: {str(e)}")
                print(f"❌ ERROR USING OPENAI API FOR FILE STRUCTURE: {str(e)}")
                # Fallback to chat completions if responses API fails
                try:
                    structure_response = openai_client.chat.completions.create(
                        model="gpt-4-turbo-preview",
                        messages=messages,
                        temperature=0,
                        max_tokens=2048
                    )
                    response_content = structure_response.choices[0].message.content.strip()
                except Exception as e2:
                    logger.error(f"❌ ERROR USING OPENAI CHAT COMPLETIONS: {str(e2)}")
                    print(f"❌ ERROR USING OPENAI CHAT COMPLETIONS: {str(e2)}")
                    # Fallback to local LLM if both OpenAI methods fail
                    logger.warning("Falling back to local LLM for file structure generation")
                    print("Falling back to local LLM for file structure generation")
                    structure_response = ollama_client.chat(
                        model='mistral',
                        messages=messages,
                        options={"temperature": 0, "num_predict": 2048}
                    )
                    response_content = structure_response['message']['content'].strip()
        else:
            logger.info("Using Ollama for file structure generation")
            logger.info("📤 SENDING REQUEST TO LOCAL LLM (OLLAMA)")
            print("📤 SENDING REQUEST TO LOCAL LLM (OLLAMA)")
            structure_response = ollama_client.chat(
                model='mistral',
                messages=messages,
                options={"temperature": 0, "num_predict": 2048}
            )
            logger.info("📥 RECEIVED RESPONSE FROM LOCAL LLM")
            print("📥 RECEIVED RESPONSE FROM LOCAL LLM")
            response_content = structure_response['message']['content'].strip()
        
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
            logger.info(f"📣 Explicitly passing online_mode={online_mode} to analyze_directory")
            result = analyze_directory(directory, online_mode=online_mode)
            print(json.dumps(result))
            
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        print(f"Error: {str(e)}")
        sys.exit(1)