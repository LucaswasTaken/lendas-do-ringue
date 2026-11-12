"""Uso:
    uv run python -m server                     # sala na porta 8766
    uv run python -m server --ngrok             # + link público para os amigos
    uv run python -m server --senha dragao      # só entra quem souber a senha
    uv run python -m server --fake-lag 120      # simula 120 ms de ping (teste)
"""

import argparse
import asyncio
import logging
import socket

from server.game_server import GameServer
from shared.constants import DEFAULT_PORT


def _lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def main() -> None:
    ap = argparse.ArgumentParser(description="Servidor do Lendas do Ringue")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--senha", default=None)
    ap.add_argument("--ngrok", action="store_true", help="abre um túnel do ngrok")
    ap.add_argument("--fake-lag", type=int, default=0, metavar="MS",
                    help="atraso artificial ida+volta, para testar a rede")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")
    proc = None

    async def run():
        nonlocal proc
        ready = asyncio.Event()
        server = GameServer(password=args.senha, fake_lag_ms=args.fake_lag)
        task = asyncio.create_task(server.run(args.host, args.port, ready))
        await ready.wait()
        public, note = None, ""
        if args.ngrok:
            from server import ngrok
            proc, public, note = await asyncio.to_thread(ngrok.start, args.port)
        print("=" * 60)
        print(" LENDAS DO RINGUE - servidor no ar")
        print(f"  Neste PC:      127.0.0.1:{args.port}")
        print(f"  Rede local:    {_lan_ip()}:{args.port}")
        if public:
            print(f"  Internet:      {public}")
        if note:
            print(f"  Aviso: {note}")
        if args.fake_lag:
            print(f"  Lag artificial: {args.fake_lag} ms")
        print("  Quem entrar primeiro vira o anfitrião. Ctrl+C encerra.")
        print("=" * 60, flush=True)
        await task

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
    finally:
        if proc is not None:
            proc.terminate()


if __name__ == "__main__":
    main()
