# Criando lutadores e palcos

## Lutador: `content/fighters/<chave>.yaml`

```yaml
name: Ravena
color: [120, 170, 255]   # cor usada até termos sprites
weight: 1.0              # maior = voa menos (divide o knockback)
speed: 1.05              # multiplica a corrida e o controle aéreo
air_jumps: 2
hurtbox: {w: 50, h: 110} # corpo que pode ser atingido (pés no centro-base)
look: {weapon: sword, accent: [235, 235, 250], hair: [40, 40, 70]}
                         # visual: sword | hammer | claws | spear; cor da arma/detalhes; cabelo
moves:
  light_side:
    name: Estocada
    startup: 6           # frames antes de acertar (60 frames = 1 s)
    active: 3            # frames em que a hitbox existe
    recovery: 14         # frames de lag depois
    impulse: [380, 0]    # opcional: velocidade (frente, cima) no 1º frame ativo
    charge: 0            # opcional: frames máximos de carga (+50% com carga cheia)
    landing_lag: 6       # golpes aéreos: lag se pousar no meio do golpe
    hitboxes:
      - {x: 60, y: 60, w: 90, h: 40,   # centro (x à frente, y acima dos pés) e tamanho
         dmg: 9, angle: 30,            # 0 = frente, 90 = cima, negativo = para baixo
         base: 300, growth: 5.5,       # knockback = (base + growth * %alvo) / weight
         start: 0, end: -1}            # opcional: janela dentro dos frames ativos
```

Todo lutador precisa destes golpes: `light_neutral`, `light_side`, `light_down`, `air_neutral`, `air_side`, `air_down`, `heavy_neutral`, `heavy_side`, `heavy_down`, `recovery` e `air_heavy_down`. Se faltar algum, o `tests/test_content.py` falha.

O desenho é um esqueleto animado ([client/rig.py](../client/rig.py)). Nos golpes, o braço mira o centro da primeira hitbox, então um golpe novo já sai animado sem precisar de arte.

Referências de balanceamento:
- O `growth` de todas as hitboxes é multiplicado por `KB_GROWTH_SCALE` em `shared/constants.py`.
- KO sem carga, medido contra a Ravena se recuperando:
  - Golpes fortes laterais (`base` de 380 a 460, `growth` de 9 a 12) matam entre 110% e 170%.
  - Os fortes para cima matam entre 150% e 180%.
  - Os leves só matam acima de 230%.
- Use F1 no jogo para ver as hitboxes.

## Palco: `content/stages/<chave>.yaml`

```yaml
name: Coliseu
platforms:
  - {x: -520, y: -400, w: 1040, h: 400}              # sólida: x/y = canto inferior esquerdo
  - {x: -400, y: 210, w: 250, h: 16, soft: true}      # fina: atravessa por baixo, ↓ desce
blast: {left: -1500, right: 1500, bottom: -900, top: 1250}
spawns: [[-300, 60], [300, 60], [-275, 300], [275, 300]]   # 4 pontos de nascimento
```
