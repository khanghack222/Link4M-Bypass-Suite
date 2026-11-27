#!/usr/bin/env python3
"""Local no-auth SOCKS5 that chains to an authenticated upstream SOCKS5.

Chrome cannot authenticate to a SOCKS5 proxy, but the public egress relay
requires credentials. This binds loopback, speaks SOCKS5 without auth, and
opens every connection through the upstream (RFC 1929 user/pass) instead.

    python3 chain_socks.py --listen 1083 \
        --upstream host:port --user l4m --password ... 
"""
from __future__ import annotations

import argparse
import asyncio
import socket
import struct

BUF = 64 * 1024


async def pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while True:
            chunk = await reader.read(BUF)
            if not chunk:
                break
            writer.write(chunk)
            await writer.drain()
    except (ConnectionError, asyncio.IncompleteReadError):
        pass
    finally:
        try:
            writer.close()
        except Exception:
            pass


async def read_addr(
    reader: asyncio.StreamReader, atyp: int
) -> tuple[int, bytes, str, int]:
    if atyp == 1:
        raw = await reader.readexactly(4)
        host = socket.inet_ntoa(raw)
    elif atyp == 3:
        length = (await reader.readexactly(1))[0]
        raw = await reader.readexactly(length)
        host = raw.decode("idna", "strict")
    elif atyp == 4:
        raw = await reader.readexactly(16)
        host = socket.inet_ntop(socket.AF_INET6, raw)
    else:
        raise ConnectionError("bad atyp")
    port = struct.unpack("!H", await reader.readexactly(2))[0]
    return atyp, raw, host, port


async def handle(reader, writer, upstream, user, password) -> None:
    try:
        version, nmethods = await reader.readexactly(2)
        await reader.readexactly(nmethods)
        writer.write(b"\x05\x00")
        await writer.drain()
        version, cmd, _rsv, _atyp = await reader.readexactly(4)
        if cmd != 1:
            writer.close()
            return
        _atyp, raw, host, port = await read_addr(reader, _atyp)

        try:
            up_r, up_w = await asyncio.wait_for(
                asyncio.open_connection(upstream[0], upstream[1]), timeout=20
            )
        except Exception:
            writer.close()
            return

        # Greeting carries nmethods *followed by* that many method bytes; the
        # earlier version sent only the header and the relay waited forever.
        up_w.write(bytes([0x05, 0x02, 0x00, 0x02]))
        await up_w.drain()
        method = (await up_r.readexactly(2))[1]
        if method != 0x02:
            up_w.close()
            writer.close()
            return
        u = user.encode()
        p = password.encode()
        up_w.write(bytes([0x01, len(u)]) + u + bytes([len(p)]) + p)
        await up_w.drain()
        if (await up_r.readexactly(2))[1] != 0x00:
            up_w.close()
            writer.close()
            return

        # CONNECT re-serializes the address: a domain target needs its length
        # byte back, which read_addr strips for the string.
        if _atyp == 3:
            addr = bytes([len(raw)]) + raw
        else:
            addr = raw
        up_w.write(bytes([0x05, 0x01, 0x00, _atyp]) + addr + struct.pack("!H", port))
        await up_w.drain()
        reply = await up_r.readexactly(4)
        if reply[1] != 0x00:
            up_w.close()
            writer.close()
            return
        await read_addr(up_r, reply[3])  # bound address, discarded

        writer.write(b"\x05\x00\x00\x01" + b"\x00" * 6)
        await writer.drain()
        await asyncio.gather(pipe(reader, up_w), pipe(up_r, writer))
    except (asyncio.IncompleteReadError, ConnectionError, OSError):
        try:
            writer.close()
        except Exception:
            pass


async def main_async(listen: int, upstream, user, password) -> None:
    server = await asyncio.start_server(
        lambda r, w: handle(r, w, upstream, user, password), "127.0.0.1", listen
    )
    print(f"chain socks5 on 127.0.0.1:{listen} -> {upstream[0]}:{upstream[1]}", flush=True)
    async with server:
        await server.serve_forever()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--listen", type=int, default=1083)
    ap.add_argument("--upstream", required=True)
    ap.add_argument("--user", required=True)
    ap.add_argument("--password", required=True)
    args = ap.parse_args()
    host, _, port = args.upstream.rpartition(":")
    asyncio.run(main_async(args.listen, (host, int(port)), args.user, args.password))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
