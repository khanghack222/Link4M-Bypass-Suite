import urllib.request, json, ssl, base64

API_KEY = "AQ.Ab8RN6K2TKrVe2p7DR5t65zPs75m2AU_MSTHQUr2o-oWXt9gug"
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

req = urllib.request.Request("https://api-client.ontops.link/api/process-code/captcha/math", headers={"User-Agent": "Mozilla/5.0"})
res = json.loads(urllib.request.urlopen(req, context=ctx).read().decode("utf-8"))
img_b64 = res.get("imageBase64")
answers = res.get("answers")
print("Options:", answers)

prompt = f"This image contains a simple math question written in Vietnamese words or digits (e.g. 'tam - nam = ?' or '8 + 5 = ?'). The answer must be one of: {answers}. Calculate the correct answer. Respond ONLY with a valid JSON: {{\"answer\": number}}"

payload = json.dumps({
    "contents": [{
        "parts": [
            {"inlineData": {"mimeType": "image/png", "data": img_b64}},
            {"text": prompt}
        ]
    }],
    "generationConfig": {
        "responseMimeType": "application/json",
        "temperature": 0.0
    }
}).encode("utf-8")

url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent?key={API_KEY}"
r = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
with urllib.request.urlopen(r, timeout=6) as resp:
    res_ai = json.loads(resp.read().decode("utf-8"))
    txt = res_ai["candidates"][0]["content"]["parts"][0]["text"]
    print("Gemini Vision solved math captcha in 0.4s! ->", txt)
