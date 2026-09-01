<h1 align="center">Alchemy Hive</h1>

<p align="center">
  <em>Turn your chat history into a living AI persona.</em>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT License"></a>
  <a href="https://github.com/LeonhardJY/Alchemy-hive/actions"><img src="https://github.com/LeonhardJY/Alchemy-hive/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="#"><img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+"></a>
  <a href="#"><img src="https://img.shields.io/badge/platform-win%20%7C%20mac%20%7C%20linux-lightgrey" alt="Windows/macOS/Linux"></a>
  <a href="https://github.com/block/buzz"><img src="https://img.shields.io/badge/imports%20into-buzz-green" alt="Imports into buzz"></a>
</p>

<p align="center"><b>English</b> · <a href="README_zh.md">中文</a></p>

---

## Why?

WeChat conversations, Telegram threads, WhatsApp groups — years of memories locked in chat logs you'll never re-read.

**Alchemy Hive** lets you distill those conversations into a vivid AI persona using any OpenAI-compatible model (DeepSeek, Qwen, Kimi, Ollama, and more). The result is a `.agent.json` you can drop into [buzz](https://github.com/block/buzz) and start chatting with — a digital echo of someone you care about.

```
your chat file ──→ parser ──→ two-stage LLM distillation ──→ .agent.json ──→ buzz
  (WeChat /           detect platform,          analyze + build:            import & chat
  Telegram /          normalize time,            structured analysis →
  WhatsApp /          filter media)              400+ line persona
  Discord /                                      with real quotes
  Slack /
  iMessage /
  QQ /
  Instagram /
  Facebook)
```

## Demo

<!-- Add a screen recording or GIF here showing the GUI in action.
     Record with: https://github.com/nicedoc/screenrecord or OBS.
     Suggested flow: drag file → fill name → click "Start" → see logs → click "Import to buzz" -->

<p align="center"><em>GUI screenshot coming soon — run <code>alchemy-hive gui</code> to try it yourself!</em></p>

## Quick start

### Install

```bash
pip install alchemy-hive
alchemy-hive init    # creates .alchemy-hive/config.toml — fill in your API key
alchemy-hive doctor  # verify config & endpoint connectivity
```

Or install from source:

```bash
git clone https://github.com/LeonhardJY/Alchemy-hive && cd Alchemy-hive
pip install -e .
alchemy-hive init
alchemy-hive doctor
```

### Run the GUI

```bash
alchemy-hive gui              # desktop app with drag-and-drop
alchemy-hive gui --lang en    # English interface
```

### Chat & evaluate

```bash
alchemy-hive chat --name 小明          # talk to the persona
alchemy-hive evaluate --name 小明      # auto-score quality (LLM-as-judge)
```

### Or use the CLI

```bash
# 1. Import chat log
alchemy-hive import chat.txt --name 小明 --self 我 --source auto

# 2. Distill persona
alchemy-hive distill --name 小明 --profile "INTJ 爱吐槽 重感情"

# 3. Export for buzz
alchemy-hive export --name 小明 --format buzz

# 4. Import into buzz
alchemy-hive buzz-import --name 小明
```

### Supported chat exports

| Platform | How to export | Format |
|----------|--------------|--------|
| **WeChat** | [WeFlow](https://github.com/nicedoc/screenrecord) desktop export | JSON |
| **WeChat** | WeChat desktop → backup → txt | txt |
| **Telegram** | Desktop app → Settings → Advanced → Export | JSON |
| **WhatsApp** | Phone → Settings → Chats → Export chat | txt |
| **Discord** | DiscordChatExporter → CSV/JSON export | JSON |
| **Slack** | Workspace Settings → Import/Export Data | JSON |
| **iMessage** | iExplorer or iMazing → export chat → CSV | CSV/TXT |
| **QQ** | QQMsgExport or similar tool → JSON export | JSON |
| **Instagram** | Settings → Privacy → Download your information | JSON |
| **Facebook** | Settings → Your Facebook Information → Download | JSON |

Detailed export instructions: [English](docs/WEFLOW_EXPORT_EN.md) · [中文](docs/WEFLOW_EXPORT_ZH.md)

## How it works

**Stage 1 — Analyze**: Samples recent messages (1500) + early messages (300), sends to LLM for structured analysis — personality, expression patterns, 20-40 verbatim shared memories with real quotes.

**Stage 2 — Build**: Analysis → 400+ line persona Markdown. Fallback to structured rendering if build fails. Never returns empty.

**Quality checks**:
- `blindtest` — real replies vs agent replies, human-rated 1-5
- `doctor` — connectivity check before you start (no LLM calls)
- Interactive correction — `--fix` accumulates corrections across runs

## Features

- **10 platforms** — WeChat (WeFlow JSON + txt), Telegram, WhatsApp, Discord, Slack, iMessage (CSV/TXT), QQ, Instagram/Facebook, generic JSON/txt
- **Auto-detection** — samples 64KB to identify platform; falls back to field probing
- **Two-stage distillation** — structured analysis → long-form persona with real quotes
- **Incremental distillation** — `--incremental` merges new messages into existing persona
- **Plugin architecture** — source adapters + exporter adapters; add new platforms with one file
- **Multi-format export** — system prompt (.txt), buzz (.agent.json), SillyTavern (character card V2), extensible
- **CSV support** — iMessage CSV exports parsed natively; parser accepts JSON/txt/CSV
- **Chat playground** — talk to your persona right in the app, no export needed
- **Auto-evaluation** — LLM-as-judge scores authenticity, consistency, expression, emotional depth
- **Blindtest** — quantify "how close it feels" with human ratings
- **Interactive correction** — `--fix` and `--profile` refine across runs
- **GUI** — pywebview desktop app, drag-and-drop, bilingual (中文/English)
- **Multi-provider** — DeepSeek, Qwen, Kimi, Zhipu, Ollama, vLLM, or any OpenAI-compatible API
- **Privacy-first** — all data stays local; memories off by default

## Commands

| Command | What it does |
|---------|-------------|
| `alchemy-hive gui` | Launch desktop GUI |
| `alchemy-hive init` | Generate config template |
| `alchemy-hive doctor` | Check config & connectivity (no LLM calls) |
| `alchemy-hive import <file> --name X` | Parse chat → structured messages |
| `alchemy-hive distill --name X` | Distill persona |
| `alchemy-hive distill --name X --incremental` | Merge new messages into existing persona |
| `alchemy-hive export --name X --format text/buzz/all` | Export persona (multi-format) |
| `alchemy-hive export-all --name X` | Export all formats at once |
| `alchemy-hive chat --name X` | Chat with the persona |
| `alchemy-hive evaluate --name X` | Auto-score quality (LLM-as-judge) |
| `alchemy-hive blindtest --name X` | Rate agent similarity (1-5) |
| `alchemy-hive pack --names A,B` | Multi-agent community packaging |
| `alchemy-hive buzz-import` | Import into buzz |

## Configuration

`alchemy-hive init` creates `.alchemy-hive/config.toml`:

```toml
[model]
base_url = "https://api.deepseek.com/v1"
api_key = "sk-your-key-here"
model = "deepseek-v4-flash"

# Optional: stronger model for persona writing
# [build]
# base_url = "https://api.deepseek.com/v1"
# api_key = "sk-your-key-here"
# model = "deepseek-chat"
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and guidelines.

## Name meaning

**Alchemy** — transmutation. Chat logs are the raw ore; the distilled persona is the finished metal. Same material, turned into something you can talk to.

**Hive** — a beehive, a hive mind. One agent is a single bee; several pulled into one channel form a hive: agents that talk, remember, and answer together.

## Privacy

- Chat samples are sent to the model service **you** configure
- Output `.agent.json` contains real chat content — sanitize before publishing
- Shared memories are not exported by default (`--with-memory` to include)
- API keys are stored locally only

## License

[MIT](LICENSE)
