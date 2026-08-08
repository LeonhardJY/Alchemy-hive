# How to export chat logs

Alchemy Hive recommends **WeFlow JSON exports** (the richest format), but input is **not limited to WeFlow** — any platform's chat export that can be parsed into messages can be distilled.

## Not just WeFlow

Platforms are auto-detected (`alchemy-hive import` accepts them directly, or pick "source platform" in the GUI):

- **Telegram**: Desktop app → "Export chat history" → tick *Machine-readable JSON*; the `messages[{type, date, from, text}]` structure is parsed directly
- **WhatsApp**: Conversation → "Export chat" → txt; the `[MM/DD/YY, h:mm AM/PM] sender: content` format is parsed directly (image/file lines are skipped)
- **Instagram / Facebook**: `message_*.json` from the Meta data download (`sender_name / content / timestamp_ms`) is parsed directly and sorted by time
- **WeChat txt**: the `timestamp 'sender'` two-line format
- **Generic fallback**: when detection fails, field probing for common names like `content/sender/time` usually still works

These platforms' exports carry **no direction marker** (they don't say which side is you), so pass `--self` before distilling so your messages are normalized to "me":

```bash
alchemy-hive import telegram.json --name counterpart --self your-nickname
```

## WeFlow (recommended)

1. Download and install [WeFlow](https://github.com/hicccc77/WeFlow), scan the QR code with WeChat — it runs fully locally, nothing is uploaded
2. Pick a **private conversation** on the left, find "Export" in the conversation's top-right menu
3. Choose **JSON**, and **make sure to tick "include both sides' messages"** — exporting only your own messages loses half the material and the distillation comes out skewed
4. The resulting `.json` goes straight into `alchemy-hive import`

Only 1-on-1 chats are supported. Group chats have a more complex multi-person structure and aren't supported yet.

## WeChat txt (alternative)

Copy the chat and save it as txt, **one pair of lines per message**:

```
2023-07-24 09:29:09 'Xiaoming'
message content
2023-07-24 09:31:53 'me'
let me look
```

- Line 1: `timestamp + space + sender` (quotes optional)
- Line 2: message content
- Time format: `YYYY-MM-DD HH:MM:SS`, hour can be `9` or `09`
- UTF-8 / GBK both work; special whitespace like ` ` (U+2005) is recognized

Both formats **skip image / emoji / link placeholders** automatically (e.g. `[图片]`, `[色]`).

## FAQ

**Q: The distillation doesn't sound like them?**

Check the material first: didn't tick "include both sides", too few messages (below a few hundred), or no personality profile. `--profile "INTJ sarcastic"` helps a lot; if it's still off, use `--fix` for interactive correction.

**Q: Is the data safe?**

WeFlow runs locally; samples are sent to the model service you configure. The `.agent.json` output contains real chat content — **sanitize it yourself before sharing or publishing** (replace names / numbers).
