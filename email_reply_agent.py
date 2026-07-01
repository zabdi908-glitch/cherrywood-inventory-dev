import os
import re
import json
import smtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


def find_matching_parts(get_db_func, search_text, limit=10):
    """
    Reuses the same keyword-matching approach as the chat widget to find
    relevant parts for a given enquiry's vehicle/part description.
    """
    stopwords = {
        'the', 'and', 'for', 'with', 'have', 'has', 'you', 'your', 'are',
        'can', 'need', 'looking', 'price', 'cost', 'much', 'how', 'what',
        'this', 'that', 'got', 'any', 'please', 'do', 'does', 'a', 'an', 'of', 'on', 'in'
    }
    words = re.findall(r'[a-zA-Z0-9]+', (search_text or '').lower())
    keywords = []
    for w in words:
        if len(w) <= 1 or w in stopwords:
            continue
        singular = w[:-1] if len(w) > 3 and w.endswith('s') and not w.endswith('ss') else w
        keywords.append(singular)
        if singular != w:
            keywords.append(w)

    if not keywords:
        return []

    try:
        db = get_db_func()
        like_clauses = []
        params = []
        for kw in keywords[:8]:
            term = f'%{kw}%'
            like_clauses.append(
                "(part_name LIKE ? OR make LIKE ? OR model LIKE ? OR category LIKE ? OR oem_number LIKE ? OR engine_code LIKE ?)"
            )
            params.extend([term, term, term, term, term, term])
        where_sql = " OR ".join(like_clauses)
        sql = f"""SELECT part_name, make, model, category, price, stock_status, oem_number
                  FROM parts
                  WHERE stock_status = 'Available' AND ({where_sql})
                  LIMIT ?"""
        params.append(limit)
        rows = db.execute(sql, params).fetchall()
        db.close()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"❌ [Email Reply] Inventory lookup error: {e}", flush=True)
        return []


def generate_email_reply(customer_data, matched_parts, api_key):
    """
    Uses OpenAI to draft a reply email. Strictly instructed to only reference
    parts actually found in matched_parts — never invent prices or stock.
    """
    if matched_parts:
        parts_list = "\n".join([
            f"- {p['part_name']} | {p['make']} {p['model']} | £{p['price']:.2f} | OEM: {p['oem_number'] or 'N/A'} | Status: {p['stock_status']}"
            for p in matched_parts
        ])
        inventory_context = f"Matching parts found in stock:\n{parts_list}"
    else:
        inventory_context = "No exact matching parts were found in current stock for this enquiry."

    system_prompt = f"""You are writing a reply email on behalf of Cherrywood Auto Parts, a Birmingham-based VAG vehicle breaker (Audi, VW, SEAT, Skoda).

Customer enquiry details:
Name: {customer_data.get('name', 'Customer')}
Vehicle: {customer_data.get('vehicle', 'Not specified')}
Part needed: {customer_data.get('part', 'Not specified')}

{inventory_context}

RULES — FOLLOW EXACTLY:
1. If matching parts were found above, reference them by name and exact price. Never invent a price or part that isn't listed above.
2. If no matching parts were found, do NOT guess or make up a part or price. Instead write a warm, honest reply saying a staff member will check current stock and follow up shortly, typically within 2 hours.
3. Keep the tone friendly, professional, and concise — 3 to 5 sentences maximum.
4. Sign off as "The Cherrywood Auto Parts Team".
5. Do not include a subject line, only the email body.
6. Do not use markdown formatting, just plain text suitable for an email.
"""

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Write the reply email now."}
        ],
        "max_tokens": 300
    }

    try:
        response = requests.post("https://api.openai.com/v1/chat/completions", json=payload, headers=headers, timeout=15)
        if response.status_code != 200:
            print(f"❌ [Email Reply] OpenAI error: {response.text}", flush=True)
            return None
        return response.json()['choices'][0]['message']['content'].strip()
    except Exception as e:
        print(f"❌ [Email Reply] Generation failed: {e}", flush=True)
        return None


def send_reply_email(customer_data, reply_body):
    """Sends the generated reply directly to the customer's email address."""
    sender = os.getenv('EMAIL_USER')
    password = os.getenv('EMAIL_PASS')
    recipient = customer_data.get('email')

    if not sender or not password or not recipient:
        print("❌ [Email Reply] Missing sender credentials or customer email — reply not sent", flush=True)
        return False

    try:
        msg = MIMEMultipart()
        msg['From'] = sender
        msg['To'] = recipient
        msg['Subject'] = f"Re: Your enquiry about {customer_data.get('part', 'your part')} - Cherrywood Auto Parts"
        msg.attach(MIMEText(reply_body, 'plain'))

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender, password)
        server.send_message(msg)
        server.quit()

        print(f"📧 [Email Reply] Sent to customer: {recipient}", flush=True)
        return True
    except Exception as e:
        print(f"❌ [Email Reply] Failed to send to customer: {e}", flush=True)
        return False


def handle_enquiry_auto_reply(customer_data, get_db_func):
    """
    Main entry point — call this after an enquiry is saved.
    Looks up matching parts, generates a reply, and sends it to the customer.
    Returns the reply text (or None if it failed), so it can also be logged.
    """
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        print("❌ [Email Reply] No OpenAI API key configured", flush=True)
        return None

    search_text = f"{customer_data.get('vehicle', '')} {customer_data.get('part', '')}"
    matched_parts = find_matching_parts(get_db_func, search_text)

    reply_body = generate_email_reply(customer_data, matched_parts, api_key)
    if not reply_body:
        return None

    sent = send_reply_email(customer_data, reply_body)
    return reply_body if sent else None
