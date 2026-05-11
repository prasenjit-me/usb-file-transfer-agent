# I Built an AI That Manages USB File Transfers — Because I Was Tired of Doing It Manually

Every photographer, field engineer, or office worker knows this moment.

You've just come back from an event. You have a USB drive with 400 files on it. You need to pull out all the photos, leave the videos, copy some PDFs to your desktop, and move a specific report to a project folder — without mixing anything up.

You plug in the USB. Open File Explorer. Start dragging. Delete something by mistake. Undo. Drag again. Open the wrong folder. Start over.

Twenty minutes later, you're done. And you're annoyed.

This happens to me constantly. So I built something to fix it.

---

## The Tool: USB File Transfer Agent

It's a desktop app for Windows that lets you talk to your USB drive like you'd talk to a colleague.

Instead of clicking and dragging, you type:

> *"Move fuelcard-MayUpdates.zip to Desktop"*

And it's done.

Or:

> *"Copy all the .jpg files to my Pictures folder"*

Done in seconds.

The app shows a dual-panel file browser — your PC on the left, your USB drive on the right — so you can see exactly what's where. You can still click and transfer manually if you want, but the AI handles the complex or repetitive jobs.

---

## How It Works (Without the Jargon)

Under the hood, it's powered by **Groq's API** running **Llama 3.3 70B** — one of the fastest open LLMs available right now. When you send a message, the AI doesn't just generate text. It decides which tool to call:

- **list_usb_drives** — detects all connected USB drives and their free space
- **list_files** — browses any directory on your PC or USB
- **transfer_files** — copies or moves files, either by exact filename or by file type

The AI reads your current folder paths from context, so it always knows where "USB" and "Desktop" actually point to on your machine.

---

## The Engineering Problem That Took Longest to Solve

This wasn't a simple wrapper. The hardest part was making the AI **reliable**, not just impressive in a demo.

**Problem 1: "Move this file" moved ALL files of that type.**

When I said *"move mcp article.md to USB"*, the model correctly identified `.md` as the extension — then transferred every `.md` file on my Desktop. That's not what I asked.

Fix: I added a `filename` parameter to the transfer tool. Now the model can target a single exact file by name, not just a file type. The prompt also explicitly instructs it: *"when the user names a specific file, use filename, not extension."*

**Problem 2: The app crashed permanently after one bad AI response.**

Some prompts caused the model to generate a malformed tool call — XML-style syntax instead of proper JSON. The API returned a 400 error. Fair enough. But the app kept crashing on every message *after* that too, because the failed user message was already committed to the conversation history, leaving it in a broken state.

Fix: The conversation history is now only updated *after* a fully successful round-trip. A failed call leaves the history completely clean. Plus, on a `tool_use_failed` error, the app silently retries with tools disabled so the model can at least give a useful text response.

**Problem 3: "Revert that" or "clear" got sent to the AI.**

The model tried to undo a file transfer — which it can't do — and hallucinated a response saying it had moved a bunch of files it never touched. "Clear" was treated as a file operation.

Fix: These are intercepted in the GUI before reaching the AI. "Clear" wipes the chat and resets the conversation history. The system prompt explicitly tells the model it cannot undo transfers.

---

## The Stack

- **Python** + **CustomTkinter** — dark-themed native desktop GUI, no browser, no Electron
- **Groq API** (Llama 3.3 70B) — fast inference, OpenAI-compatible
- **psutil** + **ctypes** — USB drive detection and Windows volume label reading
- Fully **offline-capable UI** — only the AI calls require internet

The whole thing is ~500 lines of Python across 3 files.

---

## Why This Matters Beyond the Demo

The real insight here is not the specific app — it's the pattern.

We spend enormous amounts of time on file management: moving, organising, renaming, copying across devices. It's mechanical work that requires just enough attention to be annoying and just enough variation to resist simple automation.

AI-assisted tooling changes that equation. You describe the outcome you want. The tool figures out the steps.

This is the same pattern behind AI coding assistants, AI data pipelines, AI customer support. The interface changes. The principle doesn't: **replace mechanical decision-making with a natural language intent layer.**

The USB drive is a small, tangible example of a much larger shift.

---

## The Code

The project is open source: **github.com/prasenjitdutta198/usb-agent**

If you want to run it: clone the repo, add your Groq API key to `.env`, run `setup_and_run.bat`. That's it.

I'd love to hear from anyone who builds something similar or has ideas for what to add next — delete confirmation, folder sync, scheduled transfers, offline LLM support. The foundation is solid.

---

*Built with Python, Groq, and a lot of frustration at File Explorer.*

\#Python #AI #LLM #OpenSource #Groq #Automation #WindowsApp #BuildInPublic
