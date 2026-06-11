#!/usr/bin/env python
import sys

file_path = 'C:\\Users\\Administrator\\Desktop\\Github Repos\\vaultwares-api\\api_server.py'

with open(file_path, 'r') as f:
    content = f.read()

# Update DownloadPayload
old = "class DownloadPayload(BaseModel):\n    url: str\n    links: List[str]\n    batch_size: Optional[int] = 100"

new = "class DownloadPayload(BaseModel):\n    url: str\n    links: List[str]\n    batch_size: Optional[int] = 5\n    upscale_enabled: Optional[bool] = False\n    upscale_model: Optional[str] = \"4xNomos8k_atd\""

if old in content:
    print("Found pattern, replacing...")
    content = content.replace(old, new)
    with open(file_path, 'w') as f:
        f.write(content)
    print("DownloadPayload updated")
else:
    print("Pattern not found")
    # Try to find similar
    if 'class DownloadPayload' in content:
        print("Found class DownloadPayload")
        idx = content.find('class DownloadPayload')
        print(repr(content[idx:idx+200]))
