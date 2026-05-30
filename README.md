# 🐾 Buddy — Your AI-Powered Desktop Pet

A transparent, always-on-top desktop companion that lives on your Windows desktop.  
Buddy wanders, sleeps, plays fetch, reads your screen (locally!), reacts to notifications, comments on the weather, and chats with you — all powered by a **local LLM** via [Ollama](https://ollama.com) so nothing leaves your machine.

> Built with Python + PyQt6 + Pillow + Ollama. 100 % offline-capable.

---

## ✨ Features

- **Live pixel-art pet** with 18 hand-drawn sprite sheets — walks, runs, sits, jumps, scratches, stretches, sleeps, dances
- **Live animated tail** that wags faster when excited, droops when sleeping
- **Screen vision** — uses local multimodal models (moondream, llava, etc.) to glance at your screen and comment in-character
- **Context-aware** — knows when you're coding, gaming, in a meeting, watching videos, browsing
- **Speech bubbles** powered by a local SLM (`gemma3:1b` by default)
- **Notification reactions** — barks at Windows toast notifications
- **Play mechanics** — give Buddy a treat, throw a ball, play fetch, pet him
- **Resource-aware** — automatically throttles animations/AI calls if CPU/RAM is busy
- **Weather reactions** via wttr.in
- **System tray icon** with quick actions

---

## 📦 Requirements

- **Windows 10/11**
- **Python 3.11+**
- **[Ollama](https://ollama.com)** running locally
- ~3 GB free disk space for the smallest models

---

## 🚀 Setup

```powershell
# 1. Clone
git clone https://github.com/<your-username>/desktop-pet.git
cd desktop-pet

# 2. Virtual env
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. Install dependencies
pip install -r requirements.txt

# 4. Install Ollama models (in a separate terminal)
ollama pull gemma3:1b        # text model (~700 MB)
ollama pull moondream        # vision model (~1.7 GB, optional)

# 5. Run
python main.py
```

On first launch, `config.example.yaml` is auto-copied to `config.yaml`, and a friendly dialog asks for your name.

---

## ⚙️ Configuration

Everything is in [`config.yaml`](config.example.yaml) (created on first run from `config.example.yaml`). Every key is documented inline. Highlights:

```yaml
slm:
  text_model: gemma3:1b      # any Ollama chat model
  vision_enabled: false      # set true after pulling a vision model
  vision_model: moondream    # any pulled multimodal model
```

`config.yaml` is git-ignored — your personal name and any future API keys stay private.

---

## 🎮 Controls

| Action | Result |
|---|---|
| **Left-click + drag** | Pick Buddy up and move him |
| **Hold left-click 1 s+** | Pet him (he gets happier) |
| **Double-click** | Open chat dialog — say anything |
| **Right-click tray icon** | Quick actions: give treat, throw ball, peek at screen, etc. |

---

## 🗂️ Project Structure

```
.
├── main.py                  # entry point — thin orchestrator
├── sprite_gen.py            # generates all 18 sprite sheets via PIL
├── config.example.yaml      # template config (git-tracked)
├── config.yaml              # your config (git-ignored, auto-created)
├── assets/
│   ├── sprites/             # generated pixel-art sprite sheets
│   ├── bark.wav             # bark sound
│   └── tray_icon.png        # tray icon
├── pet/
│   ├── brain.py             # state machine (IDLE/WALK/SIT/JUMP/…)
│   ├── window.py            # transparent always-on-top widget
│   └── mood.py              # mood tracker (HAPPY/LONELY/…)
├── intelligence/
│   ├── slm_client.py        # Ollama text generation
│   ├── screen_vision.py     # multimodal screen peek
│   └── weather.py           # wttr.in client
├── system/
│   ├── throttle.py          # CPU/RAM monitor
│   ├── context_detector.py  # foreground-window classifier
│   └── notification_watcher.py
├── skills/                  # high-level behaviours
│   ├── weather_skill.py
│   ├── vision_skill.py
│   ├── play_skill.py
│   ├── social_skill.py
│   ├── commentary_skill.py
│   └── chain_skill.py
├── ui/
│   ├── tray.py
│   ├── treat_widget.py
│   ├── ball_widget.py
│   └── chain_anchor.py
└── audio/
    └── engine.py            # WAV playback via sounddevice
```

---

## 🔒 Privacy

- **No data leaves your machine** when using Ollama (default).
- The only external HTTP call is to [wttr.in](https://wttr.in) for weather (no auth, no tracking).
- Screen contents are only sent to your **local** Ollama instance for vision peeks.
- `config.yaml` is git-ignored to keep your personal name out of public commits.

---

## 🐛 Troubleshooting

| Symptom | Fix |
|---|---|
| Buddy doesn't talk | Make sure Ollama is running: `ollama serve` |
| `[vision] Ollama unreachable` | Same — start Ollama |
| `I need glasses! Run: ollama pull moondream` | Pull a vision model |
| Buddy freezes on a low-spec PC | Lower `pet.fps_full` in `config.yaml` |

---

## 📄 License

[MIT](LICENSE) — do whatever you want, just don't blame me if Buddy bites.

---

## 🙏 Credits

- Sprite art generated procedurally with [Pillow](https://pillow.readthedocs.io/)
- LLM inference via [Ollama](https://ollama.com)
- Vision models: [moondream](https://moondream.ai), [LLaVA](https://llava-vl.github.io/)
- Built on [PyQt6](https://www.riverbankcomputing.com/software/pyqt/)
