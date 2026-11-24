# -*- coding: utf-8 -*-
"""Chạy service: python -m service"""
import uvicorn

from .config import CFG

if __name__ == "__main__":
    uvicorn.run("service.app:app", host=CFG.HOST, port=CFG.PORT,
                workers=1, log_level="info")
