# Remove unused type:ignore comments identified by mypy
# This script removes type:ignore comments that mypy reports as unused

import subprocess
import re
from pathlib import Path

def get_unused_ignores():
    """Run mypy and extract all unused-ignore errors."""
    result = subprocess.run(
        ['python', '-m', 'mypy', 'code', '--show-error-codes'],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent
    )
    
    unused = []
    for line in result.stdout.splitlines():
        if '[unused-ignore]' in line:
            # Parse: code\path\file.py:123: error: Unused "type: ignore" comment  [unused-ignore]
            match = re.match(r'^(.+?):(\d+):', line)
            if match:
                file_path = match.group(1).replace('\\', '/')
                line_no = int(match.group(2))
                unused.append((file_path, line_no))
    
    return unused

def remove_type_ignore_from_line(line: str) -> str:
    """Remove type:ignore comment from a line."""
    # Remove various forms: # type: ignore, # type: ignore[code], etc.
    line = re.sub(r'\s*#\s*type:\s*ignore\[[\w-]+\]\s*', '', line)
    line = re.sub(r'\s*#\s*type:\s*ignore\s*$', '', line)
    line = re.sub(r'\s*#\s*type:\s*ignore\s+#.*$', lambda m: ' ' + m.group(0).split('#', 2)[-1], line)
    return line.rstrip() + '\n' if line.strip() else '\n'

def remove_unused_ignores(unused_list):
    """Remove unused type:ignore comments from files."""
    # Group by file
    by_file = {}
    for file_path, line_no in unused_list:
        if file_path not in by_file:
            by_file[file_path] = []
        by_file[file_path].append(line_no)
    
    # Process each file
    for file_path, line_numbers in by_file.items():
        full_path = Path(file_path)
        if not full_path.exists():
            print(f"Skipping {file_path} - file not found")
            continue
            
        # Read file
        with open(full_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # Remove type:ignore from specified lines (1-indexed)
        modified = False
        for line_no in line_numbers:
            if 1 <= line_no <= len(lines):
                old_line = lines[line_no - 1]
                new_line = remove_type_ignore_from_line(old_line)
                if old_line != new_line:
                    lines[line_no - 1] = new_line
                    modified = True
        
        # Write back if modified
        if modified:
            with open(full_path, 'w', encoding='utf-8') as f:
                f.writelines(lines)
            print(f"✓ Cleaned {file_path} ({len([ln for ln in line_numbers if 1 <= ln <= len(lines)])} ignores removed)")

if __name__ == '__main__':
    print("Finding unused type:ignore comments...")
    unused = get_unused_ignores()
    print(f"Found {len(unused)} unused type:ignore comments")
    
    if unused:
        print("\nRemoving unused ignores...")
        remove_unused_ignores(unused)
        print("\n✓ Done! Run mypy again to verify.")
    else:
        print("No unused ignores found!")
