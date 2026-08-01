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
