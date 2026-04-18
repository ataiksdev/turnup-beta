import httpx
from app.config import settings


async def send_otp_sms(phone: str, code: str) -> None:
    if settings.twilio_account_sid and settings.twilio_auth_token:
        url = f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}/Messages.json"
        async with httpx.AsyncClient() as client:
            await client.post(
                url,
                data={"From": settings.twilio_phone_number, "To": phone, "Body": f"Your Turnup code: {code}"},
                auth=(settings.twilio_account_sid, settings.twilio_auth_token),
            )
    else:
        print(f"[DEV SMS] OTP for {phone}: {code}")
