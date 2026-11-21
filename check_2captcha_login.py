import requests
import re

s = requests.Session()
s.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
})
r = s.get("https://2captcha.com/auth/login")
csrf = re.findall(r'name="_token" value="([^"]+)"', r.text)
print("CSRF token:", csrf)

# Check Cloudflare or Turnstile or Captcha on login
has_turnstile = "challenges.cloudflare.com" in r.text or "cf-turnstile" in r.text
has_recaptcha = "recaptcha" in r.text
print("Has Turnstile:", has_turnstile)
print("Has reCAPTCHA:", has_recaptcha)
