# Plano: "Lendas do Ringue" — jogo de luta em plataforma no estilo Brawlhalla

## Contexto
O lendas-da-arena é um MOBA top-down em Python. Tem servidor autoritativo, YAML com "blocks", lobby, bots, cliente desktop (Arcade) e cliente web, além de build e CI. O objetivo é um jogo **original** de luta em plataforma: dano em %, knockback crescente, stocks, blast zones e plataformas. Ele reaproveita a arquitetura e as ferramentas do lendas-da-arena, mas troca a física, o combate e o input.

Decisões já tomadas:
- **Stack:** a mesma do lendas-da-arena (Python 3.12 + uv, Arcade, websockets + msgpack, PyYAML, cliente web JS sem build).
- **Rede:** servidor autoritativo com **predição no cliente** para o próprio lutador.
- **Local:** novo repositório irmão em `c:\Users\lucas\Documents\GitHub\lendas-do-ringue`. O nome é provisório e fácil de trocar.

Personagens, arte e nomes são originais. Não copiamos lendas, mapas ou visual do Brawlhalla, só o gênero e as mecânicas.

## Estrutura do novo repositório (espelha o lendas-da-arena)
```
pyproject.toml, uv.lock, ruff/pytest config, .gitattributes (LFS), AGENTS.md/CLAUDE.md
shared/   constants.py, sim.py, physics.py, combat.py, protocol.py, content.py, paths.py
server/   game_server.py, lobby.py, bots.py, web.py, ngrok.py, __main__.py
client/   game_window.py, menu_view.py, lobby_view.py, hud.py, net.py, interp.py, predict.py,
          input.py, sprites.py, effects.py, audio.py, options.py, ui.py, __main__.py
web/      index.html, js/ (mirrors client/)
content/  fighters/*.yaml, weapons/*.yaml, stages/*.yaml, rules.yaml
assets/   fighters/<key>/*.png, stages/<key>/*.png, sounds/, music/
tools/    build_sprites.py, build_audio.py, build_stage_art.py, sprite_viewer.py, hitbox_editor.py
tests/    test_physics, test_combat, test_sim, test_predict, test_server, test_content
.github/workflows/ci.yml, release.yml
```

### Copiar e adaptar do lendas-da-arena (`lendas-da-arena/`)
| Origem | Uso |
|---|---|
| `shared/paths.py` | Copiar como está (resolve caminhos no código-fonte e no PyInstaller) |
| `shared/protocol.py` | Base do envelope msgpack `{"t":...}`, com mensagens novas (abaixo) |
| `shared/content.py` | Padrão de loader YAML → dataclasses congeladas + `params`/`ab.get()` |
| `server/game_server.py` | Loop asyncio com tick, broadcast de snapshot, reconexão por token, espectadores, senha |
| `server/lobby.py` | Slots, escolha de personagem, ready, adicionar bots. Os modos viram FFA 1v1/2v2/4-FFA |
| `server/web.py`, `server/ngrok.py` | Servir `web/` + `/assets` + `/api/content.json` na mesma porta |
| `client/net.py`, `client/interp.py` (+ `web/js/` equivalentes) | Thread de rede e interpolação dos outros jogadores |
| `client/ui.py`, `options.py`, `effects.py`, `audio.py` | Botões e painéis, opções, partículas, tremor de tela, áudio com pan |
| `client/menu_view.py`, `lobby_view.py` | Fluxo Menu → Lobby → Jogo |
| `tools/build_audio.py` | Síntese de SFX com numpy (novos sons: pulo, hit leve/pesado, KO) |
| `.github/workflows/*.yml` | CI (ruff + pytest) e release PyInstaller no Windows |

## Design de jogo (MVP)
- **Partida:** 2 a 4 jogadores, 3 stocks e 8 minutos. Quem sai da blast zone perde um stock.
- **Movimento:** gravidade, pulo + 2 pulos aéreos, fast-fall, dash no chão e no ar, dodge (esquiva no chão ou no ar, com cooldown e i-frames), wall-cling curto, plataformas soft (atravessa de baixo e desce com ↓).
- **Dano e knockback:** o dano acumula em % (de 0 a 999).
  - `knockback = base + growth * damage% * peso`
  - O ângulo vem de cada hitbox.
  - O hitstun é proporcional ao knockback.
  - DI simples: o direcional muda o ângulo em até ±15°.
- **Ataques** (estilo plataforma, com nomes próprios): leves (neutro, lateral, baixo, no ar), fortes/carregáveis (neutro, lateral, baixo) e recovery (o ataque para cima no ar devolve o pulo uma vez).
- **Armas:** cada lutador usa 2 armas. Elas caem no mapa, e trocar de arma muda o moveset. Isso entra na fase 4, e o MVP usa um moveset fixo por lutador.
- **Elenco inicial:** 4 lutadores originais com pesos e velocidades diferentes.
- **Mapas:** 2 mapas, um com plataforma principal + 2 soft e um "plano" competitivo.

## Simulação (`shared/`) — determinística e pura, rodando a 60 ticks/s
- `constants.py`: `TICK_RATE = 60` (luta precisa de mais que os 30 do MOBA), gravidade, velocidade terminal e tamanho das blast zones.
- `physics.py`: AABB vs. retângulos do mapa (sólidos e soft), integração em sub-passos, detecção de chão, parede e ledge.
- `combat.py`: frame data por ataque (startup/active/recovery), hitboxes em retângulos relativos ao lutador e espelhados pela direção, hurtbox, um acerto por alvo por ataque (como o `p.hit` dos projéteis em `sim.py`) e cálculo de knockback, hitstun e hitlag.
- `sim.py`:
  - `Fighter` (dataclass) com uma máquina de estados: idle, run, jump, fall, attack, hitstun, dodge, ledge, ko, respawn.
  - `World.step(inputs)` recebe o **input de botões por jogador** naquele tick, e não comandos de alvo.
  - Mantém a lista `events` (hit, ko, jump, dodge) para som, partículas e tremor de tela, como o lendas-da-arena já faz.
- **Formato do input:** um bitmask de 16 bits (esquerda, direita, cima, baixo, pulo, leve, forte, dodge, arremessar) + número de sequência. Isso permite a predição e o replay.

### Conteúdo (`content/fighters/<key>.yaml`)
```yaml
name: Ravena
weight: 1.0        # mais alto = sai voando menos
speed: 1.1
air_jumps: 2
hurtbox: {w: 50, h: 110}
moves:
  light_side: {startup: 5, active: 3, recovery: 12,
               hitboxes: [{x: 40, y: -60, w: 60, h: 30, dmg: 8, angle: 35, base: 30, growth: 0.6}]}
  heavy_side: {startup: 14, active: 4, recovery: 22, charge: 30, ...}
sprite: {...}      # receita de camadas, como no lendas-da-arena
```
`shared/content.py` carrega isso em `FighterDef`/`MoveDef`/`HitboxDef` congelados. O documento `docs/criando-lutadores.md` vai explicar cada campo, como o `criando-campeoes.md` faz.

## Rede: servidor autoritativo + predição
- O cliente envia `input{seq, tick, bits}` a cada tick (redundância: os últimos 3 inputs vão em cada pacote).
- O servidor aplica o input mais recente de cada jogador por tick. Se faltar input, repete o último.
- Os snapshots (60 Hz, ou 30 Hz com delta) incluem `ack_seq` por jogador.
- `client/predict.py`: o cliente roda o mesmo `shared/sim` localmente só para o próprio lutador. Ao receber um snapshot, ele descarta os inputs já confirmados, reaplica o estado do servidor, re-simula os inputs pendentes e suaviza o erro visual.
- Os outros lutadores usam a interpolação existente (`interp.py`), com o delay reduzido para cerca de 50 ms.
- Hits contra você são decididos sempre no servidor. A predição cobre só movimento e animação do próprio ataque.
- `PROTOCOL_VERSION` começa em 1. Mensagens: hello/welcome, lobby_*, input, snapshot, event, match_end.

## Cliente
- **Input** (`client/input.py`): teclado configurável (padrão WASD + J/K/L/espaço) e controle via `pyglet.input`. A mesma abstração gera o bitmask.
- **Multijogador local:** 2 teclados/controles no mesmo PC, com o servidor em thread (o `--offline` já existe).
- **Câmera:** segue todos os lutadores com zoom dinâmico.
- **HUD:** retrato, % de dano com cor variando de branco a vermelho, stocks e timer.
- **Sprites:** os sheets LPC laterais (linhas esquerda/direita) servem para o MVP. Usamos `tools/build_sprites.py` adaptado, com animações idle, run, jump, attack (slash/thrust) e hurt.
- **Ferramenta `tools/hitbox_editor.py`:** abre um sprite e um move e desenha as hitboxes por frame para facilitar o ajuste.

## Bots (`server/bots.py`)
`BotBrain.think()` produz **bits de input**, não comandos:
- se aproxima do alvo mais próximo
- ataca se o alvo estiver no alcance de algum move
- faz recovery quando sai do palco (prioridade máxima)
- usa dodge com uma chance que depende da dificuldade

Haverá 3 níveis de dificuldade, que mudam o tempo de reação e a precisão.

## Fases de implementação
1. **Esqueleto:** criar o repositório, copiar os itens da tabela, deixar uv, ruff, pytest e CI verdes. O cliente abre o menu.
2. **Física e movimento offline:** `physics.py` + `Fighter` + 1 mapa + câmera + input local, com retângulos coloridos no lugar dos sprites. Testes de pulo, chão, plataforma soft e ledge.
3. **Combate:** frame data, hitboxes, %, knockback, hitstun, blast zones, stocks e HUD. 2 lutadores em YAML. Testes de knockback e KO.
4. **Rede:** protocolo de input, servidor a 60 Hz, predição + reconciliação, lobby FFA, reconexão. Teste de integração do servidor como em `tests/test_server.py`.
5. **Conteúdo e polimento:** 4 lutadores, 2 mapas, sprites, SFX, partículas, hitlag e tremor de tela, bots.
6. **Web e release:** port do cliente `web/js`. Para a predição, ele usa uma cópia JS do movimento de `physics.py`, com testes de paridade contra a versão Python. Release PyInstaller.
7. **Depois do MVP:** armas que caem no mapa, itens, modos (times, KOTH), ranking.

## Verificação
- `uv run ruff check . && uv run pytest`: testes unitários da sim (gravidade, pulos, plataformas, cálculo de knockback, KO na blast zone, determinismo com a mesma sequência de inputs → mesmo estado).
- `uv run python -m client --offline`: jogar contra um bot e conferir pulo, ataque, knockback, KO e respawn.
- Dois clientes locais contra `uv run python -m server`, com latência artificial (flag `--fake-lag 80` no servidor). O próprio lutador deve responder sem atraso, e as correções de predição não devem ficar visíveis.
- `test_server.py`: partida completa entre bots sem humanos até o fim.
- CI verde e build de release gerando o zip.
