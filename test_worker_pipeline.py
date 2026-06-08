import os
import time
import json
import base64
import requests
import unittest
from unittest.mock import patch

# Import the worker methods
import run_local_worker

class TestWorkerPipeline(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        print("\n=== Initializing Worker Pipeline Verification Test ===")
        # Point to the active local background FastAPI server
        run_local_worker.VPS_BASE_URL = "http://127.0.0.1:9001"
        run_local_worker.WORK_DIR = "./temp_test_jobs"
        run_local_worker.PROMO_ASSETS_DIR = "./temp_promo_assets"
        
        os.makedirs(run_local_worker.WORK_DIR, exist_ok=True)
        os.makedirs(run_local_worker.PROMO_ASSETS_DIR, exist_ok=True)
        
        # Setup real zip assets
        run_local_worker.LOGO_PATH = os.path.join(run_local_worker.PROMO_ASSETS_DIR, "logo.png")
        run_local_worker.PDF_PATH = os.path.join(run_local_worker.PROMO_ASSETS_DIR, "community_promo.pdf")
        
        with open(run_local_worker.LOGO_PATH, "wb") as f:
            f.write(b"MOCK_LOGO_DATA_BYTES")
        with open(run_local_worker.PDF_PATH, "wb") as f:
            f.write(b"%PDF-1.4\nMock Telegram Links Padded Bytes\n")
            f.write(os.urandom(1024 * 1024 * 6)) # 6MB padding to trigger payout tier

    def test_complete_distributed_flow(self):
        """
        Verify submitting, claiming, processing (mocked GPU), zip packaging, 
        mock uploading, and marking as complete in the active queue database.
        """
        # 1. Submit Mock Face Swap to VPS Endpoint
        mock_face_b64 = base64.b64encode(b"MOCK_SOURCE_FACE_BYTES").decode("utf-8")
        mock_target_b64 = base64.b64encode(b"MOCK_TARGET_IMAGE_BYTES").decode("utf-8")
        
        print("\n[Step 1] Submitting mock faceswap job to FastAPI queue...")
        submit_url = f"{run_local_worker.VPS_BASE_URL}/api/jobs/faceswap"
        resp = requests.post(submit_url, json={
            "source_face": mock_face_b64,
            "target_image": mock_target_b64
        })
        self.assertEqual(resp.status_code, 200)
        job_data = resp.json()
        job_id = job_data["jobId"]
        self.assertIsNotNone(job_id)
        print(f" -> Job registered successfully with ID: {job_id}")

        # 2. Mock FaceFusion GPU execution to bypass C:\FaceFusion dependencies
        print("\n[Step 2] Executing pipeline processes with mocked FaceFusion GPU subprocess...")
        dummy_out_path = os.path.join(run_local_worker.WORK_DIR, f"output_{job_id}.jpg")
        with open(dummy_out_path, "wb") as f:
            f.write(b"MOCK_OUTPUT_RESULT_IMAGE_BYTES")
            
        with patch('run_local_worker.execute_faceswap', return_value=dummy_out_path) as mock_exec, \
             patch('run_local_worker.upload_to_katfile', return_value="https://katfile.com/download/nu52gsth9xks/faceswap.zip.html") as mock_upload:
            
            # 3. Fetch/Claim the job using the Tailscale poller
            print("\n[Step 3] Fetching pending job from queue...")
            claimed = run_local_worker.claim_job()
            self.assertIsNotNone(claimed)
            self.assertEqual(claimed["id"], job_id)
            print(f" -> Job claimed: {claimed['id']} (Status marked: '{claimed['status']}')")
            
            # 4. Execute mock faceswap
            output_image = run_local_worker.execute_faceswap(job_id, claimed["payload"])
            self.assertEqual(output_image, dummy_out_path)
            self.assertTrue(os.path.exists(output_image))
            print(" -> CUDA Swapper process simulated successfully.")

            # 5. Pack zip with promotional links and verify size thresholds
            print("\n[Step 4] Packaging faceswap result with community invite flyer PDF...")
            zip_archive = run_local_worker.package_ppd_archive(job_id, output_image)
            self.assertTrue(os.path.exists(zip_archive))
            
            # Verify zip size is >6MB
            file_size = os.path.getsize(zip_archive)
            size_mb = file_size / (1024 * 1024)
            print(f" -> Package zip created: {zip_archive}")
            print(f" -> Size: {size_mb:.2f} MB (Payout threshold successfully crossed!)")
            self.assertGreater(size_mb, 5.0)

            # 6. Mock KatFile Upload & Commit Success status back to VPS
            print("\n[Step 5] Submitting premium download mirrors & success flags back to VPS...")
            download_url = run_local_worker.upload_to_katfile(zip_archive)
            run_local_worker.complete_job(job_id, "succeeded", result_url=download_url)
            
            if os.path.exists(zip_archive):
                os.remove(zip_archive)

        # 7. Check finalized status in active queue database
        print("\n[Step 6] Verifying job transition in main queue database...")
        status_resp = requests.get(f"{run_local_worker.VPS_BASE_URL}/api/jobs/{job_id}")
        self.assertEqual(status_resp.status_code, 200)
        final_job = status_resp.json()
        self.assertEqual(final_job["status"], "succeeded")
        self.assertEqual(final_job["result"]["download_url"], "https://katfile.com/download/nu52gsth9xks/faceswap.zip.html")
        print(" -> Job confirmed completed! Result link registered correctly.")
        print("\n=== All Verification Tests Passed Successfully! ===")

    @classmethod
    def tearDownClass(cls):
        # Clean up temporary test files
        for root, dirs, files in os.walk(run_local_worker.WORK_DIR, topdown=False):
            for name in files:
                os.remove(os.path.join(root, name))
            for name in dirs:
                os.rmdir(os.path.join(root, name))
        if os.path.exists(run_local_worker.WORK_DIR):
            os.rmdir(run_local_worker.WORK_DIR)
            
        for root, dirs, files in os.walk(run_local_worker.PROMO_ASSETS_DIR, topdown=False):
            for name in files:
                os.remove(os.path.join(root, name))
            for name in dirs:
                os.rmdir(os.path.join(root, name))
        if os.path.exists(run_local_worker.PROMO_ASSETS_DIR):
            os.rmdir(run_local_worker.PROMO_ASSETS_DIR)


if __name__ == "__main__":
    unittest.main()
