#!/usr/bin/env python3
"""Minimal SOCKS5 server for the egress tunnel.

Runs in user space so it works on a box without sudo. Only CONNECT is
implemented (that is all Chrome needs), IPv4/IPv6/domain targets. Optional
RFC 1929 username/password auth: the listener is published through a public
SSH relay, so an open proxy would hand strangers the home IP.

    python3 socks5.py --port 1080 --user l4m --password ...
"""

from __future__ import annotations

import argparse
import os
import asyncio
import ipaddress
import hmac
import socket
import struct

MAX_HEADER = 512
BUF = 64 * 1024

USER = ""
PASSWORD = ""


def same(left: bytes, right: bytes) -> bool:
    return hmac.compare_digest(left, right)


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


async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        head = await reader.readexactly(2)
        version, nmethods = head
        if version != 5:
            writer.close()
            return
        methods = await reader.readexactly(nmethods)
        want = 0x02 if USER else 0x00
        if want not in methods:
            writer.write(b"\x05\xff")
            await writer.drain()
            writer.close()
            return
        writer.write(bytes([0x05, want]))
        await writer.drain()
        if USER:
            auth = await reader.readexactly(2)
            if auth[0] != 0x01:
                writer.close()
                return
            user = await reader.readexactly(auth[1])
            pass_len = (await reader.readexactly(1))[0]
            password = await reader.readexactly(pass_len)
            if not (same(user, USER.encode()) and same(password, PASSWORD.encode())):
                writer.write(b"\x01\x01")
                await writer.drain()
                writer.close()
                return
            writer.write(b"\x01\x00")
            await writer.drain()

        req = await reader.readexactly(4)
        ver, cmd, _rsv, atyp = req
        if ver != 5 or cmd != 1:
            writer.write(b"\x05\x07\x00\x01" + b"\x00" * 6)
            await writer.drain()
            writer.close()
            return

        if atyp == 1:
            host = socket.inet_ntoa(await reader.readexactly(4))
        elif atyp == 3:
            length = (await reader.readexactly(1))[0]
            host = (await reader.readexactly(length)).decode("idna", "strict")
        elif atyp == 4:
            host = socket.inet_ntop(socket.AF_INET6, await reader.readexactly(16))
        else:
            writer.close()
            return
        port = struct.unpack("!H", await reader.readexactly(2))[0]

        try:
            remote_reader, remote_writer = await asyncio.wait_for(
                asyncio.open_connection(host, port), timeout=15
            )
        except Exception:
            writer.write(b"\x05\x05\x00\x01" + b"\x00" * 6)
            await writer.drain()
            writer.close()
            return

        writer.write(b"\x05\x00\x00\x01" + b"\x00" * 6)
        await writer.drain()
        await asyncio.gather(
            pipe(reader, remote_writer),
            pipe(remote_reader, writer),
        )
    except (asyncio.IncompleteReadError, ConnectionError):
        try:
            writer.close()
        except Exception:
            pass


async def main_async(port: int, host: str) -> None:
    server = await asyncio.start_server(handle, host, port, backlog=128)
    print(f"socks5 listening on {host}:{port}", flush=True)
    async with server:
        await server.serve_forever()


def main() -> int:
    global USER, PASSWORD
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=1080)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--user", default=os.environ.get("EGRESS_USER", ""))
    parser.add_argument("--password", default=os.environ.get("EGRESS_PASSWORD", ""))
    args = parser.parse_args()
    USER = args.user
    PASSWORD = args.password
    if USER:
        print(f"socks5 auth enabled for user {USER}", flush=True)
    try:
        asyncio.run(main_async(args.port, args.host))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
