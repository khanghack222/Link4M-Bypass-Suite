import sys
import time
import io
import re
import urllib.request
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from patchright.sync_api import sync_playwright
import speech_recognition as sr
from pydub import AudioSegment

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    print("[*] Loading target Link4M page...", flush=True)
    page.goto('https://link4m.net/go/68pw167Y', timeout=20000)
    page.wait_for_timeout(3500)
    
    # 1. Click anchor 0
    anchors = page.locator('iframe[src*="recaptcha/api2/anchor"]').all()
    if not anchors:
        print("[-] No anchors found!")
        sys.exit(1)
        
    a = anchors[0]
    cf = a.content_frame
    chk = cf.locator('#recaptcha-anchor')
    chk.click(force=True)
    time.sleep(2)
    
    # 2. Find matching bframe
    bf = None
    for f in page.frames:
        if 'bframe' in f.url and f.locator('#recaptcha-audio-button').count() > 0:
            bf = f
            break
            
    if not bf:
        print("[-] No active bframe found!")
        sys.exit(1)
        
    print("[+] Found active bframe! Clicking audio challenge button...", flush=True)
    clicked = bf.evaluate("""() => {
        const btn = document.querySelector('#recaptcha-audio-button');
        if (btn) {
            btn.click();
            return true;
        }
        return false;
    }""")
    print(f"[+] Audio button clicked: {clicked}", flush=True)
    time.sleep(2.0)
    
    # 3. Check what bframe content is
    bframe_text = bf.evaluate("() => document.body ? document.body.innerText : ''")
    print(f"[*] BFrame Text:\n{bframe_text[:300]}\n", flush=True)
    
    # 4. Check for download URL
    audio_url = bf.evaluate("""() => {
        const a = document.querySelector('.rc-audiochallenge-tdownload-link') ||
                  document.querySelector('a.rc-audiochallenge-download-link') ||
                  document.querySelector('a[href*="audio.mp3"]');
        return a ? a.href : null;
    }""")
    print(f"[*] Download URL: {audio_url}", flush=True)
    
    if audio_url:
        print("[+] Fetching audio MP3 stream...", flush=True)
        t_dl = time.perf_counter()
        req = urllib.request.Request(audio_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            audio_bytes = resp.read()
        print(f"[+] Downloaded {len(audio_bytes)} bytes in {round((time.perf_counter() - t_dl)*1000)}ms", flush=True)
        
        # In-memory WAV conversion
        t_trans = time.perf_counter()
        seg = AudioSegment.from_file(io.BytesIO(audio_bytes), format='mp3')
        seg = seg.set_frame_rate(16000).set_channels(1)
        wav_buf = io.BytesIO()
        seg.export(wav_buf, format='wav')
        
        # SpeechRecognition Google
        r = sr.Recognizer()
        with sr.AudioFile(io.BytesIO(wav_buf.getvalue())) as source:
            audio_data = r.record(source)
        text = r.recognize_google(audio_data, language='en-US')
        trans_ms = round((time.perf_counter() - t_trans)*1000)
        print(f"🎉 GOOGLE SPEECH TRANSCRIBED IN {trans_ms}ms: '{text}'", flush=True)
        
        # Fill response & click verify
        bf.evaluate("""(ans) => {
            const input = document.querySelector('#audio-response');
            if (input) {
                input.value = ans;
                input.dispatchEvent(new Event('input', { bubbles: true }));
                input.dispatchEvent(new Event('change', { bubbles: true }));
            }
            const verifyBtn = document.querySelector('#recaptcha-verify-button');
            if (verifyBtn) verifyBtn.click();
        }""", text)
        time.sleep(2.5)
        
        # Check token
        is_checked = chk.get_attribute("aria-checked")
        print(f"[*] reCAPTCHA checked status: {is_checked}", flush=True)
        token = page.evaluate("() => { for (const el of document.querySelectorAll('[name=\"g-recaptcha-response\"]')) { if (el.value && el.value.length > 20) return el.value; } return ''; }")
        print(f"[+] Token length: {len(token)}", flush=True)
        if token:
            print(f"🎉 BINGO! TOKEN RECEIVED: {token[:60]}...", flush=True)
    
    b.close()
