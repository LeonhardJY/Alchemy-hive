<h1 align="center">Alchemy Hive</h1>
<h3 align="center">Chat logs → lifelike AI personas → buzz .agent.json</h3>

<p align="center"><em style="font-family: Georgia, serif; font-size: 1.1em; color: #777;">Two-stage LLM distillation · Multi-platform import · One-click buzz integration</em></p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT License"></a>
  <a href="#"><img src="https://img.shields.io/badge/release-v0.1.0-blue" alt="v0.1.0"></a>
  <a href="#"><img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+"></a>
  <a href="#"><img src="https://img.shields.io/badge/platform-win%20%7C%20mac%20%7C%20linux-lightgrey" alt="Windows/macOS/Linux"></a>
  <a href="https://github.com/block/buzz"><img src="https://img.shields.io/badge/imports%20into-buzz-green" alt="Imports into buzz"></a>
</p>

<p align="center"><b>English</b> · <a href="README_zh.md">中文</a></p>

---

## What it does

Parses a chat export into structured messages, distills a persona with a two-stage LLM pipeline, and exports a `.agent.json` that the buzz desktop app can import directly.

```
chat file (WeChat / Telegram / WhatsApp / Instagram / Facebook / generic)
  → parser: detect_source samples the first 64KB to identify the platform; --self normalizes "me"; timestamps unified
  → distill:
      analyze   full-text sample (recent 1500 + early 300 messages, no truncation; sample count shrinks automatically if it exceeds the character budget) → structured JSON analysis
      build     analysis → ≥400-line persona Markdown ([build] section can override with a stronger model)
      ├── --profile  manual profile (behavior rules take priority over the chat)
      └── --fix      interactive correction (corrections accumulate into the persona)
  → blindtest: real replies vs. agent replies, human-rated 1-5
  → export: buzz-agent-snapshot v1 format .agent.json
  → buzz-import / pack: import into buzz / multi-agent community packaging
```

## About the name

**Alchemy** — transmutation. Chat logs are the raw ore; the distilled persona is the finished metal. Same material, turned into something you can talk to.

**Hive** — a beehive, a hive mind. One agent is a single bee; several pulled into one channel form a hive: agents that talk, remember, and answer together.

## Features

- **Multi-platform import**: samples the first 64KB of the file to auto-detect WeFlow JSON, WeChat txt, Telegram JSON, WhatsApp txt, Instagram/Facebook (Meta — one shared format); falls back to generic field probing (`content`/`sender`/`time` and common aliases) when detection fails
- **Timestamp normalization**: Telegram ISO, WhatsApp `MM/DD/YY, h:mm AM/PM`, Meta `timestamp_ms` are all converted to `YYYY-MM-DD HH:MM:SS`; WhatsApp date order follows the device locale (DD/MM vs MM/DD) and is detected heuristically; Meta exports are newest-first, so messages are sorted ascending so the "recent sample" stays correct
- **Direction detection**: WeFlow uses the `isSend` field; other platforms have no direction marker, so pass `--self <your nickname>` and your messages are normalized to "me"
- **Two-stage distillation**: analyze (structured analysis + 20-40 verbatim shared memories) → build (long-form persona); a `[build]` config section can swap in a stronger writing model
- **Blindtest**: samples real conversation snippets, has the agent reply, and rates similarity 1-5 — the average quantifies "how close it feels"
- **GUI**: pywebview desktop app with drag-and-drop, platform/provider dropdowns, and a bilingual interface (`--lang`, switchable at runtime)
- **buzz integration**: snapshot format aligned with the buzz desktop app; import reduced to "open the folder + copy the path"; imports all outputs when no name is given

## Quick start

### Requirements

- Python ≥ 3.10
- An OpenAI-compatible model API (`base_url` / `api_key` / `model`); DeepSeek, Qwen, Kimi, Zhipu work directly in mainland China

### Install

```bash
git clone https://github.com/LeonhardJY/Alchemy-hive && cd Alchemy-hive
pip install -e .
alchemy-hive init    # generates .alchemy-hive/config.toml
```

### Distill

```bash
alchemy-hive gui     # graphical interface
```

```bash
alchemy-hive import chat.txt --name Xiaoming --self me
alchemy-hive distill --name Xiaoming --profile "INTJ sarcastic loyal" --fix "he wouldn't say that"
alchemy-hive export --name Xiaoming --with-memory
```

How to export chat logs: see [docs/WEFLOW_EXPORT_EN.md](docs/WEFLOW_EXPORT_EN.md).

## Input formats

Auto-detected, with generic field probing as fallback; `--source <platform>` forces a specific platform.

| Platform | Input | Detection markers | Time source |
|---|---|---|---|
| WeChat | WeFlow export JSON | `isSend` / `msgContent` | `createTime` |
| WeChat | exported txt | `YYYY-MM-DD HH:MM:SS 'sender'` two-line format | line timestamp |
| Telegram | Desktop export JSON | `messages[{type,date,from,text}]` | `date` (ISO) |
| WhatsApp | exported txt | `[MM/DD/YY, h:mm AM/PM] sender: content` | 12-hour clock |
| Instagram / Facebook | Meta data export JSON | `sender_name` / `content` / `timestamp_ms` | ms timestamp |
| Other | any JSON / txt | `content` / `sender` / `time` field probing | as-is |

## Commands

| Command | Description |
|---|---|
| `gui [--lang en]` | Desktop GUI (bilingual) |
| `init` | Generate config template |
| `import <file> --name X [--self nick] [--source platform]` | Parse chat → structured messages |
| `distill --name X [--profile P] [--fix F]` | Distill persona |
| `export --name X [--with-memory]` | Export `.agent.json` |
| `blindtest --name X [--n N]` | Blindtest similarity rating |
| `pack --names A,B [--channel C]` | Multi-agent community packaging |
| `doctor` | Local connectivity check (no LLM calls) |
| `buzz-import` / `buzz-setup` | Import into buzz / buzz-cli direct setup |

## Project structure

```
src/alchemy_hive/
├── core/   # Engine: LLM client, multi-platform parsing, two-stage distillation, models, prompts, blindtest
├── buzz/   # buzz integration: .agent.json snapshot, one-click import
├── cli/    # CLI (typer)
└── gui/    # Desktop GUI (pywebview, bilingual)
examples/   # Sample chat data (also used as test fixtures)
```

## Privacy

- Chat samples are sent to the model service you configure
- Output `.agent.json` contains real chat content — sanitize before publishing
- Shared memories are not exported by default (`--with-memory` to include)
- API keys are stored locally only

[MIT](LICENSE)
