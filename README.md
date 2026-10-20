FoxyVPN Desktop 🦊
A clean, personal Windows client for the Firefox Built-in VPN service.

FoxyVPN Desktop wraps the foxyvpn engine with a simple dark-themed GUI: connectwith your own Firefox Account, pick a country, and route all your apps through alocal proxy — no technical setup required.

⚠️ Unofficial project — not affiliated with or endorsed by Mozilla.Use it only with an account you are authorized to use, and in accordance withMozilla's terms of service.

✨ Features
🔑 Your own account — every user signs in with their own Firefox Account.The password is asked only once and never stored.
🔁 Silent reconnect — after the first sign-in, a session token is cachedlocally and later connections are fully automatic.
🌍 Country picker — all Firefox Built-in VPN server locations, plus theauto-selected "Recommended" server.
🖥️ All apps, not just Firefox — an HTTP→SOCKS bridge is published as theWindows system proxy, so Chrome, Edge, Opera and most desktop apps are tunneledautomatically. SOCKS5 is also available directly for apps like Telegram.
🩺 Self-healing tunnel — background health checks detect a wedged tunneland restart the engine automatically.
🚫 Smart refusal cache — destinations rejected by the upstream edge (adand tracking domains) are refused locally with exponential backoff instead ofwasting round trips.
🧹 Clean disconnect — the engine and all child processes are reliablykilled, and the system proxy is always restored on exit.
⬆️ Auto-updater — the app checks GitHub for new releases and offers toupdate itself with one click.
📦 Download
Grab the two executables from the Releases page:

File	Purpose
FoxyVPNDesktop.exe	The graphical interface
foxyvpn-engine.exe	The VPN engine (required)
Both files must stay in the same folder.

🚀 Usage
Run FoxyVPNDesktop.exe
Enter your own Firefox Account email
Press Connect
First time: a console window opens — enter your email and passwordthere, and keep it open until you disconnect.
After that: connections are automatic, with no prompts.
Wait for CONNECTED — browsers and most apps are tunneled automatically.
Manual app configuration
App type	Address
SOCKS5-aware apps (Telegram, etc.)	SOCKS5 → 127.0.0.1:1080
HTTP-proxy-aware apps	HTTP → 127.0.0.1:8080
🛠 How it works
Your apps   │   ├─ System proxy (HTTP) ──►  HTTP bridge :8080 ──┐   ├─ Direct SOCKS5 ───────────────────────────────┤   │                                               ▼   │                            foxyvpn-engine (SOCKS5 :1080)   │                                               │   │                            HTTP/2 tunnel (proxy-pass)   │                                               ▼   └─────────────────────►  Firefox VPN edge (Fastly MASQUE)
ℹ️ Notes & limits
Requires the Firefox Built-in VPN service on your account(~50 GB monthly data limit, resets on the 1st).
