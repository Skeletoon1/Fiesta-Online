# Connect from your iPad — run Claude Code on your PC remotely

This guide sets up a **live, interactive** connection so you can sit at your iPad
(at work, on the go) and drive your home PC — editing `C:\FiestaServer` files and
running the SHN toolkit by talking to Claude Code, exactly like you do at the
desk.

**How it works:** your iPad and PC join a private network (Tailscale), then you
open a terminal on the iPad (Blink Shell) that connects to the PC and runs Claude
Code there. Nothing is exposed to the internet — both devices only make *outbound*
connections, so there's no router/firewall setup.

```
  iPad (Blink Shell) ──SSH/Mosh over Tailscale──► PC ──► runs `claude` on your files
```

---

## What you need (checklist)

**On the iPad (free App Store apps):**
- [ ] **Blink Shell** — the terminal you type into
- [ ] **Tailscale** — the connector

**On the PC:**
- [ ] **Tailscale** — same app, same account as the iPad
- [ ] **An SSH server turned on** (Windows has one built in — Step 2)
- [x] **Claude Code CLI** — you already have this
- [x] **Python** — you already have this

> The PC must be **powered on** (and not asleep) for the iPad to reach it. In
> Windows: Settings → System → Power → set "When plugged in, turn off after" to
> **Never**, or enable Wake-on-LAN if you prefer.

---

## Step 1 — Tailscale on both devices

1. Install Tailscale on the **PC** and sign in (a free personal account is fine).
2. Install Tailscale on the **iPad** and sign in with the **same account**.
3. On the PC's Tailscale app, note its **Tailscale IP** — it looks like
   `100.x.y.z`. (You can also see every device's IP in the Tailscale admin
   console.) You'll use this address to connect.

That's the whole network. The two devices can now reach each other from anywhere.

---

## Step 2 — Turn on the SSH server on the PC

Blink connects *to* your PC, so the PC needs to accept SSH. Windows includes one.

**Easy way (Settings):** Settings → System → **Optional features** → **Add a
feature** → search **"OpenSSH Server"** → Install.

**Or PowerShell (Run as Administrator):**
```powershell
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
Start-Service sshd
Set-Service sshd -StartupType Automatic
```

That last line makes SSH start automatically every time the PC boots.

Find your **PC username** (you'll need it to log in):
```powershell
whoami
```
(It prints something like `desktop-abc\user` — the part after `\` is your
username.)

---

## Step 3 — Which setup do you have? (the 10-second test)

This decides whether you get **Mosh** (the feature that keeps your session alive
when the iPad sleeps or switches Wi-Fi/cellular). Open the terminal where you
normally run `claude` and type:

```
uname -a
```

- **Prints a line containing `Linux` and `microsoft-standard-WSL2`** → you're in
  **WSL**. Follow **Branch A** (full Mosh — the good one).
- **Errors with `'uname' is not recognized...`** → you're on **native Windows**.
  Follow **Branch B**.

---

### Branch A — WSL (full Mosh)

You're set up for the best experience.

1. In your WSL terminal, install Mosh once:
   ```bash
   sudo apt update && sudo apt install -y mosh
   ```
2. You'll connect from Blink straight into WSL (see Step 4) and Mosh will keep the
   session alive across iPad sleeps and network changes.
3. Once connected, just run:
   ```bash
   claude
   ```
   …and talk to Claude exactly like at your desk. To run the toolkit directly:
   ```bash
   python3 fiesta_shn.py selftest
   ```

> Note: `mosh` connects to the machine that runs `mosh-server`. If your SSH lands
> on Windows first, enter WSL with `wsl` before starting `mosh`/`claude`, or
> configure SSH to land directly in WSL. If unsure, connect with plain `ssh`
> first (Branch B steps), run `wsl`, then `claude` — and add Mosh later.

---

### Branch B — Native Windows (plain SSH)

Blink works great here over standard SSH. The only catch: if your iPad sleeps or
changes networks, the connection drops — you just reconnect and keep going.

1. Connect from Blink (Step 4).
2. Once you see the PC prompt, run:
   ```
   claude
   ```
   or run the toolkit directly:
   ```
   python fiesta_shn.py selftest
   ```

**Want Mosh later?** Mosh needs a Linux helper that doesn't run natively on
Windows, so you'd install **WSL** (`wsl --install` in an admin PowerShell,
reboot), then follow **Branch A**. Optional — plain SSH is perfectly usable to
start.

---

## Step 4 — First connection in Blink

1. Open **Blink Shell** on the iPad.
2. Type the connect command using your PC username and its Tailscale IP from
   Step 1:
   ```
   ssh YOURUSERNAME@100.x.y.z
   ```
   (Branch A with Mosh installed and SSH landing in WSL: use `mosh
   YOURUSERNAME@100.x.y.z` instead.)
3. The first time, it asks to trust the host (say yes) and then for your **PC
   login password**. Enter it — you're in.

**Password is fine to start.** If you'd rather not type it each time, Blink can
make an SSH key (`config` → Keys → new key), and you add the **public** key to
the PC at `C:\Users\YOURNAME\.ssh\authorized_keys`. Optional polish, not required.

---

## Step 5 — Use it

You now have your PC's command line on your iPad. From here:
- `claude` → start an interactive Claude Code session on your PC (talk in plain
  English; Claude edits your real files).
- `cd` to wherever you keep the toolkit and run `python fiesta_shn.py decode
  Item.shn`, etc.
- Confirm the whole link works end-to-end with:
  ```
  python fiesta_shn.py selftest      (or python3 in WSL)
  ```
  Seeing **`SELFTEST PASSED`** means Claude's tooling is running on your PC, from
  your iPad. 🎉

---

## Security notes

- Tailscale is **outbound-only** — no ports opened, nothing exposed to the public
  internet. Only devices on *your* Tailscale account can reach the PC.
- Keep your tailnet private (don't share node keys). Use a **strong PC password**,
  or set up the SSH key above.
- This is a full login to your PC — treat the access like you'd treat sitting at
  the machine.

---

## Troubleshooting

- **Can't connect / times out** → Check Tailscale shows "Connected" on *both*
  devices, and confirm you used the PC's `100.x.y.z` Tailscale IP (not its home
  Wi-Fi IP). Make sure the PC is awake.
- **"Connection refused"** → the SSH server isn't running. On the PC:
  `Start-Service sshd` (Step 2).
- **`'uname' is not recognized`** → that's expected on native Windows — you're
  **Branch B**.
- **Mosh won't connect** → the PC has no `mosh-server`, meaning you're not in WSL.
  Use plain `ssh` (Branch B), or install WSL + Mosh for Branch A.
- **Asks for a password every time** → set up the SSH key in Step 4.
