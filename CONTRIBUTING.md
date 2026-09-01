# Contributing to Alchemy Hive

Thanks for your interest in contributing! This project turns chat logs into AI personas — every improvement helps people connect with their digital memories.

## Development Setup

```bash
git clone https://github.com/LeonhardJY/Alchemy-hive && cd Alchemy-hive
pip install -e ".[dev]"
pytest tests/ -v   # run the full test suite
```

## How to Contribute

### Bug Reports

Open an issue with:
- What you expected
- What actually happened
- The command you ran and the full error output
- Your OS and Python version

### Feature Requests

Describe the use case, not just the solution. "I want to export to Discord" is more useful than "add Discord support."

### Code Contributions

1. Fork the repo and create a branch from `main`
2. Write tests for any new functionality
3. Run `pytest tests/ -v` — all tests must pass
4. Open a PR with a clear description of what changed and why

### Adding a New Platform Parser

The parser lives in `src/alchemy_hive/core/parser.py`. To add a new platform:

1. Add detection markers to `detect_source()`
2. Write a `_parse_<platform>(path)` function returning `list[Message]`
3. Add the platform to `SOURCE_LABELS` and `_dispatch()`
4. Add tests in `tests/test_platform_formats.py`
5. Update the input formats table in both READMEs

### Translation

The GUI supports Chinese and English. To add a new language:

1. Add entries to `_L`, `_T`, and `_EN_HTML` in `gui/webview_app.py`
2. Add language detection fallback in `_detect_lang()`
3. Update the language selector options in `_HTML`

## Code Style

- Python 3.10+ (use `X | Y` union syntax, not `Optional[X]`)
- Type hints on all public functions
- Docstrings in Chinese (matching the existing codebase)
- Tests for any new code paths

## Running a Single Test

```bash
pytest tests/test_parser.py::test_whatsapp_standard_parse -v
```

## Architecture

```
src/alchemy_hive/
├── core/        # Engine: LLM, parsing, distillation, blindtest
│   ├── llm.py          # OpenAI-compatible client
│   ├── parser.py       # Multi-platform chat parser
│   ├── distill.py      # Two-stage LLM distillation
│   ├── blindtest.py    # Real vs agent reply comparison
│   ├── models.py       # Pydantic data models
│   ├── prompt.py       # LLM prompt templates
│   ├── safe.py         # Safe filename utilities
│   └── health.py       # Connectivity check
├── buzz/        # buzz desktop app integration
├── cli/         # CLI commands (typer)
└── gui/         # Desktop GUI (pywebview, bilingual)
```

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
