# Divide Reader — guide

Divide Reader reads websites, books and files one sentence at a time. For each sentence it counts **S**: how many sides the speaker sorts the sentence's figures into. It does not pick one correct reading. It lists every reading the text supports and records how many of five listeners heard each one. At the end it writes a report with numbers you can compare between sites or between periods.

Srpska verzija: [UPUTSTVO.md](UPUTSTVO.md)

---

## 1. What you need

- Ubuntu 22.04 or newer, or Debian 12 or newer, on a 64-bit PC (amd64); or Windows 10/11, 64-bit.
- About 0.5 GB of disk for the program. A local model needs another 3–7 GB.
- At least 8 GB of RAM for a local model. Without that, use an online model.

## 2. Install

### Ubuntu / Debian

1. Download `divide-reader_0.1.1_amd64.deb` from the repository page: **Releases** → **v0.1.1**.
2. Open a terminal in the folder that holds the file and run:

   ```
   sudo apt install ./divide-reader_0.1.1_amd64.deb
   ```

   `apt` installs the libraries the program needs.
3. The program appears in the menu as **Divide Reader**. From a terminal, start it with `divide-reader`.

### Windows

1. Download `DivideReader-Setup-0.1.1.exe` from the same release.
2. Run it. It installs for your user only and needs no administrator rights. The installer is not code-signed, so SmartScreen shows "Windows protected your PC": choose **More info**, then **Run anyway**.
3. The program appears in the Start menu as **Divide Reader**.

The program starts in English. Switch to Serbian (Latin script) with **Language** at the top right.

## 3. First step: choose a model (tab "1. Model")

The model is what reads the text. There are four groups.

### Built-in local model (llama.cpp)
- Works without internet and costs nothing.
- **Always returns a valid answer.** llama.cpp uses a grammar to force every answer into the required JSON schema. If an answer runs out of room before it ends, the program asks again with more room.
- The top of the screen has **direct download links** and a **Download** button next to each model. The program recommends a model for your RAM:

| Model | Size | RAM |
|---|---|---|
| Gemma 4 E2B | 3.1 GB | ~4 GB |
| Gemma 4 E4B | 5.0 GB | ~8 GB |
| Gemma 4 12B | 7.1 GB | ~16 GB |
| Qwen3.5 4B | 2.7 GB | ~4 GB |
| Qwen3.5 9B | 5.7 GB | ~10 GB |

- Downloaded models are stored in `~/.local/share/divide-reader/models/`. The program checks each download with SHA256.
- If the computer has a graphics card with a Vulkan driver (NVIDIA, AMD or Intel), the program uses it. Otherwise it runs on the CPU.
- **Speed:** on an older CPU without a graphics card, one model call can take several minutes, and one sentence needs 8 calls. Use the local model for trying things out and an online model for larger jobs.

### Ollama
If you already use Ollama, your models appear here. Click **Refresh** to reload the list.

### Free online (Gemini, Groq, Mistral, OpenRouter)
### Paid online (Claude, OpenAI, Grok, OpenRouter)

**Login always goes through your web browser:**
- **OpenRouter:** click **Log in**. The browser opens OpenRouter, you approve, and the program is logged in. This is the easiest way, and OpenRouter also gives you Claude, OpenAI and Grok.
- **Claude, OpenAI, Gemini, Groq, Mistral, Grok:** the browser opens the provider's API key page. Create a key, copy it, and paste it into the program.

**A login lasts until you close the program and is never saved.** You log in again on the next start.

For paid models the program shows the price per million tokens (input / output). Edit it if the provider has changed its prices.

### Buttons at the bottom
- **Test on 3 sentences:** reads three sample sentences to check that the model works and returns valid answers. Run it the first time you use each model.
- **Use this model →:** connects the model and moves you to the Read tab.

## 4. Reading (tab "2. Read")

1. Enter a URL such as `https://example.com`, or click **Browse…** to pick a PDF, EPUB, TXT or HTML file.
2. **How to read it:**
   - **Automatic:** the program decides whether it is a file or a site.
   - **One page:** only that one URL.
   - **Site, same domain (measuring):** visits up to the set number of pages on the same site. Use this mode to compare sites.
   - **Wander from here (exploring):** follows links off the site too. Numbers from wandering are not comparable between sites.
   - **Old snapshot (Internet Archive):** the same URL as it was in a chosen year, for example 2005.
3. **Unit:** sentence (default), paragraph, whole article or book chapter.
4. **Units per source:** how many units to read. When you compare sites, use the same number for each, for example 200. 0 means all.
5. **Cost cap:** required for paid models. The job stops when it reaches the cap, and everything done so far is kept.
6. Below the fields the program shows an **estimate** of calls, tokens and cost.
7. Click **Start**. Click **Stop** to stop, and **Resume last job** to continue later.
8. When the job is done, click **Open report**.

The walker follows each site's `robots.txt`, waits a few seconds between requests and skips pages that need a login. The report lists every skipped page.

## 5. Reading the report

The report has five parts:

1. **What was read:** URLs, dates, number of pages and units, and the model that read them.
2. **Measures.** Every measure comes in two versions. In the **simple** version every reading found counts the same. In the **weighted** version a reading counts by how many listeners heard it.
   - **Locked twos:** sentences with three or more figures where S = 2 is the only reading. This is the main measure.
   - **Open twos:** S = 2 is one of several readings.
   - **Honest twos:** the sentence really has only two figures.
   - **Distribution of S, range, readings per unit, highest S.**
   - **Stability:** how far two rounds of reading the same sentence agree. 1 means identical, 0 means nothing in common.
3. **Hypotheses about the text:** patterns the model sees across the whole text, with the sentences that support and contradict each one.
4. **Readings by unit:** each sentence with its figures and up to five most heard readings. The rest open on click. Each reading shows how many listeners heard it ("heard by 4 of 5"), its assumption and its anchor in the text.
5. **Other counts:** other things in the text that can be counted, such as times. These are not part of the measures.

Next to `report.html` the program also writes `measures.csv` for spreadsheets.

## 6. Manual count (tab "Manual count")

This is the most important step before you trust the program.

1. Enter your name and pick a source, or add a file with **Add file for counting…**.
2. Click **Load units**.
3. For each sentence:
   - Check the figures (one per line) and correct them if needed. **Ask the model for figures** can suggest them.
   - Give each figure a side, then click **Add this reading**.
   - Repeat for every reading you hear.
   - Click **Save**.
4. Count 50–100 sentences. Half of them become examples in the model's instructions; the other half are used only for checking.
5. Click **Check against program**. Coverage (the share of your S values the program also found) should be 80% or more.

## 7. Compare (tab "Compare")

Tick two or more sources and click **Compare selected**. The report puts their measures side by side. A difference counts as a **finding** only when it is larger than the difference between two rounds of reading the same source (the noise).

## 8. Where files are

| What | Ubuntu / Debian | Windows |
|---|---|---|
| Reports and the store (all data) | `~/.local/share/divide-reader/projects/default/` | `%LOCALAPPDATA%\divide-reader\projects\default\` |
| Local models | `~/.local/share/divide-reader/models/` | `%LOCALAPPDATA%\divide-reader\models\` |
| Settings (no keys) | `~/.config/divide-reader/settings.json` | `%APPDATA%\divide-reader\settings.json` |
| Local model log | `~/.local/share/divide-reader/llama-server.log` | `%LOCALAPPDATA%\divide-reader\llama-server.log` |

## 9. Command line

Ubuntu / Debian only; the Windows program has no console.

```
divide-reader models                     # models and direct download links
divide-reader download gemma-4-e4b       # download a local model
divide-reader read book.epub --provider local --model gemma-4-E4B-it-Q4_K_M.gguf
divide-reader read https://example.com --provider openrouter --model openrouter/free
divide-reader read https://example.com --provider claude --model claude-sonnet-5-5 --cap 5
divide-reader sources                    # list sources
divide-reader report 3 4                 # compare sources 3 and 4
divide-reader check                      # coverage against manual counts
```

## 10. Problems

- **The local model is very slow:** this is normal on a CPU without a graphics card. Use a smaller model (E2B) or an online model.
- **"No answer within 60 min":** the model is too slow for that unit. The program skips it and moves on.
- **Login fails:** check that you copied the whole key. With OpenRouter, finish the approval in the browser.
- **"Rate limited" on free models:** the provider limits how many calls you can make. Wait, then click **Resume last job**.
- **The report is shorter than expected:** look at "Skipped pages" in the first part of the report.

## 11. Uninstall

```
sudo apt remove divide-reader
rm -rf ~/.local/share/divide-reader ~/.config/divide-reader   # your data too, if you want
```

On Windows: **Settings → Apps → Divide Reader → Uninstall**. Your data stays in `%LOCALAPPDATA%\divide-reader` and `%APPDATA%\divide-reader`; delete those folders too if you want.

---

Licence: GPL-3.0. Bundled llama.cpp: MIT.
