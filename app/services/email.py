from abc import ABC, abstractmethod


class EmailService(ABC):
    @abstractmethod
    def send_otp(self, to_email: str, code: str, purpose: str) -> None:
        ...


class MockEmailService(EmailService):
    def send_otp(self, to_email: str, code: str, purpose: str) -> None:
        print(f"[EMAIL:MOCK] OTP to {to_email} ({purpose}): {code}")


email_service: EmailService = MockEmailService()
