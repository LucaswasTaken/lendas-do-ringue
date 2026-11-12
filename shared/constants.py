"""Constantes globais da simulação. Unidades: pixels, segundos, frames (1 frame = 1 tick)."""

TICK_RATE = 60  # luta precisa de mais resolução que os 30 Hz do MOBA
TICK_DT = 1.0 / TICK_RATE
DEFAULT_PORT = 8766
MAX_PLAYERS = 4

# Rede
SNAPSHOT_EVERY = 2  # 1 snapshot a cada 2 ticks (30 Hz)
INPUT_REDUNDANCY = 4  # cada pacote de input repete os últimos N frames
MAX_INPUT_QUEUE = 6  # se o cliente adiantar mais que isso, o servidor descarta os mais velhos
INTERP_FRAMES = 6  # os outros lutadores são desenhados ~100 ms no passado

# Movimento
GRAVITY = 2600.0
MAX_FALL = 1050.0
FAST_FALL = 1700.0
RUN_SPEED = 430.0  # multiplicado pelo `speed` do lutador
GROUND_ACCEL = 5200.0
GROUND_FRICTION = 4200.0
AIR_ACCEL = 2600.0
AIR_SPEED = 400.0
AIR_FRICTION = 1100.0  # sem direcional no ar, a velocidade horizontal some aos poucos
HITSTUN_GRAVITY = 0.55  # gravidade reduzida enquanto voa lançado
JUMP_VEL = 980.0
AIR_JUMP_VEL = 880.0
DROP_THROUGH_FRAMES = 12

# Esquiva
DODGE_FRAMES = 14
DODGE_INVULN = 14
DODGE_SPEED = 820.0
DODGE_COOLDOWN = 50
LANDING_LAG = 6

# Borda (agarrar na quina de plataformas sólidas)
LEDGE_HANG = 0.78  # fração da altura: as mãos ficam no topo da plataforma
LEDGE_REACH = 28.0  # tolerância (px) para pegar a borda
LEDGE_INVULN = 30
LEDGE_MAX = 180  # depois disso solta sozinho
LEDGE_REGRAB = 40  # frames sem poder agarrar de novo

# Combate
KB_DECAY = 0.975  # arrasto aplicado ao knockback por frame durante o hitstun
KB_GROWTH_SCALE = 1.5  # multiplica o `growth` de todas as hitboxes (ajuste global de KO)
HITSTUN_PER_KB = 0.016
MIN_HITSTUN = 8
DI_MAX_DEG = 15.0
HITLAG_BASE = 3
CHARGE_BONUS = 0.5  # +50% de dano/knockback com carga máxima
MAX_DAMAGE = 999.0
INPUT_BUFFER = 6  # frames que um botão apertado fica guardado

# Partida
STOCKS = 3
MATCH_SECONDS = 8 * 60
RESPAWN_FRAMES = 90
RESPAWN_INVULN = 120
