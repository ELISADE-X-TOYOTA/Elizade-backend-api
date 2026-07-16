from app.core.config import get_settings


def _otp_purpose_label(purpose: str) -> str:
    if purpose == "login":
        return "sign in to your admin portal"
    if purpose == "register":
        return "complete your registration"
    return "verify your identity"


def build_otp_plain_text(*, code: str, purpose: str) -> str:
    settings = get_settings()
    purpose_label = _otp_purpose_label(purpose)
    return (
        f"Your Elizade Connect verification code is {code}.\n\n"
        f"Use this code to {purpose_label}. "
        f"It expires in {settings.otp_expire_minutes} minutes.\n\n"
        "If you did not request this code, you can safely ignore this email.\n\n"
        "— Elizade Nigeria Limited"
    )


def build_otp_html(*, code: str, purpose: str) -> str:
    settings = get_settings()
    purpose_label = _otp_purpose_label(purpose)
    minutes = settings.otp_expire_minutes

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Elizade Connect verification code</title>
</head>
<body style="margin:0;padding:0;background-color:#f4f4f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color:#f4f4f5;padding:32px 16px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:620px;background:#ffffff;border-radius:20px;overflow:hidden;box-shadow:0 18px 48px rgba(15,23,42,0.12);">
          <tr>
            <td style="height:6px;background:linear-gradient(90deg,#c8102e 0%,#ffcf0f 50%,#c8102e 100%);"></td>
          </tr>
          <tr>
            <td style="padding:36px 36px 28px;">
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                <tr>
                  <td>
                    <p style="margin:0 0 10px;font-size:11px;font-weight:700;letter-spacing:0.18em;text-transform:uppercase;color:#c8102e;">
                      Elizade Connect
                    </p>
                    <h1 style="margin:0 0 12px;font-size:28px;line-height:1.2;font-weight:800;color:#111827;">
                      Your verification code
                    </h1>
                    <p style="margin:0;font-size:15px;line-height:1.6;color:#6b7280;">
                      Use the code below to {purpose_label}. For your security, it expires in {minutes} minutes.
                    </p>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <tr>
            <td style="padding:0 36px 32px;">
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#fff8e6;border:1px solid #fde68a;border-radius:18px;">
                <tr>
                  <td style="padding:28px 24px;text-align:center;">
                    <p style="margin:0 0 10px;font-size:12px;font-weight:600;letter-spacing:0.14em;text-transform:uppercase;color:#92400e;">
                      One-time code
                    </p>
                    <p style="margin:0;font-size:40px;line-height:1;font-weight:800;letter-spacing:0.28em;color:#111827;">
                      {code}
                    </p>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <tr>
            <td style="padding:0 36px 36px;">
              <p style="margin:0 0 14px;font-size:14px;line-height:1.6;color:#6b7280;">
                Enter this code on the sign-in screen to continue. Never share it with anyone — Elizade staff will never ask for your verification code.
              </p>
              <p style="margin:0;font-size:13px;line-height:1.6;color:#9ca3af;">
                If you did not request this code, you can safely ignore this email.
              </p>
            </td>
          </tr>
          <tr>
            <td style="padding:20px 36px 28px;border-top:1px solid #f3f4f6;background:#fafafa;">
              <p style="margin:0;font-size:12px;line-height:1.5;color:#9ca3af;">
                © Elizade Nigeria Limited · Toyota dealership operations portal
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""
