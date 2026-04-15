import os
import sys
import json
import logging

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('file_organizer')

def apply_changes(structure_path):
    """Apply the file structure changes"""
    try:
        with open(structure_path, 'r') as f:
            structure = json.load(f)

        logger.debug(f"Loaded structure: {json.dumps(structure, indent=2)}")

        # Get the base directory from the first file's source path
        # This ensures we're applying changes in the right directory
        base_directory = ""
        if structure.get('files') and len(structure['files']) > 0:
            first_file = structure['files'][0]
            src_path = first_file.get('src_path', '')
            if src_path:
                # Get the directory of the first source file
                base_directory = os.path.dirname(src_path)
                logger.debug(f"Base directory determined as: {base_directory}")

        moved_count = 0
        undo_manifest = []

        for file_info in structure.get('files', []):
            src_path = file_info.get('src_path')
            dst_path_relative = file_info.get('dst_path')

            if not src_path or not dst_path_relative:
                logger.warning(f"Missing path info: src={src_path}, dst={dst_path_relative}")
                continue

            # Make sure destination path is relative to the base directory
            # If dst_path is absolute, make it relative to base_directory
            if os.path.isabs(dst_path_relative):
                dst_filename = os.path.basename(dst_path_relative)
                dst_subdir = os.path.dirname(dst_path_relative).lstrip('/').lstrip('\\')
                dst_path = os.path.join(base_directory, dst_subdir, dst_filename)
            else:
                # If it's already relative, just join it with base_directory
                dst_path = os.path.join(base_directory, dst_path_relative)

            logger.debug(f"Moving file from: {src_path}")
            logger.debug(f"To: {dst_path}")

            # Create destination directory if it doesn't exist
            dst_dir = os.path.dirname(dst_path)
            os.makedirs(dst_dir, exist_ok=True)

            # Move and rename file
            try:
                os.rename(src_path, dst_path)
                moved_count += 1
                # Record the reverse operation for undo
                undo_manifest.append({"from": dst_path, "to": src_path})
                print(f"Moved: {os.path.basename(src_path)} -> {dst_path}")
                logger.debug(f"Successfully moved file: {src_path} -> {dst_path}")
            except Exception as e:
                error_msg = f"Error moving {os.path.basename(src_path)}: {str(e)}"
                print(error_msg)
                logger.error(error_msg, exc_info=True)

        # Output JSON result with undo manifest as the last line
        result = {"success": True, "moved": moved_count, "undo_manifest": undo_manifest}
        print(json.dumps(result))
        return True
    except Exception as e:
        error_msg = f"Error applying changes: {str(e)}"
        print(error_msg)
        logger.error(error_msg, exc_info=True)
        return False

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python apply_changes.py <structure_path>")
        sys.exit(1)
    
    structure_path = sys.argv[1]
    success = apply_changes(structure_path)
    
    if success:
        sys.exit(0)
    else:
        sys.exit(1)