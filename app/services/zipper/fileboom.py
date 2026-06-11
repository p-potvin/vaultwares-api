import os
import requests
import logging

logger = logging.getLogger(__name__)

CREDENTIALS_PATH = r"C:\Users\Administrator\Desktop\Prom-King\.access\fileboom.credentials.txt"

class FileboomClient:
    def __init__(self, token=None):
        self.token = token or self._load_token()

    def _load_token(self):
        if not os.path.exists(CREDENTIALS_PATH):
            raise FileNotFoundError(f"FileBoom credentials file not found at {CREDENTIALS_PATH}")
        with open(CREDENTIALS_PATH, "r", encoding="utf-8") as f:
            return f.read().strip()

    def get_upload_form_data(self):
        url = "https://fileboom.me/api/v2/getUploadFormData"
        payload = {
            "access_token": self.token
        }
        resp = requests.post(url, json=payload, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "success":
            raise ValueError(f"FileBoom API returned error for getUploadFormData: {data}")
        return data

    def upload_file(self, file_path: str) -> str:
        """
        Uploads a file to FileBoom and returns the direct download link.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Local file not found for upload: {file_path}")

        filename = os.path.basename(file_path)
        logger.info(f"FileBoom: Retrieving upload form data for {filename}...")
        form_info = self.get_upload_form_data()

        form_action = form_info["form_action"]
        file_field = form_info["file_field"]
        form_data = form_info["form_data"]

        logger.info(f"FileBoom: Uploading {filename} to {form_action}...")
        with open(file_path, "rb") as f:
            files = {
                file_field: (filename, f)
            }
            resp = requests.post(form_action, data=form_data, files=files, timeout=600) # generous timeout for large files
            resp.raise_for_status()
            res_data = resp.json()

        if res_data.get("status") != "success":
            raise ValueError(f"FileBoom upload failed: {res_data}")

        link = res_data.get("link")
        if not link:
            file_id = res_data.get("user_file_id")
            if file_id:
                link = f"https://fboom.me/file/{file_id}"
            else:
                raise ValueError(f"FileBoom upload response missing link and user_file_id: {res_data}")

        logger.info(f"FileBoom: Successfully uploaded {filename}. Link: {link}")
        return link
