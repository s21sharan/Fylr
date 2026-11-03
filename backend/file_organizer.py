import os
import sys
import json
from pathlib import Path
import PyPDF2
from PIL import Image
import mimetypes
import hashlib
import csv
import time
import logging
from dotenv import load_dotenv
from llm import get_provider, resolve_provider

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('file_organizer')


FILE_PROMPT = """
You will be provided with list of source files and a summary of their contents. Organize all the files into a directory structure that optimally organizes the files using known conventions and best practices.
Follow good naming conventions.

Here are some examples of how to organize student files:

EXAMPLE 1 - Computer Science Student:
-Academic
    -CS101_Introduction_to_Programming_Notes.pdf
    -Data_Structures_Assignment_1_Solution.py
    -Algorithms_Midterm_Study_Guide.pdf
-Research
    -Machine_Learning_Research_Paper_Draft.docx
    -AI_Ethics_Literature_Review.pdf
-Project
    -Web_App_Final_Project_Code.zip
    -Mobile_App_Design_Documentation.pdf
-Study_Materials
    -Programming_Interview_Prep_Notes.pdf
    -System_Design_Study_Guide.pdf

EXAMPLE 2 - Medical Student:
-Academic
    -Anatomy_Lecture_Notes_Week_1.pdf
    -Pharmacology_Study_Guide.pdf
    -Pathology_Case_Studies.docx
-Clinical
    -Patient_Case_Reports_2023.pdf
    -Clinical_Rotation_Schedule.xlsx
-Research
    -Medical_Research_Proposal.docx
    -Literature_Review_Cancer_Treatment.pdf
-Study_Materials
    -USMLE_Step_1_Notes.pdf
    -Medical_Terminology_Flashcards.pdf

EXAMPLE 3 - Business Student:
-Academic
    -Financial_Accounting_Homework_1.xlsx
    -Marketing_Strategy_Presentation.pptx
    -Business_Ethics_Case_Study.pdf
-Internship
    -Summer_Internship_Report.docx
    -Company_Analysis_Presentation.pptx
-Research
    -Market_Research_Project.pdf
    -Business_Plan_Competition.docx
-Study_Materials
    -GMAT_Prep_Notes.pdf
    -Business_Case_Studies.pdf

Key principles for student file organization:
1. Group by academic subject or course
2. Separate research materials from coursework
3. Keep project work in dedicated folders
4. Maintain study materials separately
5. Use consistent naming: CourseName_ContentType_Description.ext

Your response should be a JSON object with the following schema:
```json
{
    "files": [
        {
            "src_path": "original file path",
            "dst_path": "category/filename.ext"
        }
    ]
}
```

IMPORTANT: The dst_path should be RELATIVE paths with just the category folder and filename, NOT absolute paths. Do not include the base directory in dst_path.
""".strip()

def is_image_file(file_path):
    """Check if a file is an image based on its mimetype"""
    mime_type, _ = mimetypes.guess_type(file_path)
    return mime_type and mime_type.startswith('image/')

FILE_SUMMARY_TOOL = {
    "type": "function",
    "function": {
        "name": "file_summary",
        "description": "Analyze file content and return structured metadata for organizing and naming.",
        "parameters": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Broad file category. Examples: essay, notes, receipt, invoice, resume, report, code, spreadsheet, letter, form, contract, manual, presentation, research_paper",
                },
                "subject": {
                    "type": "string",
                    "description": "1-3 word specific subject. What is it actually about? Examples: linear_algebra, tax_return, job_application, meeting_minutes, project_proposal",
                },
                "summary": {
                    "type": "string",
                    "description": "One sentence summary of the file content, 10-20 words. Specific enough to distinguish from similar files.",
                },
            },
            "required": ["category", "subject", "summary"],
        },
    },
}


def get_file_summary(file_path, online_mode=True):
    """Get summary for a single file using either OpenAI or local LLM"""
    logger.debug(f"Getting summary for file: {file_path}")
    logger.info(f"Using {'OpenAI' if online_mode else 'Local LLM'} for file summary")
    try:
        if is_image_file(file_path):
            logger.debug(f"File is an image: {file_path}")
            return f"Image file: {os.path.basename(file_path)}"
        else:
            # Handle text files
            logger.debug(f"File is a text document: {file_path}")
            text = ""
            if file_path.lower().endswith('.pdf'):
                logger.debug("Extracting text from PDF file")
                with open(file_path, 'rb') as file:
                    reader = PyPDF2.PdfReader(file)
                    for page in reader.pages:
                        page_text = page.extract_text()
                        if page_text:
                            text += page_text
                            if len(text) >= 1000:
                                text = text[:1000]
                                break
            else:  # .txt file
                logger.debug("Reading text file")
                with open(file_path, 'r', encoding='utf-8') as file:
                    text = file.read(1000)  # Read only the first 1000 characters

            if text:
                user_content = json.dumps({"file_path": file_path, "content": text})

                provider = get_provider(online_mode)

                if online_mode:
                    # Use provider with tool schema for structured output
                    logger.info("Making OpenAI API request...")
                    try:
                        messages = [
                            {"role": "system", "content": "Analyze the provided file content and return structured metadata."},
                            {"role": "user", "content": user_content}
                        ]
                        response = provider.chat(
                            messages,
                            tools=[FILE_SUMMARY_TOOL],
                            tool_choice={"type": "function", "function": {"name": "file_summary"}},
                            temperature=0,
                            max_tokens=256,
                        )
                        logger.info("OpenAI API request successful")
                        result = response.tool_call
                        logger.debug(f"Structured summary: {result}")
                        return f"{result['category']} — {result['subject']}: {result['summary']}"
                    except Exception as e:
                        logger.error(f"OpenAI API request failed: {str(e)}")
                        raise
                else:
                    # Use local LLM — no tool calling, fall back to JSON prompt
                    prompt = """Analyze the file and respond with JSON only:
{"category": "broad file type", "subject": "1-3 word topic", "summary": "one sentence description"}"""
                    logger.info("Making local LLM request...")
                    try:
                        messages = [
                            {"role": "system", "content": prompt},
                            {"role": "user", "content": user_content}
                        ]
                        response = provider.chat(messages)
                        logger.info("Local LLM request successful")
                        content = response.content
                        logger.debug(f"Local LLM response: {content}")
                    except Exception as e:
                        logger.error(f"Local LLM request failed: {str(e)}")
                        raise

                    try:
                        result = json.loads(content)
                        return f"{result['category']} — {result['subject']}: {result['summary']}"
                    except Exception as e:
                        logger.error(f"Error parsing JSON response: {str(e)}")
                        return content.strip()
            else:
                logger.warning("No text extracted from file.")
                return None
    except Exception as e:
        logger.error(f"Error processing {file_path}: {str(e)}", exc_info=True)
        return None

def get_file_hash(file_path):
    """Calculate SHA-256 hash of a file"""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def generate_file_name(summary, max_length=30, online_mode=True):
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
    
    provider = get_provider(online_mode)
    messages = [{"role": "user", "content": json.dumps(prompt)}]
    response = provider.chat(messages, temperature=0, max_tokens=50)
    filename = response.content.strip()
    
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

def generate_file_structure(file_summaries, online_mode=True):
    """Generate a proposed file structure based on file summaries"""
    logger.info(f"Using {'OpenAI' if online_mode else 'Local LLM'} for file structure generation")
    try:
        summaries_json = json.dumps(file_summaries, indent=2)
        
        provider = get_provider(online_mode)
        messages = [
            {"role": "system", "content": FILE_PROMPT},
            {"role": "user", "content": summaries_json}
        ]
        response = provider.chat(messages, temperature=0, max_tokens=2048)
        content = response.content
        
        try:
            result = json.loads(content)
            return result["files"]
        except Exception as e:
            logger.error(f"Error parsing JSON response: {str(e)}")
            return None
    except Exception as e:
        logger.error(f"Error generating file structure: {str(e)}")
        return None

def display_file_structure(file_structure):
    """Display the file structure in a readable tree format"""
    if not file_structure:
        print("No file structure to display.")
        return
    
    dir_structure = {}
    for file_info in file_structure:
        dst_path = file_info['dst_path']
        dst_dir = os.path.dirname(dst_path)
        filename = os.path.basename(dst_path)
        
        if dst_dir not in dir_structure:
            dir_structure[dst_dir] = []
        
        dir_structure[dst_dir].append({
            'filename': filename,
            'src_path': file_info['src_path']
        })
    
    print("\n" + "=" * 50)
    print("PROPOSED FILE STRUCTURE:")
    print("=" * 50)
    print("📁 ROOT")
    
    sorted_dirs = sorted(dir_structure.keys())
    
    if '' in sorted_dirs:
        for file_info in sorted(dir_structure[''], key=lambda x: x['filename']):
            print(f"├── 📄 {file_info['filename']}")
        sorted_dirs.remove('')
    
    for i, directory in enumerate(sorted_dirs):
        is_last_dir = (i == len(sorted_dirs) - 1)
        dir_parts = directory.split('/')
        dir_name = dir_parts[-1] if dir_parts else directory
        
        if is_last_dir:
            print(f"└── 📁 {dir_name}")
            prefix = "    "
        else:
            print(f"├── 📁 {dir_name}")
            prefix = "│   "
        
        files = sorted(dir_structure[directory], key=lambda x: x['filename'])
        for j, file_info in enumerate(files):
            is_last_file = (j == len(files) - 1)
            if is_last_file:
                print(f"{prefix}└── 📄 {file_info['filename']}")
            else:
                print(f"{prefix}├── 📄 {file_info['filename']}")

def analyze_and_organize_files(directory, online_mode=True):
    """Main function to analyze and organize files"""
    logger.info(f"Starting file organization in {'online' if online_mode else 'offline'} mode")
    if not os.path.isdir(directory):
        logger.error(f"Directory does not exist: {directory}")
        return
    
    # Initialize lists for files and their summaries
    files_to_process = []
    
    # Walk through directory
    for root, _, files in os.walk(directory):
        for file in files:
            file_path = os.path.join(root, file)
            if file.lower().endswith(('.pdf', '.txt')) or is_image_file(file_path):
                files_to_process.append(file_path)
    
    # Check for duplicates
    logger.info("Checking for duplicate files...")
    file_hashes = {}
    duplicates = {}
    
    for file_path in files_to_process:
        file_hash = get_file_hash(file_path)
        if file_hash in file_hashes:
            if file_hash not in duplicates:
                duplicates[file_hash] = [file_hashes[file_hash]]
            duplicates[file_hash].append(file_path)
        else:
            file_hashes[file_path] = file_path
    
    # Load existing summaries from CSV if it exists
    summaries_cache = {}
    csv_path = os.path.join(os.getcwd(), "file_summaries_cache.csv")
    if os.path.exists(csv_path):
        try:
            with open(csv_path, 'r', newline='', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    summaries_cache[row['file_hash']] = {
                        'summary': row['summary'],
                        'file_path': row['file_path'],
                        'last_modified': float(row['last_modified'])
                    }
            logger.info(f"Loaded {len(summaries_cache)} cached file summaries.")
        except Exception as e:
            logger.error(f"Error loading summaries cache: {str(e)}")
    
    # Analyze files
    logger.info("Starting file analysis")
    file_summaries = []
    new_or_updated_summaries = []
    
    for file_path in files_to_process:
        logger.info(f"Analyzing: {file_path}")
        
        file_hash = get_file_hash(file_path)
        last_modified = os.path.getmtime(file_path)
        
        use_cached = False
        if file_hash in summaries_cache:
            cached_entry = summaries_cache[file_hash]
            if float(cached_entry['last_modified']) >= last_modified:
                summary = cached_entry['summary']
                logger.info("Using cached summary")
                use_cached = True
        
        if not use_cached:
            summary = get_file_summary(file_path, online_mode)
            if summary:
                new_or_updated_summaries.append({
                    'file_hash': file_hash,
                    'file_path': file_path,
                    'summary': summary,
                    'last_modified': last_modified
                })
        
        if summary:
            logger.info(f"Summary: {summary}")
            file_summaries.append({
                "file_path": file_path,
                "summary": summary
            })
    
    # Update the CSV cache
    if new_or_updated_summaries:
        try:
            file_exists = os.path.exists(csv_path)
            
            with open(csv_path, 'a', newline='', encoding='utf-8') as csvfile:
                fieldnames = ['file_hash', 'file_path', 'summary', 'last_modified']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                
                if not file_exists:
                    writer.writeheader()
                
                for entry in new_or_updated_summaries:
                    writer.writerow(entry)
            
            logger.info(f"Updated cache with {len(new_or_updated_summaries)} new or modified file summaries.")
        except Exception as e:
            logger.error(f"Error updating summaries cache: {str(e)}")
    
    # Generate file structure
    if file_summaries:
        file_structure = generate_file_structure(file_summaries, online_mode)
        if file_structure:
            display_file_structure(file_structure)
            return file_structure
        else:
            logger.error("Failed to generate file structure")
            return None
    else:
        logger.warning("No files were successfully processed")
        return None

def rename_files(files, new_names):
    """Rename files using the provided new names"""
    try:
        results = []
        for file in files:
            file_path = file['path']
            new_name = new_names.get(file['name'])
            
            if not new_name or new_name == file['name']:
                continue
                
            directory = os.path.dirname(file_path)
            base, ext = os.path.splitext(new_name)
            counter = 1
            while os.path.exists(os.path.join(directory, new_name)):
                new_name = f"{base}_{counter}{ext}"
                counter += 1
            
            new_path = os.path.join(directory, new_name)
            os.rename(file_path, new_path)
            
            results.append({
                "original": file['name'],
                "new": new_name
            })
            
        return {
            "success": True,
            "renamed_files": results
        }
        
    except Exception as e:
        logger.error(f"Error renaming files: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Error: Missing configuration file path")
        sys.exit(1)
        
    config_path = sys.argv[1]
    
    try:
        with open(config_path, 'r') as config_file:
            config = json.load(config_file)
            action = config.get('action')
            online_mode = config.get('online_mode', True)
            provider_name = config.get('provider')
            logger.info(f"Configuration loaded - Mode: {'Online' if online_mode else 'Offline'}, provider: {provider_name or 'auto'}")
            
            if action == 'organize':
                directory = config.get('directory')
                if not directory or not os.path.isdir(directory):
                    print("Error: Invalid directory path")
                    sys.exit(1)
                result = analyze_and_organize_files(directory, online_mode)
                print(json.dumps(result))
                
            elif action == 'rename':
                if 'files' not in config or 'new_names' not in config:
                    print("Error: Missing required fields for rename action")
                    sys.exit(1)
                result = rename_files(config['files'], config['new_names'])
                print(json.dumps(result))
                
            else:
                print(f"Error: Unknown action '{action}'")
                sys.exit(1)
            
    except Exception as e:
        print(f"Error: {str(e)}")
        sys.exit(1) 