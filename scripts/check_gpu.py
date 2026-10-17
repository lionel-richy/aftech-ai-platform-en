import subprocess

try:
    import torch

    print(f"torch version: {torch.__version__}")
    print(f"CUDA available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"Device: {torch.cuda.get_device_name(0)}")
except ImportError:
    print("torch not installed on this runtime; falling back to nvidia-smi")
    subprocess.run(["nvidia-smi"], check=False)
