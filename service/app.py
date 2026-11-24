# -*- coding: utf-8 -*-
"""API vượt link kiểu vnbypass.com: dán link khoá -> nhận link đích.

    uvicorn service.app:app --host 0.0.0.0 --port 8080
    # hoặc
    python -m service
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from .config import CFG, clear_proxy_env
from .providers import fast_decode, normalize, parse, supported
from .store import Store
from .worker import WorkerPool

REPO = os.path.expanduser("~/Link4M-Bypass-Suite")
os.makedirs(os.path.dirname(CFG.LOG_PATH) or ".", exist_ok=True)


def log(*a) -> None:
    line = time.strftime("%H:%M:%S ") + " ".join(str(x) for x in a)
    print(line, flush=True)
    try:
        with open(CFG.LOG_PATH, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


_store: Optional[Store] = None
_pool: Optional[WorkerPool] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _store, _pool
    if CFG.CLEAR_PROXY:
        clear_proxy_env()
    _store = Store(CFG.DB_PATH)
    _pool = WorkerPool(_store, log)
    await _pool.start()
    log(f"service lên — workers={CFG.WORKERS} cache_ttl={CFG.CACHE_TTL}s "
        f"db={CFG.DB_PATH} auth={'on' if CFG.API_KEY else 'off'}")
    try:
        yield
    finally:
        await _pool.stop()
        _store.close()


app = FastAPI(title="Link Bypass Service", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=False,
    allow_methods=["*"], allow_headers=["*"],
)


def require_key(x_api_key: Optional[str] = Header(None),
                key: Optional[str] = Query(None)) -> None:
    if not CFG.API_KEY:
        return
    if (x_api_key or key) != CFG.API_KEY:
        raise HTTPException(status_code=401, detail="API key không đúng")


class BypassReq(BaseModel):
    url: str = Field(..., description="Link khoá cần vượt")
    wait: bool = Field(False, description="Chờ tới khi xong rồi trả link đích")
    timeout: int = Field(240, ge=5, le=600, description="Giây chờ tối đa (chế độ wait)")


class BatchReq(BaseModel):
    urls: list[str] = Field(..., max_length=50)
    wait: bool = Field(False)
    timeout: int = Field(240, ge=5, le=600)


def _result(status: str, url: str, **kw) -> dict:
    out = {"status": status, "url": url, "destination_url": None,
           "provider": None, "cached": False, "elapsed_ms": 0.0, "job_id": None}
    out.update(kw)
    return out


@app.get("/")
def root():
    return {"service": "Link Bypass Service", "status": "online",
            "supported": supported(), "docs": "/docs",
            "endpoints": ["POST /api/v1/bypass", "GET /api/v1/bypass",
                          "GET /api/v1/jobs/{id}", "POST /api/v1/batch",
                          "GET /api/v1/stats", "GET /health"]}


@app.get("/health")
def health():
    st = _store.stats() if _store else {}
    return {"status": "ok", "queued": _pool.queued if _pool else 0,
            "inflight": _pool.inflight if _pool else 0,
            "workers": CFG.WORKERS, **st}


@app.get("/api/v1/stats")
def stats(limit: int = Query(15, ge=1, le=100)):
    return {"stats": _store.stats(), "queued": _pool.queued,
            "inflight": _pool.inflight, "recent": _store.recent(limit)}


@app.get("/api/v1/supported")
def supported_list():
    return {"supported": supported()}


_UI = """<!DOCTYPE html>
<html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Vượt link</title>
<style>
:root{--bg:#0f1115;--card:#181b22;--fg:#e8eaed;--dim:#8b93a1;--acc:#4c8dff;--ok:#37c871;--err:#ff5c5c}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
font:15px/1.5 system-ui,Segoe UI,Roboto,sans-serif;display:flex;justify-content:center;padding:40px 16px}
.w{width:100%;max-width:680px}h1{font-size:26px;margin:0 0 6px}p.s{color:var(--dim);margin:0 0 22px}
.box{background:var(--card);border:1px solid #23262e;border-radius:14px;padding:18px}
input,button{font:inherit}input{width:100%;padding:13px 14px;border-radius:10px;border:1px solid #2c313c;
background:#0c0e12;color:var(--fg)}button{margin-top:12px;width:100%;padding:13px;border:0;border-radius:10px;
background:var(--acc);color:#fff;font-weight:600;cursor:pointer}button:disabled{opacity:.5;cursor:default}
.out{margin-top:16px;padding:13px 14px;border-radius:10px;background:#0c0e12;border:1px solid #23262e;
word-break:break-all;display:none}.out.ok{border-color:var(--ok)}.out.err{border-color:var(--err);color:var(--err)}
a{color:var(--acc)}.meta{color:var(--dim);font-size:13px;margin-top:8px}
.h{margin-top:22px}.h h3{font-size:14px;color:var(--dim);font-weight:600;text-transform:uppercase;letter-spacing:.5px}
li{margin:6px 0;color:var(--dim);font-size:14px;word-break:break-all}
</style></head><body><div class="w">
<h1>Vượt link</h1><p class="s">Dán link khoá, nhận link đích. Hỗ trợ: link4m.</p>
<div class="box">
<input id="u" placeholder="https://link4m.net/go/xxxxx" autocomplete="off">
<button id="b">Vượt link</button>
<div class="out" id="o"></div>
</div>
<div class="h"><h3>Gần đây</h3><ol id="hist"></ol></div>
<script>
const $=s=>document.querySelector(s),KEY="l4m_hist";
function hist(){try{return JSON.parse(localStorage.getItem(KEY))||[]}catch(e){return[]}}
function save(u,d){const h=hist().filter(x=>x.u!==u);h.unshift({u,d});localStorage.setItem(KEY,JSON.stringify(h.slice(0,8)));draw()}
function draw(){const el=$("#hist");el.innerHTML="";hist().forEach(x=>{const li=document.createElement("li");
li.innerHTML=document.createTextNode(x.d+" ");const a=document.createElement("a");a.href=x.d;a.textContent="↗";li.appendChild(a);el.appendChild(li)})}
async function go(){const u=$("#u").value.trim();if(!u)return;const b=$("#b"),o=$("#o");
b.disabled=true;o.className="out";o.style.display="block";o.textContent="Đang vượt... (có thể tới ~3 phút)";
const t=Date.now();
try{const r=await fetch("/api/v1/bypass?wait=1&timeout=300&url="+encodeURIComponent(u));const j=await r.json();
if(j.status==="success"){o.className="out ok";const s=((Date.now()-t)/1000).toFixed(2);
o.innerHTML='<b>'+j.destination_url+'</b><div class="meta">'+(j.cached?"cache":"mới")+' · '+s+'s</div>';
save(u,j.destination_url)}else{o.className="out err";o.textContent="Lỗi: "+(j.detail||j.error||j.status)}}catch(e){
o.className="out err";o.textContent="Lỗi mạng: "+e}b.disabled=false}
$("#b").onclick=go;$("#u").addEventListener("keydown",e=>{if(e.key==="Enter")go()});draw();
</script></div></body></html>"""


@app.get("/ui", response_class=HTMLResponse)
def ui():
    return HTMLResponse(_UI)


async def _do_bypass(url: str, wait: bool, timeout: int, client: str) -> dict:
    url = normalize(url)
    t0 = time.perf_counter()

    # 1) fast-path: giải được bằng chuỗi, không cần browser
    quick = fast_decode(url)
    if quick:
        return _result("success", url, destination_url=quick, provider="decode",
                       elapsed_ms=round((time.perf_counter() - t0) * 1000, 1))

    m = parse(url)
    if not m:
        raise HTTPException(status_code=400,
                            detail=f"Không nhận diện được nhà cung cấp. Hỗ trợ: {supported()}")

    # 2) cache
    if CFG.CACHE_ENABLED:
        hit = _store.cache_get(m.provider, m.key, CFG.CACHE_TTL)
        if hit:
            return _result("success", url, destination_url=hit, provider=m.provider,
                           cached=True, elapsed_ms=round((time.perf_counter() - t0) * 1000, 1))

    # 3) xếp hàng
    jid = _store.create_job(url, m.provider, m.key, client)
    if not _pool.submit(jid):
        _store.set_status(jid, "error", error="hàng đợi đầy")
        raise HTTPException(status_code=429, detail="Hàng đợi đầy, thử lại sau")

    if not wait:
        return _result("queued", url, provider=m.provider, job_id=jid,
                       poll=f"/api/v1/jobs/{jid}")

    job = await _pool.wait(jid, timeout)
    return _from_job(job, url, m.provider, round((time.perf_counter() - t0) * 1000, 1))


def _from_job(job: Optional[dict], url: str, provider: str, elapsed_ms: float) -> dict:
    if not job:
        return _result("timeout", url, provider=provider, elapsed_ms=elapsed_ms)
    jid = job["id"]
    if job["status"] == "success":
        return _result("success", url, destination_url=job["destination"],
                       provider=provider, job_id=jid, elapsed_ms=elapsed_ms,
                       cached=bool(job.get("cached")))
    if job["status"] in ("queued", "running"):
        return _result("timeout", url, provider=provider, job_id=jid, elapsed_ms=elapsed_ms)
    return _result("error", url, provider=provider, job_id=jid,
                   elapsed_ms=elapsed_ms, error=job.get("error"))


@app.post("/api/v1/bypass")
async def bypass_post(req: BypassReq, client: str = Depends(require_key),
                      x_client_id: Optional[str] = Header(None)):
    return await _do_bypass(req.url, req.wait, req.timeout, x_client_id or "api")


@app.get("/api/v1/bypass")
async def bypass_get(url: str = Query(..., description="Link khoá"),
                     wait: bool = Query(False),
                     timeout: int = Query(240, ge=5, le=600),
                     _: None = Depends(require_key),
                     x_client_id: Optional[str] = Header(None)):
    return await _do_bypass(url, wait, timeout, x_client_id or "api")


@app.get("/api/v1/jobs/{job_id}")
def job_get(job_id: str, _: None = Depends(require_key)):
    job = _store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Không có job này")
    return job


@app.post("/api/v1/batch")
async def batch(req: BatchReq, _: None = Depends(require_key),
                x_client_id: Optional[str] = Header(None)):
    out = []
    for u in req.urls:
        try:
            out.append(await _do_bypass(u, req.wait, req.timeout, x_client_id or "batch"))
        except HTTPException as e:
            out.append(_result("error", u, error=e.detail))
    return {"count": len(out), "results": out}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("service.app:app", host=CFG.HOST, port=CFG.PORT, workers=1)
