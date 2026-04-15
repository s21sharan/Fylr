"""
Live filesystem watcher that monitors a directory for new files
and suggests where to organize them using AI.
"""
import os
import sys
import json
import time
import logging
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Configure logging to stderr so it doesn't interfere with stdout protocol
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger('live_watcher')

# Supported file extensions
SUPPORTED_EXTENSIONS = {'.pdf', '.txt', '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.webp'}


def categorize_file(file_path, summary, online_mode=False):
    """Use LLM to suggest a category folder for the file based on its summary."""
    prompt = f"""Based on this file summary, suggest a single category folder name for organizing this file.
The category should be simple and general (e.g., Academic, Research, Images, Documents, Finance, Medical, Legal, Personal, Work, etc.).

File: {os.path.basename(file_path)}
Summary: {summary}

Respond with ONLY the category name, nothing else. Use a single word or two words max with no special characters."""

    try:
        if online_mode:
            from openai import OpenAI
            from dotenv import load_dotenv
            load_dotenv()
            client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
            if not client.api_key:
                logger.warning("No OpenAI API key found, falling back to offline mode")
                online_mode = False
            else:
                response = client.chat.completions.create(
                    model="gpt-4-turbo-preview",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0,
                    max_tokens=20
                )
                return response.choices[0].message.content.strip()

        if not online_mode:
            from ollama import Client
            ollama_client = Client(host="http://localhost:11434")
            response = ollama_client.chat(
                model='mistral',
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0, "num_predict": 20}
            )
            return response['message']['content'].strip()
    except Exception as e:
        logger.error(f"Error categorizing file: {e}")
        # Fallback: guess category from extension
        ext = os.path.splitext(file_path)[1].lower()
        if ext in {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.webp'}:
            return "Images"
        elif ext == '.pdf':
            return "Documents"
        else:
            return "General"


class NewFileHandler(FileSystemEventHandler):
    """Handler that processes newly created files in the watched directory."""

    def __init__(self, watch_directory, online_mode=False):
        super().__init__()
        self.watch_directory = watch_directory
        self.online_mode = online_mode
        # Track files we've already processed to avoid duplicates
        self.processed_files = set()

    def on_created(self, event):
        if event.is_directory:
            return

        file_path = event.src_path
        ext = os.path.splitext(file_path)[1].lower()

        if ext not in SUPPORTED_EXTENSIONS:
            return

        if file_path in self.processed_files:
            return

        self.processed_files.add(file_path)
        logger.info(f"New file detected: {file_path}")

        # Wait briefly for the file to finish writing
        time.sleep(1)

        # Make sure file still exists and is non-empty
        if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
            logger.warning(f"File disappeared or is empty: {file_path}")
            return

        try:
            # Import get_file_summary from the organizer module
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from initial_organize_electron import get_file_summary

            # Get a summary of the file
            summary = get_file_summary(file_path, online_mode=self.online_mode)

            if not summary:
                summary = f"File: {os.path.basename(file_path)}"

            # Get a category suggestion
            category = categorize_file(file_path, summary, online_mode=self.online_mode)

            # Build the suggested destination path
            parent_dir = os.path.dirname(file_path)
            filename = os.path.basename(file_path)
            suggested_dst = os.path.join(parent_dir, category, filename)

            suggestion = {
                "src_path": file_path,
                "dst_path": suggested_dst,
                "category": category,
                "summary": summary,
                "filename": filename
            }

            # Print the suggestion on stdout using the SUGGESTION: protocol
            print(f"SUGGESTION:{json.dumps(suggestion)}", flush=True)
            logger.info(f"Suggestion emitted for {filename} -> {category}")

        except Exception as e:
            logger.error(f"Error processing file {file_path}: {e}")


def main():
    if len(sys.argv) < 2:
        print("ERROR:Missing configuration argument", flush=True)
        sys.exit(1)

    try:
        config = json.loads(sys.argv[1])
    except json.JSONDecodeError:
        print("ERROR:Invalid JSON configuration", flush=True)
        sys.exit(1)

    directory = config.get("directory", "")
    online_mode = config.get("online_mode", False)

    if not directory or not os.path.isdir(directory):
        print(f"ERROR:Invalid directory path: {directory}", flush=True)
        sys.exit(1)

    # Force bool conversion
    if isinstance(online_mode, str):
        online_mode = online_mode.lower() == 'true'

    logger.info(f"Starting live watcher on: {directory}")
    logger.info(f"Online mode: {online_mode}")

    # Signal that the watcher has started successfully
    print("STATUS:watching", flush=True)

    handler = NewFileHandler(directory, online_mode=online_mode)
    observer = Observer()
    observer.schedule(handler, directory, recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()

    observer.join()
    logger.info("Live watcher stopped")


if __name__ == "__main__":
    main()
