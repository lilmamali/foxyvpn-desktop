[README.md](https://github.com/user-attachments/files/33892682/README.md)  فارسی | English
# FoxyVPN Desktop

A graphical Windows client for the Firefox built-in VPN (via the `foxyvpn` pip package).
Each user logs in with their own Firefox Account — the password is asked only on first
sign-in and **never stored** on disk.

> 🦊 Personal use, distributed to friends as a portable `.exe`.

---

## ✨ Features

- 🔐 **Per-user Firefox Account login** — password never persisted, only the OAuth token
- 🌍 **33 country servers** (auto-loaded from the engine via `--list-servers`)
- 🔄 **Automatic reconnect** on unhealthy tunnel (port of the Android client logic)
- 🚦 **HTTP→SOCKS5 bridge on `127.0.0.1:8080`** so all Windows apps route through the VPN
- 📊 **Monthly data usage panel** with progress bar (locally tracked, Mozilla sync for the cap)
- 🛡️ **Refusal cache with exponential backoff** (ported from the Android client)
- 🔄 **Auto-updater** — checks GitHub Releases on launch, offers to download & install
- 🧹 **Clean shutdown** — kills engine subprocesses, restores Windows proxy on exit/crash

---

## 📦 Project Structure (distributed)

```
FoxyVPN-Pack/
├── FoxyVPNDesktop.exe   ← GUI (PySide6, windowed)
├── foxyvpn-engine.exe   ← Engine (console, --collect-all foxyvpn)
└── README.txt           ← Persian user guide
```

Both exes must sit in the **same folder**.

---

## 🛠️ Build (developer only)

### 1) Create venv and install deps

```cmd
cd C:\Users\<you>\fox
python -m venv venv
venv\Scripts\activate
pip install PySide6 psutil pyinstaller foxyvpn
```

### 2) Build the engine

```cmd
venv\Scripts\pyinstaller --onefile --name foxyvpn-engine ^
    --collect-all foxyvpn ^
    --hidden-import foxyvpn.__main__ ^
    venv\Lib\site-packages\foxyvpn\__main__.py
```

### 3) Build the GUI

```cmd
venv\Scripts\pyinstaller --onefile --windowed --name FoxyVPNDesktop app.py
```

Output: `dist\FoxyVPNDesktop.exe`. Drop it next to `foxyvpn-engine.exe`.

---

## 🚀 Usage (end-user)

1. Place `FoxyVPNDesktop.exe` and `foxyvpn-engine.exe` in the same folder.
2. Run `FoxyVPNDesktop.exe`.
3. Enter your Firefox Account email → press **Connect**.
4. A console window opens — enter your password there. It closes automatically.
5. Status turns green → **CONNECTED**.
6. Tick **"Route all Windows apps through the VPN"** to route browsers through it.

Returning users connect automatically (cached OAuth token).

---

## 📊 Data Usage Panel

- The progress bar shows monthly data usage (out of 50 GB for free accounts).
- Click **↻ Sync with Mozilla** to refresh the monthly cap from Mozilla's API.
- Usage is tracked locally via `psutil` I/O counters; resets to the cap on the 1st of each month.
- Stored in `%LOCALAPPDATA%\FoxyVPNDesktop\usage.json`.

---

## ⚠️ Limitations

- **50 GB monthly cap** on free Firefox accounts.
- **Country mismatch**: Mozilla's edge uses anycast — exit IP country may differ from selected.
- **Mozilla service outages**: if `--list-servers` fails, only "Recommended" is offered.
- **Data tracking is per-device**: usage from other devices on the same account isn't counted.

---

## 🔧 Settings

| Setting | Where |
|---------|-------|
| OAuth tokens | `%USERPROFILE%\.foxyvpn-tokens.json` |
| Status file | `%LOCALAPPDATA%\FoxyVPNDesktop\status.json` |
| Usage file | `%LOCALAPPDATA%\FoxyVPNDesktop\usage.json` |
| Engine status | `%LOCALAPPDATA%\FoxyVPNDesktop\proxy-state.json` |

---

## 🔄 Release Workflow (maintainer)

1. Edit code in `app.py`.
2. Bump `APP_VERSION` (e.g. `"1.0"` → `"1.1"`).
3. Rebuild: `pyinstaller --onefile --windowed --name FoxyVPNDesktop app.py`.
4. Create a new GitHub Release with tag `v1.1`, attach `FoxyVPNDesktop.exe`.
5. Update `version.json` on `main` branch:
   ```json
   { "version": "1.1", "asset": "FoxyVPNDesktop.exe" }
   ```
6. Existing clients will auto-prompt users to update on next launch.

---

## 📝 License

MIT — see [LICENSE](LICENSE).
