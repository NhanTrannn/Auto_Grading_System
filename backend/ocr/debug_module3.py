import asyncio
import sys
from pathlib import Path

TEST_IMAGE = "test.jpg"

sys.path.insert(0, str(Path(__file__).parent))

from app.module3 import is_configured, run_ocr_single

print("LLM configured (.env LLM_API_KEY/LLM_MODEL_API/LLM_MODEL_NAME):", is_configured())

if Path(TEST_IMAGE).exists():
    image_bytes = Path(TEST_IMAGE).read_bytes()
    print(f"Dùng ảnh thật: {TEST_IMAGE}")
else:
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (800, 200), color=(255, 255, 255)).save(buf, format="PNG")
    image_bytes = buf.getvalue()
    print(f"Không thấy '{TEST_IMAGE}', dùng ảnh trắng giả để test gọi API.")

print("Đang gọi API (Pass 1 + Pass 2)...")
result = asyncio.run(run_ocr_single(image_bytes, "short_text"))
print("=== run_ocr_single() THÀNH CÔNG ===")
print(result)
