"""
Krishi Bazaar — e-mail notifications.
Set SMTP_HOST (+ SMTP_USER / SMTP_PASSWORD) to send real e-mail; otherwise messages are only logged.
Sending runs in a background thread so a slow mail server never slows a page down.
"""
import email.utils
import logging
import smtplib
import threading
from email.message import EmailMessage
from typing import Optional, Tuple

from ..core import config

logger = logging.getLogger("krishi.notify")


def _deliver(to: str, subject: str, body: str) -> None:
    if not config.SMTP_HOST:
        logger.info("EMAIL (not sent, SMTP not configured) to=%s subject=%r\n%s", to, subject, body)
        return
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = config.SMTP_FROM, to, subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=15) as smtp:
            smtp.starttls()
            if config.SMTP_USER:
                smtp.login(config.SMTP_USER, config.SMTP_PASSWORD)
            smtp.send_message(msg)
    except Exception:  # never let e-mail problems break an order
        logger.exception("Could not send e-mail to %s", to)


def send_email(to: Optional[str], subject: str, body: str) -> None:
    if not to or "@" not in to:
        return
    threading.Thread(target=_deliver, args=(to, subject, body), daemon=True).start()


# ---- order events ---------------------------------------------------------------
def order_placed(order) -> None:
    product, buyer = order.product, order.buyer
    send_email(product.farmer.email, f"New order #{order.id} for {product.crop_name}",
               f"Hello {product.farmer.get_full_name},\n\n{buyer.get_full_name} ordered {order.quantity} "
               f"{product.unit} of {product.crop_name} (total Rs {order.total_price}).\n"
               "Please open your Farmer Dashboard to accept or reject the order.\n\n- Krishi Bazaar")
    send_email(buyer.email, f"Order #{order.id} received",
               f"Hello {buyer.get_full_name},\n\nWe received your order for {order.quantity} {product.unit} of "
               f"{product.crop_name} (total Rs {order.total_price}). The farmer will confirm it shortly.\n\n- Krishi Bazaar")


def order_status_changed(order) -> None:
    buyer, product = order.buyer, order.product
    send_email(buyer.email, f"Order #{order.id} {order.status}",
               f"Hello {buyer.get_full_name},\n\nYour order #{order.id} for {product.crop_name} "
               f"was {order.status} by the farmer.\n\n- Krishi Bazaar")


def order_dispatched(order) -> None:
    buyer, product = order.buyer, order.product
    send_email(buyer.email, f"Order #{order.id} is on its way",
               f"Hello {buyer.get_full_name},\n\nYour {product.crop_name} was handed to {order.courier_partner}.\n"
               f"Tracking number: {order.tracking_number}\n\n- Krishi Bazaar")


def password_reset(user, link: str) -> None:
    send_email(user.email, "Reset your Krishi Bazaar password",
               f"Hello {user.get_full_name},\n\nUse this link within 1 hour to choose a new password:\n{link}\n\n"
               "If you did not ask for this, you can ignore this e-mail.\n\n- Krishi Bazaar")
    if not config.SMTP_HOST:
        logger.warning("PASSWORD RESET LINK for %s: %s", user.username, link)


def send_otp_email(to: str, otp: str, purpose: str = "Verification") -> Tuple[bool, Optional[str]]:
    """
    Deliver OTP verification email synchronously with rich HTML + plain-text fallback.
    Returns (success: bool, error_description: Optional[str]).
    """
    subject = f"🌾 {otp} is your Krishi Bazaar verification code"

    host = config.SMTP_HOST.strip() if config.SMTP_HOST else ""
    port = int(config.SMTP_PORT) if config.SMTP_PORT else 587
    user = config.SMTP_USER.strip() if config.SMTP_USER else ""
    # Google App Passwords often have spaces when copied (e.g. 'abcd efgh ijkl mnop')
    password = config.SMTP_PASSWORD.replace(" ", "").strip() if config.SMTP_PASSWORD else ""
    sender = config.SMTP_FROM or user or "no-reply@krishibazaar.local"

    # If SMTP is not yet configured, log OTP prominently for local testing
    if not host or not user or not password:
        logger.warning("==================================================")
        logger.warning("[GMAIL OTP NOTICE: SMTP CREDENTIALS NOT SET IN .env]")
        logger.warning("To: %s | OTP: %s | Purpose: %s", to, otp, purpose)
        logger.warning("To receive real emails in your inbox, set SMTP_USER and SMTP_PASSWORD in .env")
        logger.warning("==================================================")
        return False, "SMTP_NOT_CONFIGURED"

    plain_text = (
        f"Namaste,\n\n"
        f"Your verification code for Krishi Bazaar ({purpose}) is:\n\n"
        f"       {otp}\n\n"
        f"This code will expire in 10 minutes.\n"
        f"Please do not share this code with anyone for your account security.\n\n"
        f"Warm regards,\n"
        f"Krishi Bazaar Sovereign Agrarian Exchange"
    )

    html_content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Your Verification Code</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f7f5f0; margin: 0; padding: 30px 15px;">
  <table align="center" border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width: 520px; background-color: #ffffff; border-radius: 14px; border: 1px solid #e5dfd0; box-shadow: 0 4px 20px rgba(0,0,0,0.06); overflow: hidden;">
    <tr>
      <td style="background: #07150e; padding: 28px 32px; text-align: center;">
        <div style="font-size: 24px; font-weight: 800; color: #d4af37; letter-spacing: 1.5px; font-family: Georgia, serif;">🌾 KRISHI BAZAAR</div>
        <div style="font-size: 11px; color: rgba(212,175,55,0.75); letter-spacing: 2.5px; text-transform: uppercase; margin-top: 4px;">Sovereign Agrarian Exchange</div>
      </td>
    </tr>
    <tr>
      <td style="padding: 36px 32px 28px;">
        <h2 style="font-size: 20px; font-weight: 700; color: #1a2920; margin: 0 0 12px; font-family: Georgia, serif;">Verification Code</h2>
        <p style="font-size: 14px; color: #555555; line-height: 1.5; margin: 0 0 24px;">
          Use the following 6-digit one-time passcode (OTP) to complete your <strong>{purpose}</strong>:
        </p>
        <div style="background: #fdfbf7; border: 1.5px dashed #d4af37; border-radius: 10px; padding: 22px; text-align: center; margin: 0 0 24px;">
          <span style="font-size: 38px; font-weight: 800; letter-spacing: 8px; color: #0d261a; font-family: Consolas, monospace;">{otp}</span>
          <div style="font-size: 12px; color: #888888; margin-top: 8px;">Valid for 10 minutes &bull; Single-use security token</div>
        </div>
        <p style="font-size: 12.5px; color: #777777; line-height: 1.5; margin: 0;">
          If you did not request this verification code, please ignore this email or review your account security.
        </p>
      </td>
    </tr>
    <tr>
      <td style="background-color: #f7f5f0; border-top: 1px solid #ebe6da; padding: 18px 32px; text-align: center; font-size: 11.5px; color: #888888;">
        &copy; Krishi Bazaar &bull; Direct Farm-to-Buyer Sovereign Marketplace
      </td>
    </tr>
  </table>
</body>
</html>"""

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg["Message-ID"] = email.utils.make_msgid(domain="krishibazaar.local")
    msg["X-Priority"] = "1"
    msg["Importance"] = "high"
    msg.set_content(plain_text)
    msg.add_alternative(html_content, subtype="html")

    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=12) as smtp:
                if user and password:
                    smtp.login(user, password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=12) as smtp:
                smtp.ehlo()
                smtp.starttls()
                smtp.ehlo()
                if user and password:
                    smtp.login(user, password)
                smtp.send_message(msg)
        logger.info("Successfully delivered OTP email to %s via %s:%s", to, host, port)
        return True, None
    except smtplib.SMTPAuthenticationError as e:
        err = "Gmail Authentication Failed: Bad username or password. For Gmail, you must generate a 16-character App Password at https://myaccount.google.com/apppasswords"
        logger.error("SMTP Auth Error for %s: %s", to, e)
        return False, err
    except Exception as e:
        err = f"SMTP Delivery Error: {type(e).__name__} ({str(e)})"
        logger.exception("Failed to send OTP email to %s: %s", to, e)
        return False, err


