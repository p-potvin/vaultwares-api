import os
import torch
import numpy as np
from PIL import Image
from rembg import new_session, remove

class DiffusionEditor:
    _instance = None
    _models = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DiffusionEditor, cls).__new__(cls)
            cls.model_root = r"D:\comfyui\resources\comfyui\models"
        return cls._instance

    def get_bg_session(self, model_name="birefnet"):
        """
        Loads and caches the background removal session.
        BirefNet is significantly more accurate for high-res latent masking.
        """
        if model_name not in self._models:
            # Set environment variable to force rembg to look in your local path
            os.environ["U2NET_HOME"] = os.path.join(self.model_root, "u2net")
            self._models[model_name] = new_session(model_name)
        return self._models[model_name]

    def remove_background(self, input_path: str, output_path: str):
        """
        Implements the background removal pipeline.
        """
        session = self.get_bg_session(model_name="birefnet")
        
        with open(input_path, 'rb') as i:
            input_data = i.read()
            # rembg handles the alpha channel generation internally
            result = remove(input_data, session=session)
            
        with open(output_path, 'wb') as o:
            o.write(result)
        
        return Image.open(output_path)

    def generate_latent_mask(self, image: Image.Image):
        """
        Converts the alpha channel of a processed image into a 
        normalized torch tensor for latent diffusion inpainting/editing.
        """
        if image.mode != 'RGBA':
            return None
        
        alpha = np.array(image.split()[-1])
        mask = torch.from_numpy(alpha).float() / 255.0
        return mask

# Usage
if __name__ == "__main__":
    pipeline = DiffusionEditor()
    
    # Process image
    
    # Dummy paths for usage demonstration
    input_image_path = "input.jpg"
    output_image_path = "output_rgba.png"
    
    if os.path.exists(input_image_path):
        img_no_bg = pipeline.remove_background(
            input_path=input_image_path, 
            output_path=output_image_path
        )
        
        # Ready for VAE encoding into Latent Space
        mask_tensor = pipeline.generate_latent_mask(img_no_bg)
        if mask_tensor is not None:
            print(f"Mask tensor shape: {mask_tensor.shape} - Ready for Latent Diffusion.")
    else:
        print(f"Provide {input_image_path} to run the background removal.")
