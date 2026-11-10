"""Shared OpenCLIP image/text encoder with deterministic float32 inference."""
import hashlib
import random
from pathlib import Path
import numpy as np
import open_clip
import torch
from PIL import Image

MODEL_NAME = "ViT-B-32"
PRETRAINED = "laion2b_s34b_b79k"


class OpenCLIPEncoder:
    def __init__(self, model_name=MODEL_NAME, pretrained=PRETRAINED,
                 device="cpu", cache_dir=".cache/open_clip", seed=0, threads=4):
        if threads <= 0:
            raise ValueError("threads must be positive")
        random.seed(seed)
        np.random.seed(seed)
        torch.manual_seed(seed)
        torch.set_num_threads(threads)
        torch.use_deterministic_algorithms(True)
        self.device = device
        self.model_name, self.pretrained = model_name, pretrained
        self.seed = seed
        self.threads = threads
        Path(cache_dir).mkdir(parents=True, exist_ok=True)
        self.model, _, self.preprocess = open_clip.create_model_and_transforms(
            model_name, pretrained=pretrained, device=device, precision="fp32",
            cache_dir=str(cache_dir),
        )
        self.model.eval()
        self.tokenizer = open_clip.get_tokenizer(model_name)

    @staticmethod
    def _normalize(features):
        features = features.float()
        norms = features.norm(dim=-1, keepdim=True)
        if not torch.isfinite(features).all() or (norms <= 0).any():
            raise ValueError("Encoder produced invalid embeddings")
        return (features / norms).cpu().numpy().astype(np.float32)

    @torch.inference_mode()
    def encode_images(self, images: list[Image.Image]) -> np.ndarray:
        batch = torch.stack([self.preprocess(im.convert("RGB")) for im in images])
        return self._normalize(self.model.encode_image(batch.to(self.device)))

    @torch.inference_mode()
    def encode_text(self, query: str) -> np.ndarray:
        if not query.strip():
            raise ValueError("Query cannot be empty")
        tokens = self.tokenizer([query]).to(self.device)
        return self._normalize(self.model.encode_text(tokens))[0]

    def metadata(self) -> dict:
        # Hash actual tensors: a changed remote checkpoint must not silently
        # mismatch the index. Cache the result since it reads all weights.
        if not hasattr(self, "_fingerprint"):
            digest = hashlib.sha256()
            for name, tensor in self.model.state_dict().items():
                array = tensor.detach().cpu().contiguous().numpy()
                digest.update(f"{name}:{array.dtype}:{array.shape}".encode())
                digest.update(memoryview(array).cast("B"))
            self._fingerprint = digest.hexdigest()
        return {"model": self.model_name, "pretrained": self.pretrained,
                "weights_sha256": self._fingerprint, "precision": "fp32",
                "device": self.device, "seed": self.seed, "threads": self.threads}
