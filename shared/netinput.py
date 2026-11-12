"""Fila de inputs de um jogador no servidor: 1 input por tick, em ordem de seq.

O cliente manda cada frame com um número de sequência (e repete os últimos N para
aguentar perda de pacote). O servidor consome um por tick; se faltar, repete o último
(sem criar nova "borda" de botão). Se o cliente adiantar demais, descarta os mais velhos
para a latência não acumular, guardando os botões de ação apertados neles.
"""

from __future__ import annotations

from shared import constants as C
from shared import inputs as I

ACTION = I.JUMP | I.LIGHT | I.HEAVY | I.DODGE


class InputQueue:
    def __init__(self) -> None:
        self.pending: dict[int, int] = {}
        self.ack: int | None = None  # último seq aplicado (None = ainda não sincronizou)
        self.last = 0

    def reset(self) -> None:
        self.pending.clear()
        self.ack = None
        self.last = 0

    def push(self, entries) -> None:
        for seq, bits in entries:
            seq, bits = int(seq), int(bits)
            if self.ack is None:
                self.ack = seq - 1
            if seq > self.ack:
                self.pending[seq] = bits

    def pop(self) -> int:
        carry = 0
        while len(self.pending) > C.MAX_INPUT_QUEUE:
            s = min(self.pending)
            carry |= self.pending.pop(s) & ACTION
            self.ack = s
        if self.ack is not None and self.pending:
            nxt = self.ack + 1
            if nxt not in self.pending:  # buraco maior que a redundância: pula para o próximo
                nxt = min(self.pending)
            bits = self.pending.pop(nxt)
            self.ack = nxt
            self.last = bits | carry
            return self.last
        return self.last
