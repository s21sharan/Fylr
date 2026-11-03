import os
import sys
import json
import logging
import re
import base64

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

from llm import get_provider, resolve_provider

# Configure logging — stdout only, INFO level
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger('file_renamer')

def is_image_file(file_path):
    """Check if a file is an image based on its extension"""
    image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff'}
    return os.path.splitext(file_path)[1].lower() in image_extensions

def encode_image_to_base64(image_path):
    """Encode image to base64 string"""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

IMAGE_ANALYSIS_TOOL = {
    "type": "function",
    "function": {
        "name": "image_analysis",
        "description": "Analyze an image and return structured metadata for file naming.",
        "parameters": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "What type of image is this?"},
                "subject": {"type": "string", "description": "1-3 word specific subject of the image."},
                "summary": {"type": "string", "description": "One sentence description, 5-15 words."},
            },
            "required": ["category", "subject", "summary"],
        },
    },
}

_STOP_WORDS = {
    # grammar
    'a', 'an', 'the', 'in', 'on', 'at', 'of', 'with', 'and', 'is', 'are',
    'its', 'this', 'that', 'from', 'for', 'to', 'by', 'it', 'has', 'was',
    'also', 'known', 'as', 'while', 'being', 'into', 'their', 'other',
    'who', 'there', 'each', 'using', 'around',
    # image description filler
    'image', 'photo', 'photograph', 'picture', 'showing', 'featuring', 'shows',
    'depicts', 'depicted', 'scene', 'view', 'main', 'subject', 'captured',
    'close', 'up', 'closeup', 'rendering', 'render', 'features', 'contains',
    # adjectives that don't help identify content
    'majestic', 'prominent', 'beautiful', 'stunning', 'historic', 'large',
    'small', 'young', 'visible', 'casual', 'various', 'gray', 'grey',
    # moondream artifacts
    'urn', 'urns',
    # people/clothing (too generic for filenames)
    'man', 'woman', 'person', 'people', 'group', 'individual', 'individuals',
    'men', 'women', 'boy', 'girl', 'guy',
    'shirt', 'sweatshirt', 'jacket', 'pants', 'dress', 'hoodie', 'jersey',
    'wearing', 'word', 'letter',
    # action filler
    'pose', 'poses', 'posing', 'looks', 'looking', 'seen', 'sits',
    'standing', 'operating', 'taking', 'holding', 'positioned',
    # spatial/generic filler
    'front', 'back', 'behind', 'near', 'next', 'some', 'several',
    'pair', 'set', 'type', 'kind', 'style',
}

def extract_filename_from_summary(summary, max_words=3):
    """Extract a concise filename directly from a summary string, no LLM needed."""
    text = re.sub(r'^(image|the image)\s+(containing|of|showing|depicting|with|featuring|shows)?\s*', '', summary, flags=re.IGNORECASE)
    # Deduplicate while preserving order
    seen = set()
    words = []
    for w in re.findall(r'[a-zA-Z]{2,}', text):
        wl = w.lower()
        if wl not in _STOP_WORDS and wl not in seen:
            seen.add(wl)
            words.append(wl)
    words = words[:max_words]
    if not words:
        words = ['file']
    return '_'.join(words)

FILE_NAMING_TOOL = {
    "type": "function",
    "function": {
        "name": "file_naming",
        "description": "Analyze file content and produce a structured, well-named filename.",
        "parameters": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Broad file category. Examples: receipt, essay, photo, invoice, resume, notes, diagram, screenshot, spreadsheet, presentation, letter, report, form, contract, manual",
                },
                "subject": {
                    "type": "string",
                    "description": "1-2 word specific subject. What is it actually about? Examples: coffee_shop, linear_algebra, family_dog, quarterly_sales, job_application",
                },
                "filename": {
                    "type": "string",
                    "description": "Final filename: combine category and subject into 2-3 words, lowercase with underscores, no extension. Should be specific enough to distinguish from similar files but general enough to stay readable. Examples: coffee_receipt, algebra_notes, dog_photo, sales_report",
                },
            },
            "required": ["category", "subject", "filename"],
        },
    },
}


def generate_file_name(summary, online_mode=True, provider=None, max_length=30):
    """Generate a concise file name based on the file summary using tool schema."""
    # Local mode: extract filename from summary directly — no LLM call
    if not online_mode:
        return extract_filename_from_summary(summary)

    # Online mode: use tool calling for structured output
    if provider is None:
        provider = get_provider(online_mode=True)

    response = provider.chat(
        messages=[{"role": "user", "content": f"Analyze this file content and generate a filename:\n\n{summary}"}],
        tools=[FILE_NAMING_TOOL],
        tool_choice={"type": "function", "function": {"name": "file_naming"}},
        temperature=0,
        max_tokens=100,
    )
    print(f"TOKEN_USAGE:{response.tokens_used}")

    result = response.tool_call
    if not result:
        logger.warning("No tool call returned, falling back to extraction")
        return extract_filename_from_summary(summary)

    logger.info(f"Naming result — category: {result['category']}, subject: {result['subject']}, filename: {result['filename']}")

    filename = result["filename"].strip().lower()
    filename = re.sub(r'[^a-z0-9_]', '_', filename)
    filename = re.sub(r'_+', '_', filename).strip('_')
    return filename

def _process_single_file(file, online_mode, provider=None):
    """Process a single file: analyze content and generate a new name."""
    file_path = file['path']
    file_name = file['name']
    extension = os.path.splitext(file_name)[1]

    logger.info(f"Processing: {file_name}")

    if provider is None:
        provider = get_provider(online_mode)

    # Get content summary
    if is_image_file(file_path):
        with open(file_path, "rb") as img_file:
            image_bytes = img_file.read()
        prompt = "What equipment, objects, or activities are in this image? Be specific and concise."

        if online_mode:
            response = provider.vision(
                image_bytes, prompt,
                tools=[IMAGE_ANALYSIS_TOOL],
                tool_choice={"type": "function", "function": {"name": "image_analysis"}},
            )
            print(f"TOKEN_USAGE:{response.tokens_used}")
            if response.tool_call:
                summary = response.tool_call.get("summary", response.content or "")
                logger.info(f"Vision analysis — category: {response.tool_call.get('category')}, "
                            f"subject: {response.tool_call.get('subject')}, summary: {summary}")
            else:
                summary = response.content
        else:
            response = provider.vision(image_bytes, prompt)
            summary = response.content
            if summary:
                logger.info(f"[offline vision] {file_name}: {summary}")
    else:
        # Lazy import — only loads file_organizer (PyPDF2, etc.) when needed
        from file_organizer import get_file_summary
        summary = get_file_summary(file_path, online_mode)

    if not summary:
        logger.warning(f"[{file_name}] No summary, skipping")
        return None

    # Generate filename
    new_base = generate_file_name(summary, online_mode=online_mode, provider=provider)
    if not new_base:
        return None

    new_name = f"{new_base}{extension}"
    logger.info(f"{file_name} -> {new_name}")
    return (file_name, new_name)

def generate_filenames(files, online_mode=True, provider=None):
    """Generate new filenames for the given files"""
    try:
        logger.info(f"{'Online' if online_mode else 'Local'} mode — {len(files)} files")

        generated_names = {}

        if online_mode:
            # Online: concurrent API calls
            from concurrent.futures import ThreadPoolExecutor, as_completed
            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = {executor.submit(_process_single_file, f, online_mode, provider): f for f in files}
                for future in as_completed(futures):
                    result = future.result()
                    if result:
                        generated_names[result[0]] = result[1]
        else:
            # Local: sequential — Ollama can only run one inference at a time
            for f in files:
                result = _process_single_file(f, online_mode, provider)
                if result:
                    generated_names[result[0]] = result[1]

        logger.info(f"Generated names for {len(generated_names)} files")
        return {"success": True, "generated_names": generated_names}

    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=True)
        return {"success": False, "error": str(e)}

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
        
        online_mode = config.get('online_mode', True)
        provider_name = config.get('provider')
        provider = resolve_provider(online_mode, provider_name)
        logger.info(f"Mode: {'online' if online_mode else 'offline'}, provider: {provider.name}")

        if config['action'] == 'generate':
            logger.info("Starting filename generation")
            result = generate_filenames(config['files'], online_mode, provider=provider)
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