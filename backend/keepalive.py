import os
import time
import logging
import threading
import urllib.request

logger = logging.getLogger('keepalive')

_keepalive_started = False
_keepalive_lock = threading.Lock()


def start_keepalive(interval_seconds: int = 600):
    """
    Pings the Render external URL every `interval_seconds` (default: 10 mins)
    to prevent Render Free tier from spinning down due to inactivity (15 min limit).
    """
    global _keepalive_started
    with _keepalive_lock:
        if _keepalive_started:
            return
        _keepalive_started = True

    external_url = (
        os.getenv('RENDER_EXTERNAL_URL') or
        os.getenv('KEEP_ALIVE_URL') or
        os.getenv('APP_URL') or
        ''
    ).strip().rstrip('/')

    if not external_url:
        logger.info("Keepalive disabled: No RENDER_EXTERNAL_URL or KEEP_ALIVE_URL environment variable found.")
        return

    if 'localhost' in external_url or '127.0.0.1' in external_url:
        logger.info("Keepalive disabled for local address: %s", external_url)
        return

    target_url = f"{external_url}/api/health"

    def _ping_loop():
        # Wait 45 seconds after process start so Gunicorn/Flask is fully accepting traffic
        time.sleep(45)
        logger.info("Render free-tier keepalive worker active -> target: %s (every %ds)", target_url, interval_seconds)
        while True:
            try:
                req = urllib.request.Request(
                    target_url,
                    headers={'User-Agent': 'StockManagementKeepalive/1.0'}
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    if resp.status == 200:
                        logger.info("Keepalive ping successful -> %s [200 OK]", target_url)
                    else:
                        logger.warning("Keepalive ping returned status %d", resp.status)
            except Exception as e:
                logger.warning("Keepalive ping notice: %s", e)
            time.sleep(interval_seconds)

    thread = threading.Thread(target=_ping_loop, daemon=True, name="RenderKeepaliveThread")
    thread.start()
