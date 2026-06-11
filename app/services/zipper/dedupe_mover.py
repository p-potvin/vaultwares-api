import os
import sys
import json
import shutil
import argparse

def move_file_safe(src, dst_dir):
    if not os.path.exists(src):
        print(f"Warning: Source file not found for moving: {src}")
        return
    
    filename = os.path.basename(src)
    name, ext = os.path.splitext(filename)
    dst = os.path.join(dst_dir, filename)
    
    counter = 1
    while os.path.exists(dst):
        dst = os.path.join(dst_dir, f"{name}_{counter}{ext}")
        counter += 1
        
    try:
        shutil.move(src, dst)
        print(f"Moved duplicate: {src} -> {dst}")
    except Exception as e:
        print(f"Error moving file {src} to {dst}: {e}")

def main():
    parser = argparse.ArgumentParser(description="Move duplicates identified by Czkawka to a completed folder.")
    parser.add_argument("--results", required=True, help="Path to results.json from czkawka.")
    parser.add_argument("--completed", required=True, help="Path to completed folder.")
    args = parser.parse_args()

    if not os.path.exists(args.results):
        print(f"Results file not found: {args.results}")
        sys.exit(0)

    if not os.path.exists(args.completed):
        os.makedirs(args.completed, exist_ok=True)

    try:
        with open(args.results, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error reading results JSON: {e}")
        sys.exit(1)

    if not isinstance(data, list):
        print("Invalid JSON structure: Expected a list of duplicate groups.")
        sys.exit(1)

    print(f"Processing {len(data)} groups of duplicates...")
    for group in data:
        if not isinstance(group, list) or len(group) < 2:
            continue
        
        # Sort group by modified_date ascending (keeps oldest)
        group.sort(key=lambda x: x.get("modified_date", 0))
        
        # Keep the oldest file, move the rest
        oldest_file = group[0]["path"]
        print(f"Keeping oldest file: {oldest_file}")
        
        for file_info in group[1:]:
            dup_path = file_info["path"]
            move_file_safe(dup_path, args.completed)

if __name__ == "__main__":
    main()
