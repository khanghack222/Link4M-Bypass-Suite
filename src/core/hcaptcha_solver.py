"""hCaptcha relay & solver integration using DoesCap."""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger("hcaptcha_solver")


def solve_hcaptcha(
    sitekey: str,
    *,
    host: str = "127.0.0.1",
    port: Optional[int] = None,
    timeout: int = 120,
    auto_open_browser: bool = True,
    theme: str = "dark",
    title: str = "Link4M Sponsor - hCaptcha Verification",
) -> Optional[str]:
    """Solve an hCaptcha challenge using DoesCap.

    Spawns a lightweight local HTTP server and renders the challenge in a native
    browser (desktop, mobile LAN, or Termux) with zero headless CPU/RAM lag.

    Args:
        sitekey: The hCaptcha sitekey from the target page.
        host: Host address to bind the relay server (default 127.0.0.1).
        port: Port to bind (auto-selected if None).
        timeout: Maximum seconds to wait for user/browser solve.
        auto_open_browser: Whether to automatically launch the default browser.
        theme: UI theme ('dark' or 'light').
        title: Title of the verification page.

    Returns:
        The solved hCaptcha response token (str) if successful, None otherwise.
    """
    try:
        from doescap import DoesCap

        orchestrator = DoesCap(
            host=host,
            port=port,
            timeout=timeout,
            auto_open_browser=auto_open_browser,
            theme=theme,
            title=title,
        )
        logger.info(f"[*] Starting DoesCap relay for sitekey={sitekey}")
        result = orchestrator.solve(sitekey)
        if result and str(result):
            token = str(result)
            logger.info(f"[+] DoesCap solved successfully (token len={len(token)})")
            return token
        logger.warning("[-] DoesCap returned empty result")
        return None
    except ImportError:
        logger.error("[-] doescap library is not installed. Run `pip install doescap`.")
        return None
    except Exception as e:
        logger.error(f"[-] DoesCap error: {e}")
        return None
