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

import settings_store

COMPANY_NAME = "Cherrywood Auto Parts"
COMPANY_EMAIL = "cherryvagparts@gmail.com"
COMPANY_ADDRESS = "Bordesley Green, Birmingham"
BRAND_COLOR = "#EA580C"  # orange, matching your site's accent colour


def build_confirmation_email(customer_data: dict, resolved_items: list[dict] | None = None, enquiry_id: int | None = None):
    name = customer_data.get("name", "there")
    resolved_items = resolved_items or []
    # Pulled fresh on every call so an admin editing these in /admin/settings
    # takes effect immediately, with no deploy needed.
    company_phone = settings_store.get_setting("company_phone")
    whatsapp_link = settings_store.get_setting("whatsapp_link")
    phone_tel_href = "tel:" + company_phone.replace(" ", "")

    subject = f"We've received your enquiry — {COMPANY_NAME}"

    if resolved_items:
        rows_html = "\n".join(_item_row_html(it, customer_data) for it in resolved_items)
        rows_text = "\n".join(_item_row_text(it, customer_data) for it in resolved_items)
    else:
        # Fallback for when resolved_items isn't passed through — no
        # itemized OEM/price data available here, just what the customer
        # typed on the enquiry form.
        fallback_part = customer_data.get("part", "the part you enquired about")
        fallback_vehicle = customer_data.get("vehicle", "N/A")
        rows_html = f"""
        <tr>
            <td style="padding:12px 16px; border-top:1px solid #f0f0f0; font-size:14px; color:#111;">{fallback_part}</td>
            <td style="padding:12px 16px; border-top:1px solid #f0f0f0; font-size:14px; color:#888;">{fallback_vehicle}</td>
        </tr>
        """
        rows_text = f"- {fallback_part} ({fallback_vehicle})"

    customer_email = customer_data.get("email") or "N/A"
    customer_phone = customer_data.get("phone")

    phone_detail_html = f'<p style="margin:4px 0 0 0; color:#444; font-size:14px;">Phone: {customer_phone}</p>' if customer_phone else ""
    phone_detail_text = f"Phone: {customer_phone}\n" if customer_phone else ""

    ref_html = f'<p style="margin:20px 0 0 0; color:#999; font-size:12px;">Enquiry ref: #{enquiry_id}</p>' if enquiry_id else ""
    ref_text = f"\nEnquiry ref: #{enquiry_id}" if enquiry_id else ""

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
                We've received your request for the following part:
              </p>

              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #eee; border-radius:6px; overflow:hidden;">
                <tr style="background:#fafafa;">
                  <td style="padding:10px 16px; font-size:12px; text-transform:uppercase; color:#888; font-weight:600;">Part</td>
                  <td style="padding:10px 16px; font-size:12px; text-transform:uppercase; color:#888; font-weight:600;">Vehicle</td>
                </tr>
                {rows_html}
              </table>

              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:20px; background:#fafafa; border-radius:6px;">
                <tr>
                  <td style="padding:14px 16px;">
                    <p style="margin:0; color:#888; font-size:12px; text-transform:uppercase; font-weight:600;">Your details</p>
                    <p style="margin:8px 0 0 0; color:#444; font-size:14px;">Email: {customer_email}</p>
                    {phone_detail_html}
                  </td>
                </tr>
              </table>

              <p style="margin:16px 0 0 0; color:#888; font-size:13px; line-height:1.5;">
                If anything above looks wrong, just reply to this email.
              </p>

              <p style="margin:16px 0 0 0; color:#444; font-size:15px; line-height:1.5;">
                A member of our team will call or email you within <strong>2 hours</strong> to confirm availability,
                arrange delivery or collection, and take payment.
              </p>

              <table role="presentation" cellpadding="0" cellspacing="0" style="margin-top:24px;">
                <tr>
                  <td style="border-radius:6px; background:{BRAND_COLOR};">
                    <a href="{whatsapp_link}" style="display:inline-block; padding:12px 24px; color:#ffffff; text-decoration:none; font-weight:600; font-size:14px;">
                      Message us on WhatsApp
                    </a>
                  </td>
                  <td style="width:12px;"></td>
                  <td style="border-radius:6px; background:#1a1a1a;">
                    <a href="{phone_tel_href}" style="display:inline-block; padding:12px 24px; color:#ffffff; text-decoration:none; font-weight:600; font-size:14px;">
                      Call us: {company_phone}
                    </a>
                  </td>
                </tr>
              </table>

              {ref_html}
            </td>
          </tr>

          <tr>
            <td style="padding:20px 32px; background:#fafafa; border-top:1px solid #eee;">
              <p style="margin:0; color:#888; font-size:13px; line-height:1.6;">
                {COMPANY_NAME} · {COMPANY_ADDRESS}<br>
                {company_phone} · {COMPANY_EMAIL}
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

We've received your request for the following part:

{rows_text}

Your details:
Email: {customer_email}
{phone_detail_text}
If anything above looks wrong, just reply to this email.

A member of our team will call or email you within 2 hours to confirm availability,
arrange delivery or collection, and take payment.

WhatsApp us: {whatsapp_link}
Call us: {company_phone}
{ref_text}

--
{COMPANY_NAME}
{COMPANY_ADDRESS}
{company_phone} · {COMPANY_EMAIL}
"""

    return subject, html_body, text_body


def _item_row_html(item: dict, customer_data: dict) -> str:
    name = item.get("name", "N/A")
    vehicle = item.get("vehicle") or customer_data.get("vehicle", "N/A")
    return f"""
        <tr>
            <td style="padding:12px 16px; border-top:1px solid #f0f0f0; font-size:14px; color:#111;">{name}</td>
            <td style="padding:12px 16px; border-top:1px solid #f0f0f0; font-size:14px; color:#888;">{vehicle}</td>
        </tr>
    """


def _item_row_text(item: dict, customer_data: dict) -> str:
    name = item.get("name", "N/A")
    vehicle = item.get("vehicle") or customer_data.get("vehicle", "N/A")
    return f"- {name} ({vehicle})"
