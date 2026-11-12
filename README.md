# Lendas do Ringue

Jogo de luta em plataforma entre amigos, feito em Python. Funciona no estilo do gênero: o dano acumula em %, golpes lançam mais longe conforme o %, perde-se um stock ao sair da tela, e há pulos aéreos, recovery e esquiva. Personagens, palcos e arte são originais.

A arquitetura segue o [lendas-da-arena](../lendas-da-arena/lendas-da-arena): uma simulação pura em `shared/`, conteúdo em YAML e bots que usam os mesmos inputs dos jogadores.

## Rodar

```powershell
uv sync
uv run python -m client                       # menu
uv run python -m client --quick ravena toro   # direto: você vs bot
uv run pytest -q; uv run ruff check .
```

## Jogar online

- **Pelo menu:** em "Online: criar sala", o seu PC vira o servidor e a tela da sala mostra o IP para os amigos da mesma rede. Eles usam "Online: entrar em sala" e digitam esse IP.
- **Servidor dedicado:**
  ```powershell
  uv run python -m server                    # porta 8766
  uv run python -m server --ngrok            # + link público (precisa do ngrok configurado)
  uv run python -m server --senha dragao     # sala com senha
  uv run python -m server --fake-lag 120     # simula 120 ms de ping, para testar
  uv run python -m client --server 192.168.0.5          # ou o link https do ngrok
  ```
- **Pelo navegador:** o servidor também entrega o jogo como página web.
  - Os amigos abrem `http://IP:8766` (ou o link do ngrok) e jogam sem instalar nada.
  - O botão "Treino contra bot" (ou `/?treino`) entra, põe um bot e começa.
  - O navegador roda a mesma simulação em JS (`web/js/sim.js`) para a predição. Os testes `tests/test_web_parity.py` garantem que o JS e o Python dão o mesmo resultado.
- **Na sala:**
  - Todos: ←→ trocam o lutador.
  - Convidados: Espaço marca pronto.
  - Anfitrião: P troca o palco, N a dificuldade dos bots, B põe um bot, X tira um bot e Enter inicia.

Como a rede funciona:
- O servidor é autoritativo e roda a 60 Hz. Ele envia snapshots a 30 Hz.
- O seu lutador responde na hora: o cliente prevê o movimento e reconcilia com o `ack` de cada snapshot.
- Os adversários aparecem cerca de 100 ms no passado, com interpolação.
- Se alguém cair, um bot assume o lutador. Ao voltar com o mesmo cliente, a pessoa recupera a vaga.

## Release (.exe)

Ao criar uma tag `v*`, o GitHub Actions gera `LendasDoRingue-windows.zip` e publica em Releases:

```powershell
git tag v0.1.0; git push --tags
```

Para gerar localmente:

```powershell
uv run pyinstaller client/__main__.py --name LendasDoRingue --noconsole --onedir --noconfirm `
  --add-data "content;content" --add-data "assets;assets" --add-data "web;web" `
  --hidden-import server.game_server --hidden-import server.web
```

Não use `--collect-all arcade`: o Arcade já traz um hook próprio do PyInstaller, e as duas coisas juntas conflitam no arquivo `VERSION`.

## Controles

| | P1 (teclado) | P2 (teclado) | Controle |
|---|---|---|---|
| Mover | WASD | setas | analógico / d-pad |
| Pular | Espaço | Shift direito / Num0 | A |
| Leve | J | `,` / Num1 | X |
| Forte (segure p/ carregar) | K | `.` / Num2 | B ou Y |
| Esquiva | L | `/` / Num3 | LB / RB / gatilhos |

Os golpes mudam conforme a direção segurada: neutro, lado ou baixo, no chão ou no ar. Forte no ar dispara o recovery (uma vez por voo), e baixo + forte no ar faz uma investida para baixo.

**Na borda:** ao cair rente à quina do palco, o lutador agarra sozinho. Na borda:
- ↑, a direção do palco ou um ataque sobem;
- pulo salta;
- ↓ ou a direção para fora soltam.

**Outras teclas:** ↓ numa plataforma fina desce por ela, Esc pausa, F1 mostra/esconde as hitboxes e M liga/desliga o som.

**Som:** os sons e as músicas são gerados por síntese com `uv run python tools/build_audio.py` e ficam em `assets/`.

## Estrutura

- `shared/`: simulação determinística a 60 Hz (`sim.py`), colisões (`physics.py`), fórmulas de combate (`combat.py`), loaders de conteúdo e o bitmask de input.
- `shared/netinput.py`: fila de inputs numerados no servidor (1 por tick, com redundância).
- `shared/protocol.py`: mensagens em msgpack sobre WebSocket.
- `server/`:
  - `game_server.py`: sala, partida e reconexão.
  - `lobby.py`: regras da sala.
  - `bots.py`: IA que gera inputs (fácil, médio, difícil).
- `client/`:
  - Arcade com menu, sala e partida.
  - `drivers.py`: partida local ou online, com predição e interpolação.
  - Câmera dinâmica, HUD e partículas.
- `content/fighters/*.yaml` e `content/stages/*.yaml`: veja [docs/criando-lutadores.md](docs/criando-lutadores.md).
- O roadmap completo está em [docs/plano.md](docs/plano.md).
