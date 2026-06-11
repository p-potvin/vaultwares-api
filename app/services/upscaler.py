"""
Neural image upscaler using spandrel + torch.

Loads any super-resolution .safetensors model (e.g. 4xNomos8k_atd)
via spandrel's universal model loader.  Uses tiled inference to keep
VRAM usage bounded even on large images.
"""

import io
import logging
import os
import time
from pathlib import Path
from typing import Optional

import numpy as np
import torch
from PIL import Image

logger = logging.getLogger(__name__)

# Model path: navigate from app/services/ -> vaultwares-api -> parent -> python-zipper/models/
MODELS_DIR = os.path.abspath(os.path.join(
    os.path.dirname(__file__),
    '..', '..', '..',
    'python-zipper', 'models'
))

# Tile size for inference (smaller = less VRAM, slower)
DEFAULT_TILE_SIZE = 512
TILE_OVERLAP = 32


class ImageUpscaler:
    """Service for upscaling images using local super-resolution models."""

    def __init__(self):
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        self.loaded_models = {}
        self.load_times = {}
        self.inference_times = []
        self.available_models = []

        if not os.path.exists(MODELS_DIR):
            logger.warning(f'[Upscaler] Models directory not found at {MODELS_DIR}')
        else:
            logger.info(f'[Upscaler] Models directory: {MODELS_DIR}')

        self._scan_available_models()

    def _scan_available_models(self):
        """Discover all .safetensors and .pth files in the models dir."""
        self.available_models = []
        if not os.path.exists(MODELS_DIR):
            return
        try:
            for f in os.listdir(MODELS_DIR):
                if f.endswith('.safetensors') or f.endswith('.pth'):
                    model_name = f.rsplit('.', 1)[0]
                    self.available_models.append(model_name)
                    logger.info(f'[Upscaler] Found model: {model_name}')
        except Exception as e:
            logger.error(f'[Upscaler] Failed to scan models directory: {e}')

    def get_available_models(self):
        return self.available_models

    def load_model(self, model_name: str):
        """Load a model via spandrel's universal ModelLoader."""
        if model_name in self.loaded_models:
            return self.loaded_models[model_name]

        # Try .safetensors first, then .pth
        model_path = None
        for ext in ('.safetensors', '.pth'):
            candidate = Path(MODELS_DIR) / f'{model_name}{ext}'
            if candidate.exists():
                model_path = candidate
                break

        if model_path is None:
            raise FileNotFoundError(
                f'Model {model_name} not found in {MODELS_DIR}. '
                f'Available: {self.available_models}'
            )

        start_time = time.time()
        try:
            import spandrel
            logger.info(f'[Upscaler] Loading model {model_name} from {model_path}...')
            model_descriptor = spandrel.ModelLoader(device=torch.device(self.device)).load_from_file(str(model_path))
            model = model_descriptor.model
            model.eval()

            self.loaded_models[model_name] = {
                'model': model,
                'scale': model_descriptor.scale,
                'descriptor': model_descriptor,
            }
            elapsed = time.time() - start_time
            self.load_times[model_name] = elapsed
            logger.info(
                f'[Upscaler] Loaded {model_name} '
                f'(scale={model_descriptor.scale}, device={self.device}, {elapsed:.2f}s)'
            )
            return self.loaded_models[model_name]
        except Exception as e:
            logger.error(f'[Upscaler] Failed to load model {model_name}: {e}')
            raise

    def _tensor_to_pil(self, tensor: torch.Tensor) -> Image.Image:
        """Convert a CHW float tensor [0,1] to a PIL Image."""
        arr = tensor.squeeze(0).clamp(0, 1).cpu().detach().numpy()
        arr = (arr.transpose(1, 2, 0) * 255).astype(np.uint8)
        return Image.fromarray(arr)

    def _pil_to_tensor(self, img: Image.Image) -> torch.Tensor:
        """Convert a PIL Image to a NCHW float tensor [0,1]."""
        arr = np.array(img).astype(np.float32) / 255.0
        tensor = torch.from_numpy(arr.transpose(2, 0, 1)).unsqueeze(0)
        return tensor.to(self.device)

    def _upscale_tiled(
        self,
        model: torch.nn.Module,
        img_tensor: torch.Tensor,
        scale: int,
        tile_size: int = DEFAULT_TILE_SIZE,
        overlap: int = TILE_OVERLAP,
    ) -> torch.Tensor:
        """Run tiled inference to avoid VRAM exhaustion on large images."""
        _, c, h, w = img_tensor.shape
        out_h, out_w = h * scale, w * scale
        output = torch.zeros((1, c, out_h, out_w), device=img_tensor.device)
        weight_map = torch.zeros((1, 1, out_h, out_w), device=img_tensor.device)

        step = tile_size - overlap

        for y in range(0, h, step):
            for x in range(0, w, step):
                # Clamp tile bounds
                y_end = min(y + tile_size, h)
                x_end = min(x + tile_size, w)
                y_start = max(0, y_end - tile_size)
                x_start = max(0, x_end - tile_size)

                tile = img_tensor[:, :, y_start:y_end, x_start:x_end]

                with torch.no_grad():
                    upscaled_tile = model(tile)

                # Output coordinates
                oy_start = y_start * scale
                ox_start = x_start * scale
                oy_end = y_end * scale
                ox_end = x_end * scale

                output[:, :, oy_start:oy_end, ox_start:ox_end] += upscaled_tile
                weight_map[:, :, oy_start:oy_end, ox_start:ox_end] += 1

        # Average overlapping regions
        output /= weight_map.clamp(min=1)
        return output

    def upscale_image(
        self,
        image_data: bytes,
        model_name: str = '4xNomos8k_atd',
        tile_size: int = DEFAULT_TILE_SIZE,
    ) -> bytes:
        """Upscale image bytes using the specified model.

        Parameters
        ----------
        image_data : bytes
            Raw image file bytes (JPEG, PNG, etc.)
        model_name : str
            Name of the model file (without extension)
        tile_size : int
            Tile size for tiled inference (smaller = less VRAM)

        Returns
        -------
        bytes
            Upscaled image as PNG bytes
        """
        start_time = time.time()

        try:
            model_info = self.load_model(model_name)
            model = model_info['model']
            scale = model_info['scale']

            img = Image.open(io.BytesIO(image_data))
            original_size = img.size

            if img.mode != 'RGB':
                img = img.convert('RGB')

            width, height = img.size
            img_tensor = self._pil_to_tensor(img)

            # Use tiled inference for images larger than tile_size
            if width > tile_size or height > tile_size:
                logger.info(
                    f'[Upscaler] Using tiled inference '
                    f'({width}x{height}, tile={tile_size})'
                )
                output_tensor = self._upscale_tiled(model, img_tensor, scale, tile_size)
            else:
                with torch.no_grad():
                    output_tensor = model(img_tensor)

            upscaled_img = self._tensor_to_pil(output_tensor)

            # Save as PNG
            output = io.BytesIO()
            upscaled_img.save(output, format='PNG', optimize=True)

            inference_time = time.time() - start_time
            self.inference_times.append(inference_time)
            if len(self.inference_times) > 100:
                self.inference_times = self.inference_times[-100:]

            logger.info(
                f'[Upscaler] Upscaled: {original_size[0]}x{original_size[1]} -> '
                f'{upscaled_img.size[0]}x{upscaled_img.size[1]} '
                f'(scale={scale}, {inference_time:.2f}s)'
            )

            return output.getvalue()
        except Exception as e:
            logger.error(f'[Upscaler] Upscaling failed: {e}', exc_info=True)
            raise

    def is_available(self) -> bool:
        """Check if upscaling is possible (CUDA + at least one model)."""
        return self.device == 'cuda' and len(self.available_models) > 0

    def get_stats(self):
        return {
            'device': self.device,
            'cuda_available': torch.cuda.is_available(),
            'loaded_models': list(self.loaded_models.keys()),
            'available_models': self.available_models,
            'load_times': self.load_times,
            'avg_inference_time': (
                sum(self.inference_times) / len(self.inference_times)
                if self.inference_times else 0
            ),
            'total_inferences': len(self.inference_times),
        }


# Singleton — avoid reloading the ~80MB model on every request
_singleton: Optional[ImageUpscaler] = None


def get_upscaler() -> ImageUpscaler:
    """Return the global ImageUpscaler singleton."""
    global _singleton
    if _singleton is None:
        _singleton = ImageUpscaler()
    return _singleton
