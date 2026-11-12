"""Uso:
    uv run python -m client                              # menu (local e online)
    uv run python -m client --quick ravena toro          # partida direta: você vs bot
    uv run python -m client --server 192.168.0.5         # entra direto numa sala online
"""

import argparse

import arcade


def main() -> None:
    ap = argparse.ArgumentParser(description="Cliente do Lendas do Ringue")
    ap.add_argument("--quick", nargs=2, metavar=("VOCE", "BOT"), default=None,
                    help="pula o menu: 1P vs 1 bot com estes lutadores")
    ap.add_argument("--stage", default="coliseu")
    ap.add_argument("--bot", default="medio", choices=["facil", "medio", "dificil"])
    ap.add_argument("--server", default=None, help="endereço da sala (IP, IP:porta, link ngrok)")
    ap.add_argument("--name", default=None)
    ap.add_argument("--senha", default="")
    args = ap.parse_args()

    window = arcade.Window(1280, 720, "Lendas do Ringue", resizable=True, vsync=True)
    window.set_minimum_size(960, 540)

    from client.drivers import LocalDriver
    from client.game_view import GameView
    from client.menu_view import MatchSetup, MenuView

    if args.name:
        MenuView._name = args.name[:16]
    if args.quick:
        setup = MatchSetup(1, 1, list(args.quick), args.bot, args.stage)
        window.show_view(GameView(LocalDriver(setup)))
    elif args.server:
        from client.lobby_view import LobbyView
        from client.net import NetClient
        from client.tunnel import normalize_server_url

        net = NetClient(normalize_server_url(args.server), MenuView._name, password=args.senha)
        try:
            net.connect()
            window.show_view(LobbyView(net))
        except Exception as e:  # noqa: BLE001
            window.show_view(MenuView(error=f"Não conectou: {e}"))
    else:
        window.show_view(MenuView())
    arcade.run()


if __name__ == "__main__":
    main()
