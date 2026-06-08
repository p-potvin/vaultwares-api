"""
NVIDIA NIM Cosmos API wrapper for 3D environment generation from video.
- Handles authentication (NVIDIA Developer credentials/token)
- Submits video frames to Cosmos endpoint
- Receives depth/pose/mesh results
- Designed for integration with Gradio UI
"""
import requests
import os

NIM_COSMOS_API_URL = os.environ.get("NIM_COSMOS_API_URL", "https://nim.nvidia.com/api/cosmos/v1/infer")
NIM_API_KEY = os.environ.get("NIM_API_KEY")  # User must set this in their environment

class NIMCosmosClient:
    def __init__(self, api_url=None, api_key=None):
        self.api_url = api_url or NIM_COSMOS_API_URL
        self.api_key = api_key or NIM_API_KEY
        if not self.api_key:
            raise ValueError("NIM_API_KEY environment variable must be set.")

    def infer_3d(self, frames):
        """
        frames: list of image bytes or base64-encoded images
        Returns: dict with depth, pose, mesh, etc.
        """
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {"frames": frames}
        response = requests.post(self.api_url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()
