# Linux: `sotc.ini`, AppImage, Steam Deck & Tuning

`~/.local/share/sotc-pc/sotc.ini` (AppImage / `.tar.gz`) ou / or `sotc.ini` ao lado do / next to `sotc.py`.
Uma opção por linha / one option per line, `NOME=valor`; `#` comenta / comments. Variáveis de
ambiente têm prioridade sobre o arquivo / environment variables take precedence over the file
(`BB_FULLSCREEN=0 ./SotC-PC-...AppImage`). São as mesmas que o lançador ajusta / the same ones the
launcher sets (`launcher/sotc_launcher_win.py`, `game_environment`).

A AppImage (e o `./sotc.sh` do `.tar.gz`) abre o lançador, que guarda os ajustes dele em / The AppImage (and `./sotc.sh` from `.tar.gz`) opens the launcher, which keeps its settings in `~/.local/share/sotc-pc/user/launcher_settings.json` e os passa ao jogo por cima deste arquivo / and passes them to the game over this file:

- `--play`: abre o jogo direto com os ajustes salvos (ideal para Steam) / starts the game directly with saved settings (ideal for Steam).
- `--launcher`: abre o lançador mesmo no Steam Gaming Mode / forces the launcher window even inside Steam Gaming Mode.
- `--setup`: refaz a escolha das pastas sem interface gráfica / re-runs folder setup headlessly.
- No **Steam Deck / Gamescope Gaming Mode** (`SteamDeck=1` / `SteamGamepadUI=1`), abrir sem argumentos inicia direto com `--play` quando o setup já está pronto; passe `--launcher` para abrir a janela de configurações / On **Steam Deck / Gamescope Gaming Mode**, launching with no arguments starts `--play` automatically once configured; pass `--launcher` to open settings.

Na primeira abertura, o lançador lê o que já estiver em `sotc.ini` / On its first start the launcher reads what is already in `sotc.ini`. Sem tela (terminal, SSH) ou com `--setup`, vale só `sotc.ini` / Without a display (terminal, SSH) or with `--setup`, only `sotc.ini` applies.

## Steam, atalhos e ferramentas Linux / Steam, shortcuts & Linux tools

- **Adicionar ao Steam (1 clique) / Add to Steam (1 click):** em **Avançado** (*Advanced*), o botão grava o atalho diretamente em `userdata/<id>/config/shortcuts.vdf` (backup em `.bak`) e copia capa horizontal, capa vertical, hero e ícone do seu dump (`sce_sys/icon0.png` e `pic1.png`) para `config/grid/` — funciona no Desktop e no Steam Deck / in **Advanced**, writes directly to `shortcuts.vdf` (backing up `.bak`) and installs grid artwork from your dump (`sce_sys/`) into `config/grid/`.
- **Atalhos `.desktop` / `.desktop` shortcuts:** na aba **Avançado**, cria entradas em `~/.local/share/applications/` (`sotc-pc.desktop` e `sotc-pc-play.desktop`).
- **GameMode e MangoHud:** opções em **Avançado → Linux** envolvem o comando do jogo com `gamemoderun` e/ou `mangohud` quando presentes no `PATH`.
- **Predefinição Steam Deck (800p) / Steam Deck (800p) preset:** na aba **Jogar** (*Play*), configura saída `1280×800`, modo Leve de GPU, `30 FPS` e sombras otimizadas para portátil / in **Play**, sets `1280×800`, Light GPU profile, `30 FPS`, and tuned shadows for handheld play.
- **DualShock 4 / DualSense:** barra de luz (`scePadSetLightBar`) e sensores de movimento (giroscópio + acelerômetro via SDL3) funcionam nativamente; defina `SOTC_LIGHTBAR=0` para manter o LED inalterado / Lightbar and gyro/accelerometer work out of the box; set `SOTC_LIGHTBAR=0` to disable LED updates.

## Tuning do kernel e PGO / Kernel tuning & PGO

- **`vm.max_map_count`:** o alocador de memória reserva muitas áreas virtuais; se estiver abaixo de `262144`, o lançador avisa antes de abrir. Recomendado:
  - Temporário / temporary: `sudo sysctl -w vm.max_map_count=1048576`
  - Permanente / permanent: `echo "vm.max_map_count=1048576" | sudo tee /etc/sysctl.d/99-sotc.conf`
- **`vm.unprivileged_userfaultfd`:** quando ativo (`1`), o port usa `userfaultfd` para proteção de memória; quando desativado (`0`, comum em várias distros), usa `SIGSEGV` automaticamente (o painel *Verificação* mostra o modo ativo). Para testar `userfaultfd`: `sudo sysctl -w vm.unprivileged_userfaultfd=1`.
- **Build com PGO e dependências locais / PGO build & local deps:** `build.sh` e `tools/pgo_train.sh` detectam automaticamente `$HOME/.local/opt/sotc-deps` em `CMAKE_PREFIX_PATH`. Para compilar com otimização guiada por perfil (GCC PGO + LTO), rode `bash tools/pgo_train.sh`, jogue por 1–3 minutos e feche o jogo.

## Jogo e arquivos / Game and files

| Opção / Option | Valor / Value |
|---|---|
| `SOTC_GAME_DIR` | pasta do dump / dump folder (`eboot.bin`, `sce_module`, `sce_sys`) |
| `SOTC_SYS_MODULES` | pasta com / folder with `libSceNgs2.sprx` e / and `libSceUlt.sprx` (opcional: sem ela, o mixer embutido toca o som / optional: without it, the built-in mixer plays the sound) |
| `SOTC_UPDATE_DIR` | atualização do jogo / game update (padrão / default `<jogo>-UPDATE` ou / or `-patch`) |
| `SOTC_DLC_DIR` | DLCs (`addcont` do shadPS4 ou uma subpasta por DLC / or one subfolder per DLC) |
| `SOTC_USER_DIR` | saves e caches / saves and caches (padrão / default `~/.local/share/sotc-pc/user`) |

## Modos, imagem e HDR / Modes, image & HDR

| Opção / Option | Valor / Value |
|---|---|
| `SOTC_MODES` | `af16` (filtro 16x / 16x AF), `fps60` (sem trava de 30 FPS / uncap 30 FPS); ex. `af16,fps60` (EU 1.01 e US 1.00 / EU 1.01 and US 1.00) |
| `SOTC_NEO` | `1`: modo PS4 Pro / PS4 Pro mode |
| `SOTC_OUTPUT_RES` | saída / output, ex. `2560x1440` ou `1280x800` (padrão / default `1920x1080`) |
| `SOTC_MONITOR_AT` | coordenadas `x,y` do monitor alvo no Linux (preenchido pelo lançador via SDL3) / target monitor coordinates `x,y` on Linux |
| `BB_FSR1` | `1`: FSR 1 para ampliar / to upscale (pelo `.ini` vem desligado / off by default here) |
| `BB_RCAS`, `BB_RCAS_ATTENUATION` | nitidez / sharpness: `BB_RCAS=0` desliga / off; atenuação `0` alta / high, `250` média / medium (padrão / default), `600` baixa / low |
| `BB_FULLSCREEN` | `1`: tela cheia / fullscreen |
| `BB_PRESENT_MODE` | `Mailbox` (padrão / default), `Fifo` (VSync), `Immediate` |
| `SOTC_FPS_CAP`, `SOTC_FPS_DYNAMIC`, `SOTC_FPS_FG_CAP` | teto de FPS e passo dinâmico divisor da taxa da tela (padrão ajusta quando Frame Generation está ativo) / FPS limit and dynamic divisor step (FG-aware) |
| `SOTC_FPS` | `1`: FPS no registro a cada 5 s / FPS in the log every 5 s |
| `SOTC_HDR_MAX_NITS`, `SOTC_HDR_MAX_FALL`, `SOTC_HDR_PAPER`, `SOTC_HDR_GAIN` | metadados `VK_EXT_hdr_metadata` e brilho do HDR10 no Linux (padrão 1000 / 400 nits) / HDR10 metadata and SDR-to-HDR tone mapping on Linux |

## Efeitos do motor / Engine effects (`SOTC_CVARS`)

Cvars separadas por espaço / space-separated. Definir `SOTC_CVARS` substitui o padrão; mantenha
as duas primeiras (mesma imagem, menos esperas da GPU) / Setting it replaces the default; keep the
first two (same image, fewer GPU waits):

```
SOTC_CVARS=doIndexBufferCulling=0 doSunShadowIndexBufferCulling=0 fog_enable=0
```

- `r_vignetteOverrideEnable=1 r_vignetteEnable=0`: sem vinheta / no vignette
- `fog_enable=0`: sem névoa / no fog
- `AO_Mode=0`: sem SSAO / no SSAO

## Desempenho / Performance

| Opção / Option | Valor / Value |
|---|---|
| `BB_DIRECT_MEMORY_ACCESS` | `0`: ~10% mais FPS, água distante mais lisa / ~10% more FPS, flatter distant water |
| `SOTC_FLUSH_US=500` + `SOTC_RB_AHEAD=1` | envio periódico à GPU (automático só na NVIDIA); em AMD/Intel teste, e se a tela ficar preta remova / periodic GPU submission (automatic on NVIDIA only); try on AMD/Intel, remove on a black screen |
| `SOTC_RECORD_THREAD` | `0`/`1`: gravação Vulkan em thread própria / Vulkan recording on its own thread |
| `BB_READBACKS` | não use `1` (relaxado, pode travar) / don't use `1` (relaxed, may hang) |
| `BB_TIMEOUT` | segundos do watchdog de diagnóstico (padrão desligado) / diagnostic watchdog seconds (off by default) |

## Idioma e controles / Language and controls

| Opção / Option | Valor / Value |
|---|---|
| `BB_LANGUAGE` | `15` pt-BR, `7` pt-PT, `1` inglês / English (padrão / default), `3` es, `2` fr, `4` de, `5` it, `0` ja |
| `BB_USER_NAME` | nome do jogador / player name |
| `BB_GAMEPAD` | parte do nome do controle / part of the controller's name |
| `SOTC_LIGHTBAR` | `0` desativa controle da barra de luz no DS4/DualSense / disables DS4/DualSense lightbar updates |
| `SOTC_MOUSE`, `SOTC_MOUSE_SENS`, `SOTC_MOUSE_INVERT` | câmera no mouse / mouse camera: `0` desliga / off; sensibilidade / sensitivity (padrão / default `1.0`); `1` inverte / inverts Y |
| `key.<ação>=Teclas` | teclas do SDL, vírgula separa / SDL key names, comma-separated (`key.cross=Space,Return`) |
| `pad.<ação>=botões` | botões do SDL / SDL buttons (`a b x y back start leftshoulder rightshoulder lefttrigger righttrigger dpup ...`) |

Ações / actions: `cross circle square triangle l1 r1 l2 r2 l3 r3 options touchpad touchpad_right
up down left right`; no teclado também / on the keyboard also `move_up/down/left/right` e / and
`look_up/down/left/right`. Menu sobre o jogo / in-game overlay: **F1**, **Insert** ou / or **L3+R3**.
