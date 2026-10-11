# Divide Reader

Divide Reader reads websites, books and files one sentence at a time. For each sentence it counts **S**: how many sides the speaker sorts the sentence's figures into. It finds every reading the text supports, not one verdict. The report shows the five most heard readings per sentence and gives measures you can compare between sites or between periods.

**Install and use:** [GUIDE.md](GUIDE.md) (English) · [UPUTSTVO.md](UPUTSTVO.md) (srpski). The `.deb` package is under **Releases**.

The full design is in `Divide-Reader-plan.docx` (in Serbian), one folder up.

## How a sentence is read

1. **Figures.** The model lists the explicit figures three times. Figures named at least twice are locked as f0, f1, …
2. **Five listeners.** Each listener reads the sentence from a different position: neutral, close to the speaker, averse to the speaker, from the place of a figure, and with no context.
   - When F ≤ 5, the program lists every partition of the figures itself (at most 52) and asks which ones the text supports. The list is therefore complete by construction.
   - When F ≥ 6, the listeners propose readings themselves, and completeness is not guaranteed.
3. **Other counts.** Anything else in the sentence that can be counted, such as times or occasions, goes in a separate part of the report.

Every partition has a canonical key (`0,0,0,1` = {f0, f1, f2} | {f3}). This lets readings from different listeners, rounds, models and manual counts be compared directly. Rejected partitions are kept along with the reason.

A whole source is **one speaker**: a site, a book, or a book with several authors. Quoted people are figures.

## Models

On the start screen you choose one of these:

| Group | What | Login |
|---|---|---|
| Built-in | llama.cpp ships in the package. A JSON grammar forces every answer into the schema, so the answer is always valid. | none |
| Ollama | models you already have in Ollama | none |
| Free online | Gemini, Groq, Mistral, OpenRouter free models | browser |
| Paid online | Claude, OpenAI, Grok, OpenRouter | browser |

- **Local models.** The start screen gives a direct download link for each recommended file, and a Download button that checks the SHA256.
  - Gemma 4 E2B / E4B / 12B
  - Qwen3.5 4B / 9B
- **Online logins.** An online login always opens your default browser.
  - OpenRouter returns a key to the program by itself (OAuth PKCE).
  - The other providers only issue API keys. The browser opens their key page and you paste the key in.
  - Logins are kept in memory only and are gone when the program closes.
- **Paid models.** Paid models need a cost cap for each job, and the job stops when it reaches the cap.

## Use

GUI: `divide-reader` (no arguments).

CLI:

```
divide-reader models                       # models and direct download links
divide-reader download gemma-4-e4b
divide-reader read https://example.com --provider claude --model claude-sonnet-5-5 --cap 5
divide-reader read book.epub --provider local --model gemma-4-E4B-it-Q4_K_M.gguf --unit paragraph
divide-reader read https://example.com --mode wayback --year 2005 --provider ollama --model gemma3:latest
divide-reader sources
divide-reader report 3 4                   # two sources side by side
divide-reader check                        # coverage and excess against manual counts
```

Each job writes three files: `report.html`, `measures.csv` and the SQLite store, which holds every intermediate result. They go under `~/.local/share/divide-reader/projects/<name>/`.

## Develop

```
uv venv .venv && uv pip install -p .venv -e ".[dev]"
.venv/bin/python -m pytest
bash packaging/build_deb.sh                # dist/divide-reader_<v>_amd64.deb
```

A `.deb` runs only on systems with the same or newer glibc than the machine it was built on. The release build therefore runs on Ubuntu 22.04 (`.github/workflows/build-deb.yml`).

## Licence

GPL-3.0-or-later. The bundled llama.cpp is MIT.
