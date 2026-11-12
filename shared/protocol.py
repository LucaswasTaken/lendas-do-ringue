"""Mensagens entre cliente e servidor (msgpack sobre WebSocket).

Fluxo: hello -> welcome -> lobby... -> game_start -> snapshot... -> (fim) lobby...

Cliente -> servidor:
    hello   {name, token, version, password}  token permite reconectar na mesma vaga
    leave   {}
    pick    {fighter}             sala: escolher lutador
    ready   {ready}               sala: pronto / não pronto
    stage   {stage}               sala (anfitrião)
    bots    {level}               sala (anfitrião): facil | medio | dificil
    add_bot {}                    sala (anfitrião)
    remove_bot {}                 sala (anfitrião): tira o último bot
    start   {}                    sala (anfitrião)
    input   {inputs: [[seq, bits], ...]}   últimos frames (redundância contra perda)
Servidor -> cliente:
    welcome {player_id, token, phase}
    lobby   {phase, host, stage, bot_level, can_start, players: [...], notice}
    game_start {stage, stocks, seconds, roster: [{pid, fighter, name, bot}]}
    snapshot {f, over, winner, fighters: [estado completo], events, ack}
             ack = último seq de input aplicado para este jogador (predição)
    error   {reason}
"""

import msgpack

PROTOCOL_VERSION = 1

HELLO = "hello"
LEAVE = "leave"
PICK = "pick"
READY = "ready"
STAGE = "stage"
BOTS = "bots"
ADD_BOT = "add_bot"
REMOVE_BOT = "remove_bot"
START = "start"
INPUT = "input"
WELCOME = "welcome"
LOBBY = "lobby"
GAME_START = "game_start"
SNAPSHOT = "snapshot"
ERROR = "error"


def encode(msg_type: str, **fields) -> bytes:
    return msgpack.packb({"t": msg_type, **fields}, use_bin_type=True)


def decode(data: bytes) -> dict:
    msg = msgpack.unpackb(data, raw=False)
    if not isinstance(msg, dict) or "t" not in msg:
        raise ValueError("mensagem inválida")
    return msg
