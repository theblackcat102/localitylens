import os
import pwd
import fnmatch
from pathlib import Path
from datetime import datetime, date
from magika import Magika

def get_file_metadata(file_path):
    # Get basic file stats
    try:
        stats = os.stat(file_path)
    except FileNotFoundError:
        return 'unknown', date.min, date.min, -1
    # Fetch the owner of the file
    try:
        owner = pwd.getpwuid(stats.st_uid).pw_name
    except KeyError:
        owner = 'Unknown'  # In case the user ID doesn't match any user

    # Convert creation and modification times to readable format
    creation_date = datetime.fromtimestamp(stats.st_ctime).strftime('%Y-%m-%d %H:%M:%S')
    modified_date = datetime.fromtimestamp(stats.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
    # in bytes
    size = stats.st_size

    return owner, creation_date, modified_date, size

def find_files_and_dirs(directory, ignore_patterns):
    matches = []
    for root, dirnames, filenames in os.walk(directory, topdown=True):
        # Filter out ignored directories
        dirnames[:] = [d for d in dirnames if not any(fnmatch.fnmatch(os.path.join(root, d), pattern) for pattern in ignore_patterns)]
        
        # Add directories not ignored to matches with a tag
        for dirname in dirnames:
            dir_path = os.path.join(root, dirname)
            if not any(fnmatch.fnmatch(dir_path, pattern) for pattern in ignore_patterns):
                owner, creation_date, modified_date, size = get_file_metadata(dir_path)
                matches.append((dir_path, 0, owner, creation_date, modified_date, size))
        # Add files not ignored to matches with a tag
        for filename in filenames:
            file_path = os.path.join(root, filename)
            if not any(fnmatch.fnmatch(file_path, pattern) for pattern in ignore_patterns):
                owner, creation_date, modified_date, size = get_file_metadata(file_path)
                matches.append((file_path, 1, owner, creation_date, modified_date, size))
    return matches


if __name__ == "__main__":
    model = Magika()
    # Specify the root directory to search from, e.g., '.', for the current directory
    root_directory = '/home/theblackcat102'

    # List of patterns to ignore, similar to what might be found in a .gitignore file
    # Note: Patterns now include paths relative to the root directory
    ignore_patterns = ['*/.env', '*/.venv', '*/node_modules/*', '*/.git/*', '*/env', '*/.npm', '*/.vscode', '*/.config', '*/.mozilla', '*/snap']

    # Find files and directories, excluding the ones that match the ignore_patterns
    found_items = find_files_and_dirs(root_directory, ignore_patterns)

    # Print the paths of the items found along with their type
    for params in found_items:
        path, item_type, owner, creation_date, modified_date, size = params
        if item_type:
            directory = os.path.dirname(path)
            filename = os.path.basename(path)
            if filename[-5:] == '.lock':
                continue
            result = model.identify_paths([ Path(path) ])[0].output
            metadata = {}
            if size >= 0:
                metadata['size_bytes'] = size
            if hasattr(result, 'group'):
                metadata['group'] = result.group
            if hasattr(result, 'mime_type'):
                metadata['mime_type'] = result.mime_type
            print(filename, metadata)
        else:
            print(f"{path} ({item_type}) - Owner: {owner}, Created: {creation_date}, Modified: {modified_date} {size}")
