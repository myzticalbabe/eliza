# Windows/WSL Concurrent Execution Guide for ELIZA BCC Re-Investigation

## Overview

ELIZA runs natively on **Windows** (Python 3.14t/3.15t free-threaded) and can
orchestrate concurrent workloads on **WSL2 Ubuntu** and **Kali Linux** for
BCC re-investigation. This guide documents the exact setup we use.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  WINDOWS HOST (ELIZA Controller)                                │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │ Python 3.15t    │  │ PMB Daemon      │  │ PAMS Server     │ │
│  │ Free-threaded   │  │ :8765/:8766     │  │ :21435          │ │
│  │ ELIZA CLI       │  │ Floor Proxy     │  │ Memory Bus      │ │
│  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘ │
│           │                    │                    │          │
│           ▼                    ▼                    ▼          │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  SHARED FILESYSTEM (C:\Users\clint\ ↔ /mnt/c/Users/clint)│   │
│  │  • PMB workspace: C:\Users\clint\.pmb\workspaces\...     │   │
│  │  • PAMS data: C:\Users\clint\.pams\memory_data\          │   │
│  │  • BCC raw: C:\Users\clint\bcc_raw\                      │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
           │                                    │
           ▼                                    ▼
┌─────────────────────────────┐    ┌─────────────────────────────┐
│  WSL2 UBUNTU (Worker)       │    │  KALI LINUX (Worker)        │
│  • Python 3.15t (same bin)  │    │  • Python 3.15t             │
│  • scrapling/playwright     │    │  • Full bypass tooling      │
│  • Node.js + Puppeteer      │    │  • curl_cffi                │
│  • pmb_wsl.py (PMB client)  │    │  • scrapling                │
│  • bcc_bypass.py            │    │  • pmb_wsl.py               │
└─────────────────────────────┘    └─────────────────────────────┘
```

---

## Prerequisites (One-Time Setup)

### Windows Host

```powershell
# 1. Install Python 3.15t free-threaded
#    C:\Users\clint\AppData\Local\Programs\Python\Python315\python3.15t.exe

# 2. Install PMB daemon (Windows venv)
pip install -e C:\Azazael\pams-source
# PMB daemon: pmb-ai.exe daemon start (via Startup item at logon)

# 3. PAMS server (Windows)
pip install persistent-ai-memory
# Runs as pams-server.exe via _pams_launcher.py

# 4. Shared filesystem access
#    WSL2 auto-mounts C: at /mnt/c/
#    Verify: ls /mnt/c/Users/clint/.pmb/workspaces/
```

### WSL2 Ubuntu

```bash
# 1. Python 3.15t (symlink to Windows binary)
sudo ln -sf /mnt/c/Users/clint/AppData/Local/Programs/Python/Python315/python3.15t.exe \
            /usr/local/bin/python3.15t

# 2. Install dependencies
pip install --upgrade pip
pip install scrapling playwright curl_cffi
playwright install chromium

# 3. Node.js for Puppeteer
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs
npm install -g puppeteer

# 4. PMB client (uses Windows PMB via pmb_wsl.py)
cp /mnt/c/Users/clint/llama-server/unified/pmb_wsl.py ~/pmb_wsl.py
chmod +x ~/pmb_wsl.py

# 5. ELIZA tools
cp -r /mnt/c/Users/clint/azazael/Project_ELIZA ~/eliza
cd ~/eliza && pip install -e .
```

### Kali Linux (WSL or VM)

```bash
# 1. Python 3.15t (build from source or use same symlink approach)
# 2. Full bypass tooling already available
# 3. Same PMB client approach
```

---

## Concurrent Execution Patterns

### Pattern 1: ELIZA Controller on Windows, Workers on WSL/Kali

**Windows (Controller):**
```powershell
# Start PMB daemon (if not running via Startup)
pmb-ai.exe daemon start

# Start PAMS server
python C:\Users\clint\llama-server\unified\_pams_launcher.py

# Run ELIZA controller
cd C:\Users\clint\azazael\Project_ELIZA
python -m eliza.psyche.rt_channel --demo

# Or run batch investigation
python tools/bcc_bypass.py --process-edge < edge.json
```

**WSL (Worker - Web Bypass):**
```bash
# In WSL terminal
cd ~/eliza
python tools/bcc_bypass.py --url "https://ujsportal.pacourts.us/..." --tier A --edge-idx 42 --flock COURT

# Batch process multiple edges
for edge in edges/*.json; do
    python tools/bcc_bypass.py --process-edge < "$edge" &
done
wait
```

**Kali (Worker - Heavy Bypass):**
```bash
# Same as WSL but with full tooling
cd ~/eliza
python tools/bcc_bypass.py --demo
```

### Pattern 2: Parallel Edge Processing (Free-Threaded)

```python
# tools/parallel_investigate.py
import asyncio
from tools.bcc_bypass import BCCFetchEngine, BCCEdgeProcessor, BCCEdge

async def investigate_edges(edges: list[BCCEdge], max_concurrent: int = 8):
    """Process multiple edges concurrently using free-threaded Python."""
    engine = BCCFetchEngine()
    processor = BCCEdgeProcessor(engine)
    
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def process_one(edge):
        async with semaphore:
            return await processor.process_edge(edge)
    
    results = await asyncio.gather(*[process_one(e) for e in edges])
    return results

# Run from Windows or WSL
# python tools/parallel_investigate.py edges.json
```

### Pattern 3: PMB Memory Sync Across Environments

```bash
# Windows: write to PMB
python -c "
import pmb
pmb.record_batch(items=[{'type':'fact','content':'UJS docket CP-06-CR-1234-2023 fetched'}])
"

# WSL: read from PMB (via pmb_wsl.py)
python ~/pmb_wsl.py recall "UJS docket CP-06-CR-1234-2023"

# Kali: same
python ~/pmb_wsl.py recall "UJS docket CP-06-CR-1234-2023"
```

---

## Environment Variables

```bash
# Windows (set in PowerShell profile)
$env:PMB_HOME = "C:\Users\clint\.pmb"
$env:PAMS_DATA_DIR = "C:\Users\clint\.pams\memory_data"
$env:BCC_RAW_DIR = "C:\Users\clint\bcc_raw"

# WSL/Kali (~/.bashrc or ~/.zshrc)
export PMB_HOME="/mnt/c/Users/clint/.pmb"
export PAMS_DATA_DIR="/mnt/c/Users/clint/.pams/memory_data"
export BCC_RAW_DIR="/mnt/c/Users/clint/bcc_raw"
export PAMS_ROOT="/mnt/c/Users/clint/.pams"
export AI_MEMORY_DATA_DIR="/mnt/c/Users/clint/.pams/memory_data"
```

---

## Verification Checklist

Run this on each environment to verify connectivity:

```bash
# 1. PMB connectivity
# Windows:
pmb recall "test"
# WSL/Kali:
python ~/pmb_wsl.py recall "test"

# 2. PAMS health
# Windows:
curl http://127.0.0.1:21435/api/health
# WSL/Kali:
curl http://127.0.0.1:21435/api/health

# 3. BCC bypass
# Windows:
python tools/bcc_bypass.py --demo
# WSL/Kali:
python ~/eliza/tools/bcc_bypass.py --demo

# 4. File sync
# Create on Windows, verify on WSL
echo "test" > C:\Users\clint\bcc_raw\sync_test.txt
cat /mnt/c/Users/clint/bcc_raw/sync_test.txt
```

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| PMB daemon not reachable from WSL | Verify floor proxy on :8766 (Startup item at logon) |
| PAMS port file stale | `_heal_stale_record()` runs at PAMS startup |
| `curl_cffi` not found | `pip install curl_cffi` on each env |
| Playwright chromium missing | `playwright install chromium` on each env |
| Shared filesystem permissions | Ensure Windows files not read-only; WSL needs `chmod` sometimes |
| Python version mismatch | Use same 3.15t binary via symlink on WSL/Kali |

---

## Performance Notes

- **Free-threaded Python 3.15t** enables true parallel `asyncio.gather()` across 16 cores
- **PMB floor proxy** on :8766 filters recall at 0.89 threshold (noise ≤ 0.836)
- **Concurrent workers**: 8-16 simultaneous bypass fetches typical
- **Memory**: PMB workspace ~5GB; PAMS data ~2GB; BCC raw grows per investigation

---

## Security Note

All bypass tooling is **operator-authorized for public-records investigation only**.
- No credentialed access
- No private data collection
- All fetches logged with SHA256 provenance
- Tier system ensures grade discipline

---

*Generated 2026-11-02. This is the exact concurrent execution model we use for BCC re-investigation.*