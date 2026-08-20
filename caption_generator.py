"""Smart Farm Caption Generator (S1).

Usage:
    python caption_generator.py                     # stdin mode
    python caption_generator.py --product "ESP32"   # CLI mode

Reads GOOGLE_API_KEY from env. Generates a Thai caption for an IoT/Smart Farm product.
"""

import argparse
import json
import os
import sys
from typing import Any

from dotenv import load_dotenv
from google import genai


PROMPT_TEMPLATE = """\
คุณคือ social media manager ของร้าน 'Smart Farm & IoT Supply' ร้านขายอุปกรณ์อิเล็กทรอนิกส์และเซ็นเซอร์สำหรับการเกษตร

จงเขียนแคปชั่นภาษาไทย 2 ถึง 3 ประโยคโปรโมตสินค้าต่อไปนี้:
{product_details}

เงื่อนไข:
- โทนดูเป็นผู้เชี่ยวชาญ กระตือรือร้น เข้าใจง่าย ใส่ emoji ที่เข้ากับเทคโนโลยีและการเกษตร (เช่น ⚙️, 🌿, 💧, 📡)
- ถ้ามีข้อมูลราคาและสเปก ให้ใส่รายละเอียดเหล่านั้นให้ชัดเจนในแคปชั่น เน้นประโยชน์การนำไปใช้งานจริง
- ต้องมี call-to-action ปิดท้าย เช่น สั่งซื้อเลย หรือ สอบถามสเปกเพิ่มเติม
- ห้ามใช้ em dash
"""


def _normalize_specs(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        normalized = []
        for item in value:
            if isinstance(item, str) and item.strip():
                normalized.append(item.strip())
            elif item is not None:
                normalized.append(str(item))
        return normalized
    if value is None:
        return []
    return [str(value)]


def _coerce_product(product: Any) -> dict[str, Any]:
    if isinstance(product, str):
        try:
            parsed = json.loads(product)
        except json.JSONDecodeError:
            return {"name": product}
        return _coerce_product(parsed)

    if isinstance(product, dict):
        normalized: dict[str, Any] = {}
        for key, value in product.items():
            key_lower = str(key).lower()
            if key_lower in {"name", "product", "product_name", "title", "สินค้า"}:
                normalized["name"] = value
            elif key_lower in {"price", "ราคา"}:
                normalized["price"] = value
            elif key_lower in {"specs", "spec", "สเปก", "คุณสมบัติ", "features", "details"}:
                normalized["specs"] = _normalize_specs(value)
            elif isinstance(value, (dict, list)):
                nested = _coerce_product(value)
                for nested_key, nested_value in nested.items():
                    if nested_key not in normalized:
                        normalized[nested_key] = nested_value
        return normalized

    if isinstance(product, list):
        for item in product:
            normalized = _coerce_product(item)
            if normalized:
                return normalized

    return {}


def build_prompt(product: Any) -> str:
    """Build a prompt that includes product name, price, and specs when available."""
    product_data = _coerce_product(product)
    product_name = product_data.get("name") or (
        product if isinstance(product, str) else "อุปกรณ์ IoT")
    details = [f"สินค้า: {product_name}"]

    if product_data.get("price") is not None:
        details.append(f"ราคา: {product_data['price']} บาท")

    if product_data.get("specs"):
        specs = product_data["specs"]
        if isinstance(specs, list):
            spec_text = ", ".join(str(item) for item in specs)
        else:
            spec_text = str(specs)
        details.append(f"สเปก/จุดเด่น: {spec_text}")

    return PROMPT_TEMPLATE.format(product_details="\n".join(details))


def generate_caption(product: Any, api_key: str | None = None, max_attempts: int = 3) -> str:
    """Generate a Thai caption for the given IoT product, retrying if it is too long."""
    key = api_key or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError("GOOGLE_API_KEY not set in env or argument")

    client = genai.Client(api_key=key)
    last_text = ""

    for _ in range(max_attempts):
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=build_prompt(product),
        )
        text = (response.text or "").strip()
        if len(text) <= 280:
            return text
        last_text = text

    return last_text


def main() -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Generate Thai captions for Smart Farm & IoT Supply products"
    )
    parser.add_argument(
        "--product", "-p",
        help="Product name to promote",
    )
    parser.add_argument(
        "--n",
        type=int,
        default=1,
        help="Number of captions to generate (default: 1)",
    )

    args = parser.parse_args()

    # Get product from CLI argument or stdin
    if args.product:
        product = args.product.strip()
    else:
        product = input("อุปกรณ์ที่จะโปรโมต: ").strip()

    if not product:
        print("กรุณาใส่ชื่ออุปกรณ์", file=sys.stderr)
        return 1

    for i in range(args.n):
        caption = generate_caption(product)

        if args.n > 1:
            print(f"\n📝 แคปชั่นที่ {i + 1}:")
        else:
            print()
        print(caption)

        if i < args.n - 1:
            print("-" * 40)

    return 0


if __name__ == "__main__":
    sys.exit(main())