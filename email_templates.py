"""
email_templates.py

Builds a proper branded confirmation email instead of a single run-on
sentence. Uses multipart/alternative (HTML + plain text fallback) so it
renders well in every email client and doesn't get flagged as spammy
plain-text-only.

Usage:
    from email_templates import build_confirmation_email
    subject, html_body, text_body = build_confirmation_email(customer_data, resolved_items)

`resolved_items` should be the same real DB-backed list your proxy_chat
route already produces via tracker.resolve_selections() — never model-
generated text, so prices/names in the email are guaranteed accurate.

If resolved_items isn't available (e.g. an older code path), pass an
empty list and the template falls back to customer_data['part'] as a
single line — still styled, just not itemized.
"""

COMPANY_NAME = "Cherrywood Auto Parts"
COMPANY_PHONE = "Your business phone here"
COMPANY_WHATSAPP_LINK = "https://wa.me/44XXXXXXXXXX"  # replace with your real WhatsApp link
COMPANY_EMAIL = "cherryvagparts@gmail.com"
COMPANY_ADDRESS = "Bordesley Green, Birmingham"
BRAND_COLOR = "#EA580C"  # orange, matching your site's accent colour


def build_confirmation_email(customer_data: dict, resolved_items: list[dict] | None = None):
    name = customer_data.get("name", "there")
    resolved_items = resolved_items or []

    if resolved_items:
        subject = f"Your enquiry: {', '.join(it['name'] for it in resolved_items)} - {COMPANY_NAME}"
        total = sum(float(it.get("price", 0)) for it in resolved_items)
        rows_html = "\n".join(_item_row_html(it) for it in resolved_items)
        rows_text = "\n".join(_item_row_text(it) for it in resolved_items)
        total_html = f"""
        <tr>
            <td colspan="2" style="padding:12px 16px; text-align:right; font-weight:600; border-top:2px solid #eee;">Total</td>
            <td style="padding:12px 16px; text-align:right; font-weight:700; color:{BRAND_COLOR}; border-top:2px solid #eee;">£{total:.2f}</td>
        </tr>
        """
        total_text = f"Total: £{total:.2f}"
    else:
        # Fallback for when resolved_items isn't passed through
        fallback_part = customer_data.get("part", "the part you enquired about")
        subject = f"Your enquiry: {fallback_part} - {COMPANY_NAME}"
        rows_html = f"""
        <tr>
            <td colspan="3" style="padding:12px 16px;">{fallback_part}</td>
        </tr>
        """
        rows_text = fallback_part
        total_html = ""
        total_text = ""

    html_body = f"""\
<!DOCTYPE html>
<html>
<body style="margin:0; padding:0; background:#f4f4f5; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f5; padding:24px 0;">
    <tr>
      <td align="center">
        <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="background:#ffffff; border-radius:8px; overflow:hidden;">

          <tr>
            <td style="background:#1a1a1a; padding:24px 32px;">
              <span style="color:#ffffff; font-size:20px; font-weight:700; letter-spacing:0.5px;">{COMPANY_NAME.upper()}</span>
            </td>
          </tr>

          <tr>
            <td style="padding:32px;">
              <h1 style="margin:0 0 16px 0; font-size:20px; color:#111;">Thanks for your enquiry, {name}</h1>
              <p style="margin:0 0 24px 0; color:#444; font-size:15px; line-height:1.5;">
                We've received your request and confirmed the following part{'s' if len(resolved_items) != 1 else ''} are available:
              </p>

              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #eee; border-radius:6px; overflow:hidden;">
                <tr style="background:#fafafa;">
                  <td style="padding:10px 16px; font-size:12px; text-transform:uppercase; color:#888; font-weight:600;">Part</td>
                  <td style="padding:10px 16px; font-size:12px; text-transform:uppercase; color:#888; font-weight:600;">OEM</td>
                  <td style="padding:10px 16px; font-size:12px; text-transform:uppercase; color:#888; font-weight:600; text-align:right;">Price</td>
                </tr>
                {rows_html}
                {total_html}
              </table>

              <p style="margin:24px 0 0 0; color:#444; font-size:15px; line-height:1.5;">
                A member of our team will call or email you within <strong>2 hours</strong> to confirm availability,
                arrange delivery or collection, and take payment.
              </p>

              <table role="presentation" cellpadding="0" cellspacing="0" style="margin-top:24px;">
                <tr>
                  <td style="border-radius:6px; background:{BRAND_COLOR};">
                    <a href="{COMPANY_WHATSAPP_LINK}" style="display:inline-block; padding:12px 24px; color:#ffffff; text-decoration:none; font-weight:600; font-size:14px;">
                      Message us on WhatsApp
                    </a>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <tr>
            <td style="padding:20px 32px; background:#fafafa; border-top:1px solid #eee;">
              <p style="margin:0; color:#888; font-size:13px; line-height:1.6;">
                {COMPANY_NAME} · {COMPANY_ADDRESS}<br>
                {COMPANY_PHONE} · {COMPANY_EMAIL}
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""

    text_body = f"""\
Thanks for your enquiry, {name}

We've received your request and confirmed the following part(s) are available:

{rows_text}
{total_text}

A member of our team will call or email you within 2 hours to confirm availability,
arrange delivery or collection, and take payment.

WhatsApp us: {COMPANY_WHATSAPP_LINK}

--
{COMPANY_NAME}
{COMPANY_ADDRESS}
{COMPANY_PHONE} · {COMPANY_EMAIL}
"""

    return subject, html_body, text_body


def _item_row_html(item: dict) -> str:
    name = item.get("name", "N/A")
    oem = item.get("oem", "N/A")
    price = float(item.get("price", 0))
    return f"""
        <tr>
            <td style="padding:12px 16px; border-top:1px solid #f0f0f0; font-size:14px; color:#111;">{name}</td>
            <td style="padding:12px 16px; border-top:1px solid #f0f0f0; font-size:14px; color:#888;">{oem}</td>
            <td style="padding:12px 16px; border-top:1px solid #f0f0f0; font-size:14px; color:#111; text-align:right;">£{price:.2f}</td>
        </tr>
    """


def _item_row_text(item: dict) -> str:
    name = item.get("name", "N/A")
    oem = item.get("oem", "N/A")
    price = float(item.get("price", 0))
    return f"- {name} (OEM: {oem}) — £{price:.2f}"
