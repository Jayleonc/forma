import torch


def get_best_device() -> str:
    """Selects the best available device.

    Returns:
        The device string ("cuda", "mps", or "cpu").
    """
    if torch.cuda.is_available():
        return "cuda"
    # Check for Apple Silicon (MPS)
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


DEVICE = get_best_device()
