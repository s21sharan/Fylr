import os
import sys
import json
from pathlib import Path
import logging
from openai import OpenAI
from ollama import Client
from dotenv import load_dotenv
from file_organizer import get_file_summary, generate_file_name
import base64
from PIL import Image

# Import the analyze_image_with_openai function
from test_openai_vision import analyze_image_with_openai

# Load environment variables
load_dotenv()

# Configure logging to output to both file and console
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.StreamHandler(sys.stdout),  # Output to console
        logging.FileHandler('rename_files.log')  # Output to file
    ]
)
logger = logging.getLogger('file_renamer')

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
    # Try to use the default model (will download automatically on first use)
    try:
        moondream_model = md.vl()
        logger.info("Moondream model initialized successfully (using default model)")
    except Exception as e:
        logger.warning(f"Failed to initialize Moondream with default model: {str(e)}")
        # Fallback to checking for local model file
        model_path = os.path.expanduser("~/Downloads/moondream-0_5b-int8.mf")
        if os.path.exists(model_path):
            moondream_model = md.vl(model=model_path)
            logger.info(f"Moondream model initialized successfully from: {model_path}")
        else:
            logger.warning(f"Moondream model file not found at: {model_path}")
except ImportError:
    logger.warning("Moondream package not installed. Simple image analysis will be used for offline mode.")
except Exception as e:
    logger.error(f"Failed to initialize Moondream model: {str(e)}")

def is_image_file(file_path):
    """Check if a file is an image based on its extension"""
    image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff'}
    return os.path.splitext(file_path)[1].lower() in image_extensions

def encode_image_to_base64(image_path):
    """Encode image to base64 string"""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def analyze_image_with_moondream(image_path):
    """Analyze image using Moondream model or fallback to basic analysis"""
    try:
        image = Image.open(image_path)
        
        # If Moondream is available, use it
        if moondream_model:
            result = moondream_model.caption(image)
            caption = result["caption"]
            return f"Image containing {caption.lower()}"
        
        # Otherwise, use a simple fallback method
        width, height = image.size
        format_name = image.format
        mode = image.mode
        
        # Very basic image info without ML analysis
        image_summary = f"Image ({width}x{height} {format_name})"
        
        # If Ollama is available, try to use it for a better description based on this basic info
        if ollama_client:
            try:
                prompt = f"""Based on these image details: {width}x{height} {format_name} image named '{os.path.basename(image_path)}',
generate a very concise description that might help organize the file. Focus on what could be in this image based on the filename."""
                
                response = ollama_client.chat(
                    model='mistral',
                    messages=[{'role': 'user', 'content': prompt}],
                    options={"temperature": 0, "num_predict": 100}
                )
                
                summary = response['message']['content'].strip()
                return f"Image possibly containing {summary.lower()}"
            except:
                pass
        
        return image_summary
    except Exception as e:
        logger.error(f"Error analyzing image with local methods: {str(e)}")
        return f"Image file: {os.path.basename(image_path)}"

def generate_file_name(summary, online_mode=True, max_length=30):
    """Generate a very concise file name based on the file summary"""
    logger.info(f"Using {'OpenAI' if online_mode else 'Local LLM'} for filename generation")
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
        # Use OpenAI
        response = openai_client.chat.completions.create(
            model="gpt-4-turbo-preview",
            messages=[
                {"role": "user", "content": json.dumps(prompt)}
            ],
            temperature=0,
            max_tokens=50
        )
        # Only track token usage for OpenAI
        if online_mode:
            print(f"TOKEN_USAGE:{response.usage.total_tokens}")
        filename = response.choices[0].message.content.strip()
    else:
        # Use local LLM - no token tracking
        response = ollama_client.chat(
            model='mistral',
            messages=[{'role': 'user', 'content': json.dumps(prompt)}]
        )
        filename = response['message']['content'].strip()
    
    # Clean up the response
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
    
    return filename.strip('_')

def generate_filenames(files, online_mode=True):
    """Generate new filenames for the given files"""
    try:
        logger.info(f"Starting filename generation in {'online' if online_mode else 'offline'} mode")
        logger.info(f"Processing {len(files)} files")
        
        generated_names = {}
        for file in files:
            file_path = file['path']
            extension = os.path.splitext(file['name'])[1]
            
            logger.info(f"Processing file: {file_path}")
            
            # For images, use appropriate model based on mode
            if is_image_file(file_path):
                if online_mode:
                    logger.info("Using OpenAI Vision for image analysis")
                    summary = analyze_image_with_openai(file_path)
                    # Only track token usage for OpenAI in online mode
                    if online_mode and summary and hasattr(summary, 'usage'):
                        print(f"TOKEN_USAGE:{summary.usage.total_tokens}")
                else:
                    logger.info("Using Moondream for image analysis")
                    summary = analyze_image_with_moondream(file_path)
            else:
                # Get file summary using the function from file_organizer.py
                logger.info(f"Getting file summary using {'OpenAI' if online_mode else 'local LLM'}")
                summary = get_file_summary(file_path, online_mode)
                # Only track token usage for OpenAI in online mode
                if online_mode and summary and hasattr(summary, 'usage'):
                    print(f"TOKEN_USAGE:{summary.usage.total_tokens}")
            
            if not summary:
                logger.warning(f"No summary found for {file['name']}, skipping")
                continue
            
            logger.info(f"Generated summary: {summary}")
            
            # Generate new filename using the function from file_organizer.py
            logger.info(f"Generating filename using {'OpenAI' if online_mode else 'local LLM'}")
            new_base = generate_file_name(summary, online_mode=online_mode)
            if not new_base:
                logger.warning(f"Could not generate filename for {file['name']}, skipping")
                continue
            
            logger.info(f"Generated new base name: {new_base}")
            generated_names[file['name']] = f"{new_base}{extension}"
            
        logger.info(f"Successfully generated names for {len(generated_names)} files")
        return {
            "success": True,
            "generated_names": generated_names
        }
        
    except Exception as e:
        logger.error(f"Error generating filenames: {str(e)}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }

def rename_files(files, new_names):
    """Rename files using the provided new names"""
    try:
        logger.info(f"Starting file renaming process")
        logger.info(f"Files to process: {json.dumps(files, indent=2)}")
        logger.info(f"New names mapping: {json.dumps(new_names, indent=2)}")
        
        results = []
        for file in files:
            try:
                file_path = file['path']
                original_name = file['name']
                new_name = new_names.get(original_name)
                
                if not new_name or new_name == original_name:
                    logger.info(f"Skipping {original_name} - no new name provided or name unchanged")
                    continue
                
                # Get directory and construct new path
                directory = os.path.dirname(file_path)
                new_path = os.path.join(directory, new_name)
                
                logger.info(f"Processing rename operation:")
                logger.info(f"  Original path: {file_path}")
                logger.info(f"  New path: {new_path}")
                
                # Ensure the new name is unique
                base, ext = os.path.splitext(new_name)
                counter = 1
                while os.path.exists(new_path):
                    new_name = f"{base}_{counter}{ext}"
                    new_path = os.path.join(directory, new_name)
                    counter += 1
                    logger.info(f"  Adjusted new path (for uniqueness): {new_path}")
                
                # Check if source file exists
                if not os.path.exists(file_path):
                    logger.error(f"Source file does not exist: {file_path}")
                    continue
                
                # Check if we have write permission
                if not os.access(os.path.dirname(file_path), os.W_OK):
                    logger.error(f"No write permission for directory: {os.path.dirname(file_path)}")
                    continue
                
                # Perform the rename operation
                os.rename(file_path, new_path)
                logger.info(f"Successfully renamed {original_name} to {new_name}")
                
                results.append({
                    "original": original_name,
                    "new": new_name
                })
                
            except Exception as e:
                logger.error(f"Error processing file {file.get('name', 'unknown')}: {str(e)}")
                continue
        
        if results:
            logger.info(f"Successfully renamed {len(results)} files")
            logger.info(f"Rename results: {json.dumps(results, indent=2)}")
            return {
                "success": True,
                "renamed_files": results
            }
        else:
            logger.warning("No files were renamed")
            return {
                "success": False,
                "error": "No files were renamed"
            }
        
    except Exception as e:
        logger.error(f"Error in rename_files: {str(e)}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }

if __name__ == "__main__":
    logger.info("Starting rename_files.py script")
    
    if len(sys.argv) != 2:
        logger.error("Usage: python rename_files.py <config_path>")
        sys.exit(1)
        
    config_path = sys.argv[1]
    logger.info(f"Loading configuration from: {config_path}")
    
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
            logger.info(f"Configuration loaded: {json.dumps(config, indent=2)}")
        
        if 'action' not in config:
            logger.error("Error: 'action' not specified in config")
            sys.exit(1)
        
        # Get online_mode from config, default to True if not specified
        online_mode = config.get('online_mode', True)
        logger.info(f"Running in {'online' if online_mode else 'offline'} mode")
            
        if config['action'] == 'generate':
            logger.info("Starting filename generation")
            result = generate_filenames(config['files'], online_mode)
        elif config['action'] == 'rename':
            logger.info("Starting file renaming")
            result = rename_files(config['files'], config['new_names'])
        else:
            logger.error(f"Error: Unknown action '{config['action']}'")
            sys.exit(1)
            
        logger.info(f"Operation completed. Result: {json.dumps(result, indent=2)}")
        print(json.dumps(result))  # Ensure result is printed to stdout
        
    except Exception as e:
        logger.error(f"Error in main execution: {str(e)}", exc_info=True)
        sys.exit(1) 