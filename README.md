# ComCare — ADRD Caregiver Assistant

ComCare is a personal web app that helps caregivers of people with Alzheimer's Disease and Related Dementias (ADRD) track observations, prepare for doctor visits, and get AI-powered support — all privately on their own computer.

---

## What You'll Need

Before installing ComCare, you need Python, plus **one** AI option:

1. **Python 3.10 or newer** — the programming language ComCare runs on
2. **An AI backend** — pick one:
   - **OpenAI API** — cloud-based, uses your own OpenAI API key. Simplest to set up, no extra software to install. Usage is billed to your OpenAI account.
   - **Ollama** — runs the AI privately on your own machine (no data sent to the cloud). Free, but requires installing Ollama and downloading a ~5GB model.

Both are described below — use whichever one you prefer.

---

## Step 1 — Install Python

### Mac
1. Open your browser and go to **https://www.python.org/downloads/**
2. Click the big yellow **"Download Python 3.x.x"** button
3. Open the downloaded file and follow the installer (click Continue → Agree → Install)
4. When it finishes, open the **Terminal** app (search "Terminal" in Spotlight with ⌘ Space)
5. Type `python3 --version` and press Enter — you should see something like `Python 3.12.3`

### Windows
1. Go to **https://www.python.org/downloads/**
2. Click **"Download Python 3.x.x"**
3. Open the installer — **important: check the box that says "Add Python to PATH"** before clicking Install
4. Click **Install Now** and wait for it to finish
5. Open the **Command Prompt** (search "cmd" in the Start menu)
6. Type `python --version` and press Enter — you should see `Python 3.x.x`

---

## Step 2 — Choose Your AI Backend

### Option A — OpenAI API (recommended if you don't want to install anything else)

1. Go to **https://platform.openai.com/api-keys** and sign in (or create an account)
2. Click **Create new secret key**, name it (e.g. "ComCare"), and copy the key that starts with `sk-...`
3. Keep it somewhere safe — you'll paste it into ComCare's Settings in Step 5, and OpenAI won't show it to you again
4. Note: this uses your OpenAI account's billing. Small models like `gpt-4o-mini` (the default) are inexpensive for this kind of use.

You can skip straight to Step 3 — no extra software to install.

### Option B — Ollama (fully private, runs on your machine)

Ollama runs a powerful AI model privately on your computer. Nothing leaves your machine.

1. Go to **https://ollama.com/download**
2. Click the download button for your system (Mac or Windows)
3. Open the downloaded file and install it (drag to Applications on Mac, or run the installer on Windows)
4. Once installed, open **Terminal** (Mac) or **Command Prompt** (Windows)
5. Type the following and press Enter — this downloads the AI model (about 5 GB, takes a few minutes):

   ```
   ollama pull llama3.1
   ```

6. When it finishes, type:

   ```
   ollama serve
   ```

   You should see a message like `Listening on 127.0.0.1:11434`. Leave this window open — Ollama needs to stay running.

> **Tip:** On Mac, Ollama also adds a small icon to your menu bar. If you see it there, Ollama is already running and you can skip the `ollama serve` step.

---

## Step 3 — Download ComCare

### Option A — If you received a zip file
1. Unzip the file (double-click on Mac, or right-click → Extract All on Windows)
2. You'll get a folder called **ComCare** — move it somewhere easy to find, like your Desktop or Documents

### Option B — From GitHub
1. Go to the ComCare GitHub page
2. Click the green **"Code"** button → **"Download ZIP"**
3. Unzip and move the **ComCare** folder to your Desktop or Documents

---

## Step 4 — Install ComCare's Dependencies

ComCare needs a few small Python libraries. This is a one-time step.

### Mac
1. Open **Terminal**
2. Type `cd ` (with a space after it), then drag the **ComCare folder** into the Terminal window — the path fills in automatically. Press Enter.
3. Type this and press Enter:

   ```
   pip3 install -r requirements.txt
   ```

4. Wait for it to finish. You'll see packages being downloaded and installed.

### Windows
1. Open **Command Prompt**
2. Type `cd ` (with a space), then type the path to your ComCare folder. For example:

   ```
   cd C:\Users\YourName\Desktop\ComCare
   ```

3. Press Enter, then type:

   ```
   pip install -r requirements.txt
   ```

4. Press Enter and wait for it to finish.

---

## Step 5 — Run ComCare

Every time you want to use ComCare, do the following:

### Mac
1. If you're using Ollama, make sure it's running (check menu bar, or run `ollama serve` in a Terminal). Skip this if you're using OpenAI.
2. Open a new **Terminal** window
3. Navigate to the ComCare folder (same `cd` step as above)
4. Type this and press Enter:

   ```
   uvicorn app:app --reload
   ```

5. You'll see output ending in something like `Application startup complete.`
6. Open your browser and go to: **http://localhost:8000**

### Windows
1. If you're using Ollama, make sure it's running (system tray, or `ollama serve` in a separate Command Prompt window). Skip this if you're using OpenAI.
2. Open a new **Command Prompt**
3. Navigate to the ComCare folder
4. Type this and press Enter:

   ```
   uvicorn app:app --reload
   ```

5. Open your browser and go to: **http://localhost:8000**

> **To stop ComCare:** Click in the Terminal/Command Prompt window and press **Ctrl + C**

---

## First-Time Setup Inside the App

When ComCare opens in your browser:

1. Click **Settings** (gear icon at the bottom of the left sidebar)
2. Fill in your patient's profile:
   - Name, age, and diagnosis
   - Primary physician's name
   - Next visit date
3. Under **AI Backend**, choose the option that matches what you set up in Step 2:
   - **OpenAI** — paste your API key (starts with `sk-...`), and optionally change the model (default: `gpt-4o-mini`)
   - **Ollama (Local)** — set the model name to `llama3.1:latest`
4. Click **Save Settings**, then click **Test Connection** to confirm it's working
5. That's it — ComCare is ready to use!

---

## Using the App (Quick Guide)

| Page | What it does |
|------|-------------|
| **AI Chat** | Talk naturally about what you're observing. ComCare listens, asks follow-up questions, and suggests saving records. After a conversation, click **Summarize our chat** to get a structured recap. |
| **Home Dashboard** | See recent records, upcoming visit date, and quick stats. |
| **Enter a Record** | Manually log an observation using one of 6 structured record types. |
| **Visit Summary** | Choose a specialty (e.g. Neurology), describe the visit purpose, and generate a polished summary letter for your care team. The output is editable — you can revise it before printing or copying. |
| **Settings** | Update patient profile and AI backend. |

---

## Install on iPhone as an App (Optional)

You can add ComCare to your iPhone home screen so it opens like a real app (full screen, no browser bar).

**Requirements:** ComCare must be running on a computer connected to the same Wi-Fi as your iPhone.

1. Find your computer's local IP address:
   - **Mac:** System Settings → Wi-Fi → click your network → look for the IP (e.g. `192.168.1.42`)
   - **Windows:** Open Command Prompt, type `ipconfig`, look for "IPv4 Address"

2. Start ComCare with this command instead (replace `0.0.0.0` to allow network access):

   ```
   uvicorn app:app --host 0.0.0.0 --reload
   ```

3. On your iPhone, open **Safari** and go to: `http://192.168.1.42:8000` (use your computer's IP)

4. Tap the **Share button** (box with arrow pointing up) → **Add to Home Screen** → **Add**

5. ComCare now appears on your home screen and opens full-screen.

---

## Troubleshooting

**"command not found: python3" or "pip3"**
→ Python wasn't installed correctly. Repeat Step 1, making sure to check "Add Python to PATH" on Windows.

**"OpenAI API key not configured" or a 401/403 error in the app**
→ Double-check the key was pasted correctly into Settings (no extra spaces), and that the key hasn't been revoked at platform.openai.com/api-keys.

**"Cannot reach AI backend" error in the app**
→ If using Ollama: it isn't running. Open a Terminal and type `ollama serve`, then try again.
→ If using OpenAI: check your internet connection.

**The page won't load at http://localhost:8000**
→ ComCare server isn't running. Make sure you ran `uvicorn app:app --reload` and it shows "Application startup complete."

**AI responses are very slow**
→ With Ollama, this is normal on first use — the model is loading into memory. Subsequent responses will be faster. With OpenAI, responses should typically come back within a few seconds.

**"No module named 'fastapi'" or similar**
→ The dependencies weren't installed. Go back to Step 4 and run `pip3 install -r requirements.txt` again.

---

## Your Data & Privacy

- All your care records are stored in a file called `comcare.db` inside the ComCare folder — on your computer only.
- When using Ollama, your conversations never leave your machine.
- When using OpenAI, your conversation messages are sent to OpenAI's API (governed by OpenAI's own privacy policy) in order to generate a reply — your API key and the rest of your settings still stay in `comcare.db` on your computer.
- To back up your data, copy the `comcare.db` file to a safe location.

---

## Getting Help

If you run into problems not covered above, the most helpful information to share is the error message shown in the Terminal/Command Prompt window where ComCare is running.
