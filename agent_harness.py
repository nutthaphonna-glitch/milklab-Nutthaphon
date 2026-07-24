"""MilkLab Agent Harness (S2).

Usage:
    python agent_harness.py --cmd "บันทึกขายนมหมี 2 ขวด ขวดละ 65"

รับคำสั่งภาษาไทย ส่งให้ Gemini พร้อม tool schema parse response เป็น tool call
เรียก tool จริง print trace log
"""

import argparse
import json
import os
import sys

from dotenv import load_dotenv
from google import genai
from google.genai import types

# นำเข้าฟังก์ชันบันทึกและส่งแจ้งเตือนจาก sales_logger.py
from sales_logger import append_to_sheet, send_notification


TOOL_SCHEMA = [
    {
        "name": "log_sale",
        "description": "บันทึกการขายลง Google Sheets และส่ง notification",
        "parameters": {
            "type": "object",
            "properties": {
                "menu": {"type": "string", "description": "ชื่อเมนู"},
                "qty": {"type": "integer", "description": "จำนวนที่ขาย"},
                "price": {"type": "number", "description": "ราคาต่อหน่วย"},
            },
            "required": ["menu", "qty", "price"],
        },
    },
    {
        "name": "query_sales",
        "description": "ดูยอดขายของวันที่ระบุ",
        "parameters": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "วันที่ format YYYY-MM-DD"},
            },
            "required": ["date"],
        },
    },
    {
        "name": "send_alert",
        "description": "ส่ง message แจ้งเตือนผ่าน Bot",
        "parameters": {
            "type": "object",
            "properties": {
                "message": {"type": "string"},
            },
            "required": ["message"],
        },
    },
]


def parse_command(cmd: str, api_key: str | None = None) -> dict:
    """TODO 1: ส่ง cmd ไป Gemini พร้อม TOOL_SCHEMA ขอให้ตอบเป็น JSON {tool, args}"""
    key = api_key or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError("ไม่พบ GOOGLE_API_KEY ใน environment variables")

    client = genai.Client(api_key=key)

    system_prompt = f"""คุณคือ AI Agent ผู้ช่วยจัดการระบบร้านค้า
ให้วิเคราะห์คำสั่งของผู้ใช้ แล้วเลือก Tool จาก รายการ TOOL_SCHEMA ด้านล่างให้เหมาะสม:
{json.dumps(TOOL_SCHEMA, ensure_ascii=False, indent=2)}

คำตอบของคุณต้องส่งกลับมาเป็น JSON Object ตัวเดียวเท่านั้น ในฟอร์แมต:
{{"tool": "<ชื่อ_tool>", "args": {{<arguments_ตาม_schema>}}}}

ข้อบังคับ:
- ห้ามมีข้อความอื่นนอกเหนือจาก JSON (ไม่ต้องใส่ markdown ```json)
- กำหนด Type ของ arguments ให้ถูกต้องตาม Schema
"""

    try:
        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=cmd,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.0,
                response_mime_type="application/json",
            ),
        )

        res_text = response.text.strip()
        data = json.loads(res_text)

        if "tool" not in data or "args" not in data:
            raise ValueError(
                "คีย์ใน JSON Response ไม่ครบถ้วน (ต้องมี 'tool' และ 'args')")

        return data

    except Exception as exc:
        raise RuntimeError(
            f"ไม่สามารถ parse คำสั่งจาก Gemini ได้: {exc}") from exc


def dispatch_tool(tool_call: dict) -> str:
    """TODO 2: เรียก tool ตาม tool_call["tool"] ด้วย args จริง"""
    tool_name = tool_call.get("tool")
    args = tool_call.get("args", {})

    if tool_name == "log_sale":
        menu = str(args.get("menu"))
        qty = int(args.get("qty", 1))
        price = float(args.get("price", 0.0))

        # 1. บันทึกข้อมูลลง Google Sheets
        sheet_res = append_to_sheet(menu, qty, price)
        timestamp = sheet_res["timestamp"]
        total = sheet_res["total"]

        # 2. ส่ง Notification แจ้งเตือนเข้า Bot
        try:
            send_notification(f"บันทึกขาย {menu} x{qty} = {total} บาท")
        except Exception:
            pass  # ละเว้นหากแจ้งเตือนล้มเหลว เพื่อไม่ให้ระบบหลักพัง

        return f"OK: row appended at {timestamp}"

    elif tool_name == "query_sales":
        date = str(args.get("date"))
        # Mock Data สำหรับการสอบถามยอดขาย
        return f"OK: ยอดขายรวมของวันที่ {date} คือ 1,350 บาท (2 รายการ)"

    elif tool_name == "send_alert":
        msg = str(args.get("message"))
        provider = send_notification(msg)
        return f"OK: message sent via {provider}"

    else:
        raise ValueError(f"ไม่พบ Tool ชื่อ: {tool_name}")


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--cmd", required=True, help="คำสั่งภาษาไทย")
    args = parser.parse_args()

    # TODO 3: Print Trace Log ตามฟอร์แมตของ Session 2
    print(f"| [USER] {args.cmd}")

    try:
        tool_call = parse_command(args.cmd)
        args_json = json.dumps(tool_call["args"], ensure_ascii=False)
        print(f"| [LLM]  tool={tool_call['tool']} args={args_json}")

        result_msg = dispatch_tool(tool_call)
        print(f"| [TOOL] {tool_call['tool']} {result_msg}")

        # ปรับการสรุปข้อความให้ผู้ใช้อ่านง่าย
        if tool_call["tool"] == "log_sale":
            total = int(tool_call["args"]["qty"]) * \
                float(tool_call["args"]["price"])
            print(f"| [USER] ← บันทึกแล้ว ยอดรวม {total:g} บาท")
        else:
            print(f"| [USER] ← {result_msg}")

    except Exception as exc:
        print(f"[ERROR] การทำงานล้มเหลว: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
