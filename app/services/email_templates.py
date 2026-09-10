from app.core.config import get_settings

# ── Brand ────────────────────────────────────────────────────────────
# Matches the Elizade Connect mobile app: near-black surfaces, gold accent.
BRAND_BLACK = "#0A0A0B"
BRAND_INK = "#141A21"
BRAND_GOLD = "#F5B301"
BRAND_GOLD_DARK = "#D89A00"
ON_GOLD = "#1E1B00"
TEXT_MUTED = "#5C6470"
TEXT_FAINT = "#9AA1AC"
SURFACE_ALT = "#F5F6F8"
BORDER = "#E6E9EE"


def _otp_purpose_label(purpose: str) -> str:
    if purpose == "login":
        return "sign in to Elizade Connect"
    if purpose == "register":
        return "complete your registration"
    return "verify your identity"


def _otp_heading(purpose: str) -> str:
    return "Welcome to Elizade Connect" if purpose == "register" else "Your verification code"


def build_otp_plain_text(*, code: str, purpose: str) -> str:
    """Plain-text alternative. Some clients prefer or only render this."""
    settings = get_settings()
    return (
        f"Your Elizade Connect verification code is {code}\n\n"
        f"Use this code to {_otp_purpose_label(purpose)}. "
        f"It expires in {settings.otp_expire_minutes} minutes.\n\n"
        "For your security, never share this code with anyone. "
        "Elizade staff will never ask you for it.\n\n"
        "If you did not request this code, you can safely ignore this email.\n\n"
        f"Need help? Contact {settings.support_email} or {settings.support_phone}\n"
        "— Elizade Nigeria Limited · Authorised Toyota, Jetour & JAC Distributor"
    )


def build_otp_html(*, code: str, purpose: str) -> str:
    """
    Responsive HTML email for the OTP code.

    Written for email clients, not browsers:
      * table-based layout with inline CSS — the only reliably supported combo
      * no flexbox/grid, no external stylesheets, no gradients (Outlook drops
        them), no web fonts — system font stack instead
      * 600px max width, the safe standard; scales down on mobile
      * a hidden preheader controls the inbox preview snippet
      * letter-spaced monospace code so digits are unambiguous (0 vs O)
    """
    settings = get_settings()
    minutes = settings.otp_expire_minutes
    purpose_label = _otp_purpose_label(purpose)
    heading = _otp_heading(purpose)
    spaced_code = " ".join(code)  # visual grouping; plain text keeps it joined

    return f"""<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <meta http-equiv="X-UA-Compatible" content="IE=edge" />
  <meta name="color-scheme" content="light dark" />
  <meta name="supported-color-schemes" content="light dark" />
  <title>Your Elizade Connect verification code</title>
  <!--[if mso]>
  <style type="text/css">
    body, table, td {{ font-family: Arial, Helvetica, sans-serif !important; }}
  </style>
  <![endif]-->
  <style type="text/css">
    /* Small-screen tuning. Media queries are ignored by Outlook desktop,
       which is fine — the fixed 600px table already degrades gracefully. */
    @media only screen and (max-width: 620px) {{
      .wrap {{ width: 100% !important; }}
      .pad {{ padding-left: 22px !important; padding-right: 22px !important; }}
      .code {{ font-size: 34px !important; letter-spacing: 6px !important; }}
      .h1 {{ font-size: 24px !important; }}
      .stack {{ display: block !important; width: 100% !important; text-align: center !important; }}
    }}
    a {{ color: {BRAND_GOLD_DARK}; }}
  </style>
</head>
<body style="margin:0;padding:0;background-color:{SURFACE_ALT};-webkit-font-smoothing:antialiased;">

  <!-- Inbox preview text, hidden in the body -->
  <div style="display:none;font-size:1px;color:{SURFACE_ALT};line-height:1px;max-height:0;max-width:0;opacity:0;overflow:hidden;">
    Your Elizade Connect code is {code}. It expires in {minutes} minutes.
    &#8199;&#65279;&#847; &#8199;&#65279;&#847; &#8199;&#65279;&#847; &#8199;&#65279;&#847;
  </div>

  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
         style="background-color:{SURFACE_ALT};padding:28px 12px;">
    <tr>
      <td align="center">

        <table role="presentation" class="wrap" width="600" cellspacing="0" cellpadding="0" border="0"
               style="width:600px;max-width:600px;background:#ffffff;border-radius:16px;overflow:hidden;border:1px solid {BORDER};">

          <!-- Brand header -->
          <tr>
            <td style="background-color:{BRAND_BLACK};padding:28px 32px;" class="pad">
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                <tr>
                  <td align="left" style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
                    <span style="display:inline-block;font-size:22px;font-weight:700;color:{BRAND_GOLD};letter-spacing:0.5px;line-height:1;">
                      Elizade
                    </span>
                    <span style="display:inline-block;font-size:11px;font-weight:600;color:#FFFFFF;letter-spacing:4px;text-transform:uppercase;padding-left:8px;">
                      Connect
                    </span>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Gold rule (solid, not a gradient — Outlook safe) -->
          <tr><td style="height:4px;background-color:{BRAND_GOLD};font-size:0;line-height:0;">&nbsp;</td></tr>

          <!-- Heading + intro -->
          <tr>
            <td class="pad" style="padding:34px 32px 8px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
              <h1 class="h1" style="margin:0 0 10px;font-size:26px;line-height:1.25;font-weight:700;color:{BRAND_INK};">
                {heading}
              </h1>
              <p style="margin:0;font-size:15px;line-height:1.6;color:{TEXT_MUTED};">
                Use the code below to {purpose_label}.
              </p>
            </td>
          </tr>

          <!-- OTP code -->
          <tr>
            <td class="pad" style="padding:22px 32px 6px;">
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
                     style="background-color:{SURFACE_ALT};border:1px solid {BORDER};border-radius:14px;">
                <tr>
                  <td align="center" style="padding:26px 16px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
                    <p style="margin:0 0 12px;font-size:11px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:{TEXT_MUTED};">
                      Verification code
                    </p>
                    <p class="code" style="margin:0;font-family:'SFMono-Regular',Consolas,'Liberation Mono',Menlo,Courier,monospace;font-size:40px;line-height:1.1;font-weight:700;letter-spacing:8px;color:{BRAND_INK};">
                      {spaced_code}
                    </p>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Expiry -->
          <tr>
            <td class="pad" align="center" style="padding:12px 32px 0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
              <p style="margin:0;font-size:13px;color:{TEXT_MUTED};">
                This code expires in <strong style="color:{BRAND_INK};">{minutes} minutes</strong>.
              </p>
            </td>
          </tr>

          <!-- Security notice -->
          <tr>
            <td class="pad" style="padding:22px 32px 0;">
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
                     style="background-color:#FFF8E6;border-left:4px solid {BRAND_GOLD};border-radius:8px;">
                <tr>
                  <td style="padding:14px 16px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
                    <p style="margin:0;font-size:13px;line-height:1.6;color:#6B4E00;">
                      <strong>Keep this code private.</strong> Never share it with anyone —
                      Elizade staff will never ask you for your verification code.
                    </p>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Ignore notice -->
          <tr>
            <td class="pad" style="padding:20px 32px 30px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
              <p style="margin:0;font-size:13px;line-height:1.6;color:{TEXT_FAINT};">
                Didn't request this? You can safely ignore this email — no changes will be made
                to your account without this code.
              </p>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td class="pad" style="padding:22px 32px 26px;background-color:{SURFACE_ALT};border-top:1px solid {BORDER};font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
              <p style="margin:0 0 10px;font-size:13px;font-weight:600;color:{BRAND_INK};">
                Need help?
              </p>
              <p style="margin:0 0 14px;font-size:13px;line-height:1.7;color:{TEXT_MUTED};">
                <a href="mailto:{settings.support_email}" style="color:{BRAND_GOLD_DARK};text-decoration:underline;">{settings.support_email}</a>
                &nbsp;·&nbsp;
                <a href="tel:{settings.support_phone.replace(' ', '')}" style="color:{BRAND_GOLD_DARK};text-decoration:underline;">{settings.support_phone}</a>
                &nbsp;·&nbsp;
                <a href="{settings.support_url}" style="color:{BRAND_GOLD_DARK};text-decoration:underline;">Contact us</a>
              </p>
              <p style="margin:0;font-size:11px;line-height:1.6;color:{TEXT_FAINT};">
                &copy; Elizade Nigeria Limited · Authorised Distributor for Toyota, Jetour &amp; JAC<br />
                This is an automated message — please do not reply to this address.
              </p>
            </td>
          </tr>

        </table>

        <table role="presentation" class="wrap" width="600" cellspacing="0" cellpadding="0" border="0" style="width:600px;max-width:600px;">
          <tr>
            <td align="center" style="padding:16px 12px 4px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
              <p style="margin:0;font-size:11px;line-height:1.6;color:{TEXT_FAINT};">
                Sent to you because a verification code was requested for this email address.
              </p>
            </td>
          </tr>
        </table>

      </td>
    </tr>
  </table>
</body>
</html>"""


# ── Quotation ────────────────────────────────────────────────────────
#
# WHY THIS EXISTS. The quotation email was the notification body and nothing
# more: subject "Your quote is ready", body "We've prepared your quote for the
# 2024 Toyota Corolla. It's valid until 21 September 2026." No price, no line
# items, no total. A customer who opened it still had no quote — and the app's
# success sheet had promised them "a formal quotation".
#
# A quote is a DOCUMENT, not a nudge. It has to carry the figures, or the mail
# may as well not arrive: "I got an email but there's no quote in it" is the
# same complaint one step later.


def _naira(amount) -> str:
    """Naira, thousands-separated, no kobo.

    Kobo on a car price is noise — ₦28,500,000.00 reads better as ₦28,500,000.
    The `Decimal` is formatted directly rather than converted to float, so a
    long price cannot drift on its way to the customer.
    """
    return f"₦{amount:,.0f}"


def build_quotation_plain_text(
    *,
    customer_name: str,
    vehicle_label: str,
    line_items: list[tuple[str, object]],
    total,
    valid_until: str,
    reference: str,
) -> str:
    settings = get_settings()
    greeting = f"Hello {customer_name}," if customer_name else "Hello,"
    lines = [
        greeting,
        "",
        f"Here is your quotation for the {vehicle_label}.",
        "",
        f"Quotation reference: {reference}",
        "",
    ]
    for description, amount in line_items:
        lines.append(f"  {description} - {_naira(amount)}")
    lines += [
        "",
        f"TOTAL: {_naira(total)}",
        f"Valid until: {valid_until}",
        "",
        "This quotation is indicative and excludes registration, insurance and",
        "optional accessories. A sales adviser will confirm final pricing and",
        "availability before purchase.",
        "",
        "Your quotation is also saved in the Elizade Connect app.",
        "",
        f"Questions? Contact {settings.support_email} or {settings.support_phone}",
        "",
        "- Elizade Nigeria Limited - Authorised Toyota, Jetour & JAC Distributor",
    ]
    return "\n".join(lines)


def build_quotation_html(
    *,
    customer_name: str,
    vehicle_label: str,
    line_items: list[tuple[str, object]],
    total,
    valid_until: str,
    reference: str,
) -> str:
    """Branded HTML quotation, under the same email-client constraints as the
    OTP mail: table layout, inline CSS, no flexbox, no web fonts, 600px."""
    settings = get_settings()
    font = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
    greeting = f"Hello {customer_name}, here" if customer_name else "Here"

    rows = "".join(
        f"""
                <tr>
                  <td style="padding:12px 0;border-bottom:1px solid {BORDER};font-family:{font};font-size:14px;line-height:1.5;color:{BRAND_INK};">
                    {description}
                  </td>
                  <td align="right" style="padding:12px 0;border-bottom:1px solid {BORDER};font-family:{font};font-size:14px;line-height:1.5;color:{BRAND_INK};white-space:nowrap;">
                    {_naira(amount)}
                  </td>
                </tr>"""
        for description, amount in line_items
    )

    return f"""<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <meta http-equiv="X-UA-Compatible" content="IE=edge" />
  <title>Your Elizade Connect quotation</title>
  <!--[if mso]>
  <style type="text/css">
    body, table, td {{ font-family: Arial, Helvetica, sans-serif !important; }}
  </style>
  <![endif]-->
  <style type="text/css">
    @media only screen and (max-width: 620px) {{
      .wrap {{ width: 100% !important; }}
      .pad {{ padding-left: 22px !important; padding-right: 22px !important; }}
      .h1 {{ font-size: 24px !important; }}
      .total {{ font-size: 26px !important; }}
    }}
    a {{ color: {BRAND_GOLD_DARK}; }}
  </style>
</head>
<body style="margin:0;padding:0;background-color:{SURFACE_ALT};-webkit-font-smoothing:antialiased;">

  <div style="display:none;font-size:1px;color:{SURFACE_ALT};line-height:1px;max-height:0;max-width:0;opacity:0;overflow:hidden;">
    Your quotation for the {vehicle_label} - {_naira(total)}, valid until {valid_until}.
    &#8199;&#65279;&#847; &#8199;&#65279;&#847; &#8199;&#65279;&#847; &#8199;&#65279;&#847;
  </div>

  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
         style="background-color:{SURFACE_ALT};padding:28px 12px;">
    <tr>
      <td align="center">

        <table role="presentation" class="wrap" width="600" cellspacing="0" cellpadding="0" border="0"
               style="width:600px;max-width:600px;background:#ffffff;border-radius:16px;overflow:hidden;border:1px solid {BORDER};">

          <tr>
            <td style="background-color:{BRAND_BLACK};padding:28px 32px;" class="pad">
              <span style="display:inline-block;font-family:{font};font-size:22px;font-weight:700;color:{BRAND_GOLD};letter-spacing:0.5px;line-height:1;">
                Elizade
              </span>
              <span style="display:inline-block;font-family:{font};font-size:11px;font-weight:600;color:#FFFFFF;letter-spacing:4px;text-transform:uppercase;padding-left:8px;">
                Connect
              </span>
            </td>
          </tr>

          <tr><td style="height:4px;background-color:{BRAND_GOLD};font-size:0;line-height:0;">&nbsp;</td></tr>

          <tr>
            <td class="pad" style="padding:34px 32px 4px;font-family:{font};">
              <h1 class="h1" style="margin:0 0 10px;font-size:26px;line-height:1.25;font-weight:700;color:{BRAND_INK};">
                Your quotation
              </h1>
              <p style="margin:0;font-size:15px;line-height:1.6;color:{TEXT_MUTED};">
                {greeting} is your quotation for the
                <strong style="color:{BRAND_INK};">{vehicle_label}</strong>.
              </p>
            </td>
          </tr>

          <tr>
            <td class="pad" style="padding:24px 32px 0;">
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                <tr>
                  <td style="padding:0 0 8px;font-family:{font};font-size:11px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:{TEXT_MUTED};">
                    Breakdown
                  </td>
                  <td align="right" style="padding:0 0 8px;font-family:{font};font-size:11px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:{TEXT_MUTED};">
                    Amount
                  </td>
                </tr>{rows}
              </table>
            </td>
          </tr>

          <tr>
            <td class="pad" style="padding:20px 32px 0;">
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
                     style="background-color:{SURFACE_ALT};border:1px solid {BORDER};border-radius:14px;">
                <tr>
                  <td style="padding:20px;font-family:{font};">
                    <p style="margin:0 0 4px;font-size:11px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:{TEXT_MUTED};">
                      Total
                    </p>
                    <p class="total" style="margin:0;font-size:30px;line-height:1.15;font-weight:700;color:{BRAND_INK};">
                      {_naira(total)}
                    </p>
                  </td>
                  <td align="right" style="padding:20px;font-family:{font};">
                    <p style="margin:0 0 4px;font-size:11px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:{TEXT_MUTED};">
                      Valid until
                    </p>
                    <p style="margin:0;font-size:15px;line-height:1.4;font-weight:600;color:{BRAND_INK};white-space:nowrap;">
                      {valid_until}
                    </p>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <tr>
            <td class="pad" style="padding:14px 32px 0;font-family:{font};">
              <p style="margin:0;font-size:12px;color:{TEXT_FAINT};">
                Reference {reference}
              </p>
            </td>
          </tr>

          <tr>
            <td class="pad" style="padding:22px 32px 0;">
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
                     style="background-color:#FFF8E6;border-left:4px solid {BRAND_GOLD};border-radius:8px;">
                <tr>
                  <td style="padding:14px 16px;font-family:{font};">
                    <p style="margin:0;font-size:13px;line-height:1.6;color:#6B4E00;">
                      This quotation is indicative and excludes registration, insurance
                      and optional accessories. A sales adviser will confirm final
                      pricing and availability before purchase.
                    </p>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <tr>
            <td class="pad" style="padding:20px 32px 30px;font-family:{font};">
              <p style="margin:0;font-size:13px;line-height:1.6;color:{TEXT_FAINT};">
                Your quotation is also saved in the Elizade Connect app.
              </p>
            </td>
          </tr>

          <tr>
            <td class="pad" style="padding:22px 32px 26px;background-color:{SURFACE_ALT};border-top:1px solid {BORDER};font-family:{font};">
              <p style="margin:0 0 10px;font-size:13px;font-weight:600;color:{BRAND_INK};">
                Questions about this quote?
              </p>
              <p style="margin:0 0 14px;font-size:13px;line-height:1.7;color:{TEXT_MUTED};">
                <a href="mailto:{settings.support_email}" style="color:{BRAND_GOLD_DARK};text-decoration:underline;">{settings.support_email}</a>
                &nbsp;&#183;&nbsp;
                <a href="tel:{settings.support_phone.replace(' ', '')}" style="color:{BRAND_GOLD_DARK};text-decoration:underline;">{settings.support_phone}</a>
              </p>
              <p style="margin:0;font-size:11px;line-height:1.6;color:{TEXT_FAINT};">
                &copy; Elizade Nigeria Limited &#183; Authorised Distributor for Toyota, Jetour &amp; JAC<br />
                This is an automated message &#8212; please do not reply to this address.
              </p>
            </td>
          </tr>

        </table>

      </td>
    </tr>
  </table>
</body>
</html>"""



# ── Reservation ──────────────────────────────────────────────────────
#
# The app's success sheet said "A confirmation has been sent to your email".
# Nothing was sent — there was no reservation event in the catalogue, no
# template, and no call. The customer was told a receipt existed for a hold on
# a car worth millions of naira, and nothing arrived.
#
# NO PAYMENT IS TAKEN at this point. The hold is real and the vehicle is marked
# reserved, but the deposit is arranged with the branch afterwards, so the
# figure below is labelled as owed, not received. The app had the same bug on
# screen, printing "Deposit Paid" beside an amount nobody had paid.


def build_reservation_plain_text(
    *,
    customer_name: str,
    vehicle_label: str,
    branch: str,
    deposit,
    hold_until: str,
    reference: str,
) -> str:
    settings = get_settings()
    greeting = f"Hello {customer_name}," if customer_name else "Hello,"
    lines = [
        greeting,
        "",
        f"The {vehicle_label} is now held for you at {branch}.",
        "",
        f"Reservation reference: {reference}",
        f"Held until: {hold_until}",
    ]
    if deposit and deposit > 0:
        lines += [
            f"Deposit to pay: {_naira(deposit)}",
            "",
            "NO PAYMENT HAS BEEN TAKEN YET. Our sales team will contact you to",
            "arrange the deposit, which is deducted from the final price.",
        ]
    else:
        lines += ["", "No deposit has been taken. Our sales team will be in touch."]
    lines += [
        "",
        "If the hold expires the vehicle returns to general availability, so",
        "please get in touch before then if you need longer.",
        "",
        f"Questions? Contact {settings.support_email} or {settings.support_phone}",
        "",
        "- Elizade Nigeria Limited - Authorised Toyota, Jetour & JAC Distributor",
    ]
    return "\n".join(lines)


def build_reservation_html(
    *,
    customer_name: str,
    vehicle_label: str,
    branch: str,
    deposit,
    hold_until: str,
    reference: str,
) -> str:
    """Branded receipt, under the same email-client constraints as the rest:
    table layout, inline CSS, no flexbox, no web fonts, 600px."""
    settings = get_settings()
    font = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
    greeting = f"Hello {customer_name}, the" if customer_name else "The"

    deposit_block = ""
    if deposit and deposit > 0:
        deposit_block = f"""
          <tr>
            <td class="pad" style="padding:20px 32px 0;">
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
                     style="background-color:#FFF8E6;border-left:4px solid {BRAND_GOLD};border-radius:8px;">
                <tr>
                  <td style="padding:14px 16px;font-family:{font};">
                    <p style="margin:0 0 4px;font-size:13px;line-height:1.6;color:#6B4E00;">
                      <strong>Deposit to pay: {_naira(deposit)}</strong>
                    </p>
                    <p style="margin:0;font-size:13px;line-height:1.6;color:#6B4E00;">
                      No payment has been taken yet. Our sales team will contact you
                      to arrange it, and it is deducted from the final price.
                    </p>
                  </td>
                </tr>
              </table>
            </td>
          </tr>"""

    return f"""<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <meta http-equiv="X-UA-Compatible" content="IE=edge" />
  <title>Your Elizade Connect reservation</title>
  <!--[if mso]>
  <style type="text/css">
    body, table, td {{ font-family: Arial, Helvetica, sans-serif !important; }}
  </style>
  <![endif]-->
  <style type="text/css">
    @media only screen and (max-width: 620px) {{
      .wrap {{ width: 100% !important; }}
      .pad {{ padding-left: 22px !important; padding-right: 22px !important; }}
      .h1 {{ font-size: 24px !important; }}
    }}
    a {{ color: {BRAND_GOLD_DARK}; }}
  </style>
</head>
<body style="margin:0;padding:0;background-color:{SURFACE_ALT};-webkit-font-smoothing:antialiased;">

  <div style="display:none;font-size:1px;color:{SURFACE_ALT};line-height:1px;max-height:0;max-width:0;opacity:0;overflow:hidden;">
    The {vehicle_label} is held for you at {branch} until {hold_until}.
    &#8199;&#65279;&#847; &#8199;&#65279;&#847; &#8199;&#65279;&#847; &#8199;&#65279;&#847;
  </div>

  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
         style="background-color:{SURFACE_ALT};padding:28px 12px;">
    <tr>
      <td align="center">

        <table role="presentation" class="wrap" width="600" cellspacing="0" cellpadding="0" border="0"
               style="width:600px;max-width:600px;background:#ffffff;border-radius:16px;overflow:hidden;border:1px solid {BORDER};">

          <tr>
            <td style="background-color:{BRAND_BLACK};padding:28px 32px;" class="pad">
              <span style="display:inline-block;font-family:{font};font-size:22px;font-weight:700;color:{BRAND_GOLD};letter-spacing:0.5px;line-height:1;">
                Elizade
              </span>
              <span style="display:inline-block;font-family:{font};font-size:11px;font-weight:600;color:#FFFFFF;letter-spacing:4px;text-transform:uppercase;padding-left:8px;">
                Connect
              </span>
            </td>
          </tr>

          <tr><td style="height:4px;background-color:{BRAND_GOLD};font-size:0;line-height:0;">&nbsp;</td></tr>

          <tr>
            <td class="pad" style="padding:34px 32px 4px;font-family:{font};">
              <h1 class="h1" style="margin:0 0 10px;font-size:26px;line-height:1.25;font-weight:700;color:{BRAND_INK};">
                Vehicle reserved
              </h1>
              <p style="margin:0;font-size:15px;line-height:1.6;color:{TEXT_MUTED};">
                {greeting} <strong style="color:{BRAND_INK};">{vehicle_label}</strong> is
                now held for you at <strong style="color:{BRAND_INK};">{branch}</strong>.
              </p>
            </td>
          </tr>

          <tr>
            <td class="pad" style="padding:22px 32px 0;">
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
                     style="background-color:{SURFACE_ALT};border:1px solid {BORDER};border-radius:14px;">
                <tr>
                  <td style="padding:20px;font-family:{font};">
                    <p style="margin:0 0 4px;font-size:11px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:{TEXT_MUTED};">
                      Held until
                    </p>
                    <p style="margin:0;font-size:20px;line-height:1.2;font-weight:700;color:{BRAND_INK};">
                      {hold_until}
                    </p>
                  </td>
                  <td align="right" style="padding:20px;font-family:{font};">
                    <p style="margin:0 0 4px;font-size:11px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:{TEXT_MUTED};">
                      Reference
                    </p>
                    <p style="margin:0;font-size:15px;line-height:1.4;font-weight:600;color:{BRAND_INK};white-space:nowrap;">
                      {reference}
                    </p>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
{deposit_block}
          <tr>
            <td class="pad" style="padding:20px 32px 30px;font-family:{font};">
              <p style="margin:0;font-size:13px;line-height:1.6;color:{TEXT_FAINT};">
                If the hold expires the vehicle returns to general availability, so
                please get in touch before then if you need longer. Your reservation
                is also saved in the Elizade Connect app.
              </p>
            </td>
          </tr>

          <tr>
            <td class="pad" style="padding:22px 32px 26px;background-color:{SURFACE_ALT};border-top:1px solid {BORDER};font-family:{font};">
              <p style="margin:0 0 10px;font-size:13px;font-weight:600;color:{BRAND_INK};">
                Questions about this reservation?
              </p>
              <p style="margin:0 0 14px;font-size:13px;line-height:1.7;color:{TEXT_MUTED};">
                <a href="mailto:{settings.support_email}" style="color:{BRAND_GOLD_DARK};text-decoration:underline;">{settings.support_email}</a>
                &nbsp;&#183;&nbsp;
                <a href="tel:{settings.support_phone.replace(' ', '')}" style="color:{BRAND_GOLD_DARK};text-decoration:underline;">{settings.support_phone}</a>
              </p>
              <p style="margin:0;font-size:11px;line-height:1.6;color:{TEXT_FAINT};">
                &copy; Elizade Nigeria Limited &#183; Authorised Distributor for Toyota, Jetour &amp; JAC<br />
                This is an automated message &#8212; please do not reply to this address.
              </p>
            </td>
          </tr>

        </table>

      </td>
    </tr>
  </table>
</body>
</html>"""



# ── The shared shell ─────────────────────────────────────────────────
#
# EVERY notification email that is not the OTP, the quotation or the
# reservation went out as bare plain text. A ticket confirmation arrived as one
# unstyled sentence from an address on somebody else's domain, which is what a
# phishing attempt looks like — and it is the single most common mail this
# system sends.
#
# Rather than hand-build a template per event, the catalogue's copy is dropped
# into one branded shell. Twenty events gain a header, a readable body, an
# optional detail table and a call to action for the price of one template, and
# a new event gets it automatically.
#
# Bespoke templates still win where the content IS the point — a quotation with
# line items, a reservation receipt. This is the floor, not the ceiling.


def _cta_button(label: str, url: str, font: str) -> str:
    """A call-to-action that survives Outlook.

    A table with a background colour, not a styled `<a>`: Outlook drops padding
    on inline anchors, which turns a button into underlined text sitting on a
    coloured smear.
    """
    return f"""
          <tr>
            <td class="pad" style="padding:26px 32px 0;">
              <table role="presentation" cellspacing="0" cellpadding="0" border="0">
                <tr>
                  <td align="center" style="background-color:{BRAND_GOLD};border-radius:10px;">
                    <a href="{url}"
                       style="display:inline-block;padding:14px 28px;font-family:{font};font-size:15px;font-weight:700;color:{ON_GOLD};text-decoration:none;">
                      {label}
                    </a>
                  </td>
                </tr>
              </table>
            </td>
          </tr>"""


def build_notification_html(
    *,
    title: str,
    body: str,
    customer_name: str = "",
    details: list[tuple[str, str]] | None = None,
    cta_label: str | None = None,
    cta_url: str | None = None,
) -> str:
    """Brand any notification, from the catalogue's title and body.

    `details` renders the vehicle or booking metadata as a two-column table —
    the thing a customer scans for rather than reads. `cta_*` adds one button;
    one, because an email with three competing actions has none.
    """
    settings = get_settings()
    font = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
    greeting = f"Hello {customer_name}," if customer_name else "Hello,"

    detail_rows = "".join(
        f"""
                <tr>
                  <td style="padding:10px 0;border-bottom:1px solid {BORDER};font-family:{font};font-size:13px;color:{TEXT_MUTED};white-space:nowrap;">
                    {label}
                  </td>
                  <td align="right" style="padding:10px 0;border-bottom:1px solid {BORDER};font-family:{font};font-size:14px;font-weight:600;color:{BRAND_INK};">
                    {value}
                  </td>
                </tr>"""
        for label, value in (details or [])
    )

    detail_block = ""
    if detail_rows:
        detail_block = f"""
          <tr>
            <td class="pad" style="padding:22px 32px 0;">
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
                     style="background-color:{SURFACE_ALT};border:1px solid {BORDER};border-radius:14px;padding:6px 18px;">
                {detail_rows}
              </table>
            </td>
          </tr>"""

    cta_block = ""
    if cta_label and cta_url:
        cta_block = _cta_button(cta_label, cta_url, font)

    return f"""<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <meta http-equiv="X-UA-Compatible" content="IE=edge" />
  <title>{title}</title>
  <!--[if mso]>
  <style type="text/css">
    body, table, td {{ font-family: Arial, Helvetica, sans-serif !important; }}
  </style>
  <![endif]-->
  <style type="text/css">
    @media only screen and (max-width: 620px) {{
      .wrap {{ width: 100% !important; }}
      .pad {{ padding-left: 22px !important; padding-right: 22px !important; }}
      .h1 {{ font-size: 23px !important; }}
    }}
    a {{ color: {BRAND_GOLD_DARK}; }}
  </style>
</head>
<body style="margin:0;padding:0;background-color:{SURFACE_ALT};-webkit-font-smoothing:antialiased;">

  <div style="display:none;font-size:1px;color:{SURFACE_ALT};line-height:1px;max-height:0;max-width:0;opacity:0;overflow:hidden;">
    {body}
    &#8199;&#65279;&#847; &#8199;&#65279;&#847; &#8199;&#65279;&#847; &#8199;&#65279;&#847;
  </div>

  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
         style="background-color:{SURFACE_ALT};padding:28px 12px;">
    <tr>
      <td align="center">

        <table role="presentation" class="wrap" width="600" cellspacing="0" cellpadding="0" border="0"
               style="width:600px;max-width:600px;background:#ffffff;border-radius:16px;overflow:hidden;border:1px solid {BORDER};">

          <tr>
            <td style="background-color:{BRAND_BLACK};padding:28px 32px;" class="pad">
              <span style="display:inline-block;font-family:{font};font-size:22px;font-weight:700;color:{BRAND_GOLD};letter-spacing:0.5px;line-height:1;">
                Elizade
              </span>
              <span style="display:inline-block;font-family:{font};font-size:11px;font-weight:600;color:#FFFFFF;letter-spacing:4px;text-transform:uppercase;padding-left:8px;">
                Connect
              </span>
            </td>
          </tr>

          <tr><td style="height:4px;background-color:{BRAND_GOLD};font-size:0;line-height:0;">&nbsp;</td></tr>

          <tr>
            <td class="pad" style="padding:34px 32px 4px;font-family:{font};">
              <h1 class="h1" style="margin:0 0 14px;font-size:25px;line-height:1.25;font-weight:700;color:{BRAND_INK};">
                {title}
              </h1>
              <p style="margin:0 0 10px;font-size:14px;line-height:1.6;color:{TEXT_MUTED};">
                {greeting}
              </p>
              <p style="margin:0;font-size:15px;line-height:1.65;color:{BRAND_INK};">
                {body}
              </p>
            </td>
          </tr>
{detail_block}{cta_block}
          <tr>
            <td class="pad" style="padding:26px 32px 30px;font-family:{font};">
              <p style="margin:0;font-size:13px;line-height:1.6;color:{TEXT_FAINT};">
                You can also see this in the Elizade Connect app.
              </p>
            </td>
          </tr>

          <tr>
            <td class="pad" style="padding:22px 32px 26px;background-color:{SURFACE_ALT};border-top:1px solid {BORDER};font-family:{font};">
              <p style="margin:0 0 10px;font-size:13px;font-weight:600;color:{BRAND_INK};">
                Need help?
              </p>
              <p style="margin:0 0 14px;font-size:13px;line-height:1.7;color:{TEXT_MUTED};">
                <a href="mailto:{settings.support_email}" style="color:{BRAND_GOLD_DARK};text-decoration:underline;">{settings.support_email}</a>
                &nbsp;&#183;&nbsp;
                <a href="tel:{settings.support_phone.replace(' ', '')}" style="color:{BRAND_GOLD_DARK};text-decoration:underline;">{settings.support_phone}</a>
                &nbsp;&#183;&nbsp;
                <a href="{settings.support_url}" style="color:{BRAND_GOLD_DARK};text-decoration:underline;">elizade.net</a>
              </p>
              <p style="margin:0;font-size:11px;line-height:1.6;color:{TEXT_FAINT};">
                &copy; Elizade Nigeria Limited &#183; Authorised Distributor for Toyota, Jetour &amp; JAC<br />
                This is an automated message &#8212; please do not reply to this address.
              </p>
            </td>
          </tr>

        </table>

      </td>
    </tr>
  </table>
</body>
</html>"""
