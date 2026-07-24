"""MilkLab Sales Logger (S2).

Usage:
    python sales_logger.py --menu "นมหมีฮอกไกโด" --qty 2 --price 65

Reads GOOGLE_SHEETS_CREDENTIALS and TELEGRAM_BOT_TOKEN (or LINE_CHANNEL_TOKEN) from env.
Appends row [timestamp, menu, qty, price, total] to a Google Sheet,
then sends a notification via Telegram or LINE bot.
"""

import argparse
import json
import os
import sys
from datetime import datetime

import requests


def append_to_sheet(menu: str, qty: int, price: float) -> dict:
    import gspread
    from google.oauth2.service_account import Credentials

    creds_env = os.environ.get("GOOGLE_SHEETS_CREDENTIALS")
    if not creds_env:
        raise RuntimeError(
            "ไม่พบ GOOGLE_SHEETS_CREDENTIALS ใน environment variables"
        )

    sheet_id = os.environ.get("GOOGLE_SHEET_ID")
    sheet_name = os.environ.get("GOOGLE_SHEET_NAME")
    if not sheet_id and not sheet_name:
        raise RuntimeError(
            "ต้องระบุ GOOGLE_SHEET_ID หรือ GOOGLE_SHEET_NAME ใน environment variables"
        )

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.readonly",
    ]

    try:
        if os.path.isfile(creds_env):
            # ถ้าเป็น Path ของไฟล์ (เช่น credentials.json)
            creds = Credentials.from_service_account_file(
                creds_env, scopes=scopes)
        else:
            # ถ้าเป็น เนื้อหา JSON ทั้งก้อน ( Single-line JSON String จาก Secrets )
            creds_dict = json.loads(creds_env)
            creds = Credentials.from_service_account_info(
                creds_dict, scopes=scopes)

        client = gspread.authorize(creds)
    except (ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"ไฟล์/ข้อมูล credentials ไม่ถูกต้อง: {exc}") from exc
    except Exception as exc:
        raise RuntimeError(f"ยืนยันตัวตนกับ Google ล้มเหลว: {exc}") from exc

    try:
        if sheet_id:
            spreadsheet = client.open_by_key(sheet_id)
        else:
            spreadsheet = client.open(sheet_name)
        worksheet = spreadsheet.sheet1
    except gspread.exceptions.SpreadsheetNotFound as exc:
        raise RuntimeError(
            "ไม่พบ Sheet หรือ service account ยังไม่ถูก share สิทธิ์เข้าถึง "
            "(เช็คว่า share Sheet ให้กับ client_email ในไฟล์ credentials แล้วหรือยัง)"
        ) from exc
    except gspread.exceptions.APIError as exc:
        raise RuntimeError(f"Google Sheets API error: {exc}") from exc

    timestamp = datetime.now().isoformat(timespec="seconds")
    total = round(qty * price, 2)
    row = [timestamp, menu, qty, price, total]

    try:
        worksheet.append_row(row, value_input_option="USER_ENTERED")
    except gspread.exceptions.APIError as exc:
        raise RuntimeError(f"append_row ไปยัง Sheet ล้มเหลว: {exc}") from exc

    return {
        "timestamp": timestamp,
        "menu": menu,
        "qty": qty,
        "price": price,
        "total": total,
    }


def send_notification(message: str) -> str:
    """ส่ง message ไปยัง Telegram bot (ใช้ TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID)
    หรือ LINE bot (ใช้ LINE_CHANNEL_TOKEN + LINE_USER_ID/LINE_TO) เลือกตัวใดตัวหนึ่ง
    โดยจะลอง Telegram ก่อน ถ้าไม่มี credentials ค่อยลอง LINE

    Returns: provider name ที่ใช้ ("telegram" หรือ "line")
    Raises RuntimeError ถ้า no credentials หรือส่งไม่สำเร็จ
    """
    telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    line_token = os.environ.get("LINE_CHANNEL_TOKEN")
    line_to = os.environ.get("LINE_USER_ID") or os.environ.get("LINE_TO")

    if telegram_token and telegram_chat_id:
        url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
        try:
            resp = requests.post(
                url,
                json={"chat_id": telegram_chat_id, "text": message},
                timeout=10,
            )
        except requests.RequestException as exc:
            raise RuntimeError(
                f"เชื่อมต่อ Telegram API ไม่ได้: {exc}") from exc

        if resp.status_code != 200:
            raise RuntimeError(
                f"Telegram API ตอบ error (status {resp.status_code}): {resp.text}"
            )
        return "telegram"

    if line_token and line_to:
        url = "https://api.line.me/v2/bot/message/push"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {line_token}",
        }
        payload = {"to": line_to, "messages": [
            {"type": "text", "text": message}]}
        try:
            resp = requests.post(url, headers=headers,
                                 json=payload, timeout=10)
        except requests.RequestException as exc:
            raise RuntimeError(f"เชื่อมต่อ LINE API ไม่ได้: {exc}") from exc

        if resp.status_code != 200:
            raise RuntimeError(
                f"LINE API ตอบ error (status {resp.status_code}): {resp.text}"
            )
        return "line"

    raise RuntimeError(
        "ไม่พบ credentials สำหรับ notification: ต้องตั้ง "
        "TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID หรือ "
        "LINE_CHANNEL_TOKEN + LINE_USER_ID ใน environment variables อย่างใดอย่างหนึ่ง"
    )

def query_sales(target_date: str) -> str:
    """อ่านข้อมูลใน Google Sheet แล้วรวมยอดขายของ target_date (รูปแบบ YYYY-MM-DD)"""
    import gspread
    from google.oauth2.service_account import Credentials

    creds_env = os.environ.get("GOOGLE_SHEETS_CREDENTIALS")
    if not creds_env:
        raise RuntimeError("ไม่พบ GOOGLE_SHEETS_CREDENTIALS ใน environment variables")

    sheet_id = os.environ.get("GOOGLE_SHEET_ID")
    sheet_name = os.environ.get("GOOGLE_SHEET_NAME")
    if not sheet_id and not sheet_name:
        raise RuntimeError("ต้องระบุ GOOGLE_SHEET_ID หรือ GOOGLE_SHEET_NAME ใน environment variables")

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.readonly",
    ]

    if os.path.isfile(creds_env):
        creds = Credentials.from_service_account_file(creds_env, scopes=scopes)
    else:
        creds_dict = json.loads(creds_env)
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)

    client = gspread.authorize(creds)

    if sheet_id:
        spreadsheet = client.open_by_key(sheet_id)
    else:
        spreadsheet = client.open(sheet_name)

    print(f"\n[DEBUG] 📂 กำลังอ่านไฟล์ชื่อ: {spreadsheet.title}")
    print(f"[DEBUG] 🔗 URL ของไฟล์: {spreadsheet.url}\n")
    
    worksheet = spreadsheet.sheet1
    records = worksheet.get_all_values()

    total_sales = 0.0
    count = 0

    # ข้าม Header (แถวที่ 1) อ่านตั้งแต่แถวที่ 2 เป็นต้นไป
    for row in records[1:]:
        if len(row) >= 5:
            timestamp = row[0] # คอลัมน์ที่ 1: Timestamp
            total_val = row[4] # คอลัมน์ที่ 5 (Index 4): Total
            
            # เช็คว่า timestamp มีวันที่ target_date อยู่หรือไม่ (เช่น "2026-07-24")
            if target_date in timestamp:
                try:
                    total_sales += float(total_val)
                    count += 1
                except ValueError:
                    continue

    records = worksheet.get_all_values()

    print("--- ข้อมูลทั้งหมดที่อ่านได้จาก Sheet ---")
    for i, row in enumerate(records):
        print(f"Row {i+1}: {row}")
    print("----------------------------------")

    return f"ยอดขายรวมของวันที่ {target_date} คือ {total_sales:,.0f} บาท ({count} รายการ)"


def main() -> int:
    parser = argparse.ArgumentParser(description="MilkLab Sales Logger")
    parser.add_argument("--menu", required=True, help="ชื่อเมนู")
    parser.add_argument("--qty", type=int, required=True, help="จำนวนขวด")
    parser.add_argument("--price", type=float,
                        required=True, help="ราคาต่อขวด")
    args = parser.parse_args()

    try:
        row = append_to_sheet(args.menu, args.qty, args.price)
        total = row["total"]
    except Exception as exc:
        print(f"[ERROR] บันทึก Sheet ล้มเหลว: {exc}", file=sys.stderr)
        print(
            "[HINT] ตรวจ GOOGLE_SHEETS_CREDENTIALS และ share Sheet กับ service account email",
            file=sys.stderr,
        )
        return 1

    try:
        provider = send_notification(
            f"บันทึก {args.menu} x{args.qty} = {total} บาท")
    except Exception as exc:
        print(
            f"[WARN] บันทึก Sheet สำเร็จแต่ส่งแจ้งเตือนล้มเหลว: {exc}", file=sys.stderr)
        return 0

    print(f"[OK] บันทึกและแจ้งเตือนผ่าน {provider} เรียบร้อย ยอด {total} บาท")
    return 0


if __name__ == "__main__":
    sys.exit(main())
