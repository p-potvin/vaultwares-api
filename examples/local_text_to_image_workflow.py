"""
Full local text-to-image workflow using your models and Python libraries.
Paths point to D:/comfyui/resources/comfyui/models/{type}/{name}

Required pip installs:
  pip install torch diffusers transformers pillow opencv-python realesrgan codeformer segment-anything

Note: You must have the correct model files in the specified directories. Some steps (e.g., ADetailer) are skipped if no direct Python module is available.
"""
import os
from datetime import datetime
from PIL import Image
import torch
from diffusers import StableDiffusionPipeline, StableDiffusionControlNetPipeline, ControlNetModel, StableDiffusionImg2ImgPipeline
from diffusers.utils import load_image
from realesrgan import RealESRGAN

MODEL_ROOT = r"D:/comfyui/resources/comfyui/models"
CHECKPOINT = os.path.join(MODEL_ROOT, "checkpoints", "illustrious_v6NS.safetensors")
VAE = os.path.join(MODEL_ROOT, "vae", "sdxl_vae.safetensors")
LORA = os.path.join(MODEL_ROOT, "loras", "add-detail-xl.safetensors")
CONTROLNET_INPAINT = os.path.join(MODEL_ROOT, "controlnet", "control_v11p_sd15_inpaint.pth")
CONTROLNET_OPENPOSE = os.path.join(MODEL_ROOT, "controlnet", "control_v11p_sd15_openpose.pth")
UPSCALER = os.path.join(MODEL_ROOT, "upscale_models", "RealESRGAN_x4plus.pth")
FACERESTORE = os.path.join(MODEL_ROOT, "facerestore_models", "codeformer.pth")
SAM = os.path.join(MODEL_ROOT, "sams", "sam_vit_b_01ec64.pth")

RUN_ID = datetime.now().strftime("%Y%m%d_%H%M%S")
OUTDIR = os.path.join("outputs", f"workflow_local_{RUN_ID}")
os.makedirs(OUTDIR, exist_ok=True)

def save_and_log(step, img, meta=None):
    img_path = os.path.join(OUTDIR, f"{step}.png")
    img.save(img_path)
    if meta:
        with open(os.path.join(OUTDIR, f"{step}_meta.txt"), "w") as f:
            f.write(str(meta))
    print(f"[{step}] Saved: {img_path}")
    return img_path

# 1. Text-to-Image Generation (SDXL/Stable Diffusion)
def text_to_image(prompt):
    pipe = StableDiffusionPipeline.from_single_file(CHECKPOINT, torch_dtype=torch.float16).to("cuda")
    pipe.vae = pipe.vae.from_pretrained(VAE, torch_dtype=torch.float16)
    # LoRA support: pipe.load_lora_weights(LORA)  # Uncomment if using diffusers>=0.20
    img = pipe(prompt, num_inference_steps=30).images[0]
    return save_and_log("text2img", img, {"prompt": prompt})

# 2. ControlNet (bbox/segment/object removal)
def apply_controlnet(img_path, mode):
    img = load_image(img_path)
    if mode == "bbox":
        controlnet = ControlNetModel.from_pretrained(CONTROLNET_OPENPOSE, torch_dtype=torch.float16)
    elif mode == "segment":
        controlnet = ControlNetModel.from_pretrained(CONTROLNET_OPENPOSE, torch_dtype=torch.float16)
    else:
        controlnet = ControlNetModel.from_pretrained(CONTROLNET_INPAINT, torch_dtype=torch.float16)
    pipe = StableDiffusionControlNetPipeline.from_pretrained(CHECKPOINT, controlnet=controlnet, torch_dtype=torch.float16).to("cuda")
    out = pipe(image=img, prompt="", num_inference_steps=20).images[0]
    return save_and_log(f"controlnet_{mode}", out)

# 3. Upscale (RealESRGAN)
def upscale(img_path):
    img = Image.open(img_path).convert("RGB")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = RealESRGAN(device, scale=4)
    model.load_weights(UPSCALER)
    out = model.predict(img)
    return save_and_log("upscale", out)

# 4. Face Restore (CodeFormer)
def face_restore(img_path):
    # Placeholder: Save input as output
    img = Image.open(img_path)
    return save_and_log("facerestore", img)

# 5. Segmentation (SAM)
def segment(img_path):
    # Placeholder: Save input as output
    img = Image.open(img_path)
    return save_and_log("segment", img)

# --- Workflow ---
prompt = "A futuristic cityscape at sunset with flying cars"
img_path = text_to_image(prompt)
img_bbox = apply_controlnet(img_path, "bbox")
img_segment = apply_controlnet(img_path, "segment")
img_objrem = apply_controlnet(img_path, "object_removal")
img_upscaled = upscale(img_objrem)
img_facerestore = face_restore(img_upscaled)
img_segmented = segment(img_facerestore)

print(f"Workflow complete. All outputs saved in: {OUTDIR}")
