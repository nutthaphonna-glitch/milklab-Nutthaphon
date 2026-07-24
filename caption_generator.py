"""MilkLab Caption Generator (S1).

Usage:
    python caption_generator.py                     # stdin mode
    python caption_generator.py --menu "นมหมีฮอกไกโด"  # CLI mode

Reads GOOGLE_API_KEY from env. Generates a Thai caption for a milk menu item.
"""

import argparse
import json
import os
import sys
from typing import Any

from dotenv import load_dotenv
from google import genai


PROMPT_TEMPLATE = """\
คุณคือ social media manager ของร้าน MilkLab° ร้านนมสดกลางคืน

จงเขียนแคปชั่นภาษาไทย 2 ถึง 3 ประโยคโปรโมตเมนูต่อไปนี้:
{menu_details}

เงื่อนไข:
- โทนสนุก ใช้คำง่าย ใส่ emoji ได้
- ถ้ามีข้อมูลราคาและส่วนผสม ให้ใส่รายละเอียดเหล่านั้นให้ชัดเจนในแคปชั่น
- ต้องมี call-to-action ปิดท้าย เช่น สั่งเลย หรือ ทักแชท
- ห้ามใช้ em dash
"""


def _normalize_ingredients(value: Any) -> list[str]:
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


def _coerce_menu(menu: Any) -> dict[str, Any]:
    if isinstance(menu, str):
        try:
            parsed = json.loads(menu)
        except json.JSONDecodeError:
            return {"name": menu}
        return _coerce_menu(parsed)

    if isinstance(menu, dict):
        normalized: dict[str, Any] = {}
        for key, value in menu.items():
            key_lower = str(key).lower()
            if key_lower in {"name", "menu", "menu_name", "title"}:
                normalized["name"] = value
            elif key_lower in {"price", "ราคา"}:
                normalized["price"] = value
            elif key_lower in {"size", "ขนาด", "volume"}:
                normalized["size"] = value
            elif key_lower in {"ingredients", "ingredient", "ส่วนผสม", "components"}:
                normalized["ingredients"] = _normalize_ingredients(value)
            elif isinstance(value, (dict, list)):
                nested = _coerce_menu(value)
                for nested_key, nested_value in nested.items():
                    if nested_key not in normalized:
                        normalized[nested_key] = nested_value
        return normalized

    if isinstance(menu, list):
        for item in menu:
            normalized = _coerce_menu(item)
            if normalized:
                return normalized

    return {}


def build_prompt(menu: Any) -> str:
    """Build a prompt that includes menu name, price, size, and ingredients when available."""
    menu_data = _coerce_menu(menu)
    menu_name = menu_data.get("name") or (
        menu if isinstance(menu, str) else "เมนู")
    details = [f"เมนู: {menu_name}"]

    if menu_data.get("price") is not None:
        details.append(f"ราคา: {menu_data['price']} บาท")

    if menu_data.get("size"):
        details.append(f"ขนาด: {menu_data['size']}")

    if menu_data.get("ingredients"):
        ingredients = menu_data["ingredients"]
        if isinstance(ingredients, list):
            ingredient_text = ", ".join(str(item) for item in ingredients)
        else:
            ingredient_text = str(ingredients)
        details.append(f"ส่วนผสม: {ingredient_text}")

    return PROMPT_TEMPLATE.format(menu_details="\n".join(details))


def generate_caption(menu: Any, api_key: str | None = None, max_attempts: int = 3) -> str:
    """Generate a Thai caption for the given milk menu item, retrying if it is too long."""
    key = api_key or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError("GOOGLE_API_KEY not set in env or argument")

    client = genai.Client(api_key=key)
    last_text = ""

    for _ in range(max_attempts):
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=build_prompt(menu),
        )
        text = (response.text or "").strip()
        if len(text) <= 280:
            return text
        last_text = text

    return last_text


def main() -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Generate Thai captions for MilkLab menu items"
    )
    parser.add_argument(
        "--menu", "-m",
        help="Menu name to promote",
    )
    parser.add_argument(
        "--n",
        type=int,
        default=1,
        help="Number of captions to generate (default: 1)",
    )

    args = parser.parse_args()

    # Get menu from CLI argument or stdin
    if args.menu:
        menu = args.menu.strip()
    else:
        menu = input("เมนูที่จะโปรโมต: ").strip()

    if not menu:
        print("กรุณาใส่ชื่อเมนู", file=sys.stderr)
        return 1

    for i in range(args.n):
        caption = generate_caption(menu)

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
