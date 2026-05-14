# Freedom EVO Integration Guide

How to test the galago EVO driver on a Windows PC with real EVOware installed.

---

## 1. Prerequisites

| Component | Requirement | Check |
|-----------|-------------|-------|
| OS | Windows 10/11 (COM is Windows-only) | — |
| EVOware | 2.0+ installed and licensed | Launch EVOware GUI — can you open the editor? |
| Python | 3.9+ | `python --version` |
| Git | Any recent version | `git --version` |
| Network | Pi → PC reachable, or code synced via git | `ping <pi-ip>` |

---

## 2. Get the Code

Clone from your fork to your PC:

```powershell
cd C:\projects
git clone https://github.com/Le7on/galago-tools.git
cd galago-tools
git checkout main
```

If the fork doesn't have the latest, push from the Pi first:

```bash
# On the Pi
cd /home/pi/galago-tools
git remote add myfork git@github.com:Le7on/galago-tools.git
git push myfork main
```

---

## 3. Install Dependencies

```powershell
cd C:\projects\galago-tools

# Core deps
pip install comtypes grpcio grpcio-tools protobuf appdirs pydantic

# Dev deps (for tests)
pip install pytest
```

**Verify comtypes works:**

```powershell
python -c "import comtypes; print('comtypes OK')"
```

---

## 4. Build Proto Files

The pb2 files on the Pi were compiled for Linux — rebuild for Windows:

```powershell
cd C:\projects\galago-tools

# Build just freedom_evo (doesn't need the full tool_base)
python -m grpc_tools.protoc `
  -I interfaces/tools/grpc_interfaces `
  --python_out=tools/grpc_interfaces `
  --grpc_python_out=tools/grpc_interfaces `
  interfaces/tools/grpc_interfaces/freedom_evo.proto
```

---

## 5. Quick Import Check

```powershell
python -c "from tools.freedom_evo import ESCBuilder; print('Import OK,', len(ESCBuilder()), 'steps')"
# Expected: Import OK, 0 steps
```

Run the unit tests (pure Python, no COM needed):

```powershell
pytest tools/freedom_evo/test_script_builder.py -v
# Expected: 28 passed
```

---

## 6. Verify EVOware COM Registration

EVOware registers two COM servers. Check they exist:

```powershell
# Method 1: Try creating the object in Python
python -c "
import comtypes.client
sys = comtypes.client.CreateObject('evoapi.system')
print('evoapi.system OK, GetStatus=', sys.GetStatus())
"

# Method 2: Check registry
Get-ChildItem -Path "HKLM:\SOFTWARE\Classes" -Recurse | 
  Where-Object { $_.PSChildName -like "*evoapi*" }
```

If `CreateObject('evoapi.system')` fails:
- EVOware may not have been run at least once (Evoapi.exe is self-registering)
- Launch EVOware GUI normally, then close it, retry
- Or run `"C:\Program Files\Tecan\EVOware\Evoapi.exe" /regserver` as admin

---

## 7. Simulation Mode Test (Safe First Step)

Before touching real hardware, verify the server logic works:

```powershell
cd C:\projects\galago-tools

# Start the server in a terminal
python -m tools.freedom_evo.server --port 50051
```

In another terminal, test via Python directly (no gRPC client needed):

```powershell
# test_sim.py — paste into a file
from tools.freedom_evo.driver import FreedomEVODriver

driver = FreedomEVODriver(
    user_name="admin",
    password="admin",
    plus_mode=False,
    simulate=True,
)

# Test lifecycle
assert driver.logon()
assert driver.initialize()
print("System status:", hex(driver.get_system_status()))

# Test info query
info = driver.get_system_info()
print(f"EVOware {info.version}, serial={info.serial_number}")

# Test script execution
from tools.freedom_evo import ESCBuilder
b = ESCBuilder()
b.add_comment("Integration test")
b.add_aspirate("Src", "S1", "MTP", 1, "A1", 50.0, "Water", "200ul", 1)
b.add_dispense("Dst", "D1", "MTP", 1, "B1", 50.0, "Water", "200ul", 1)
esc = b.build()
print("ESC script:\n", esc)

ok = driver.run_esc_script(esc, "test_integration.esc")
print("Script executed:", ok)

# Cleanup
driver.stop()
driver.logoff()
driver.close()
print("All simulation tests passed")
```

```powershell
python test_sim.py
# Expected: all green, ESC script printed
```

---

## 8. Real Mode Test (With Hardware)

**⚠️ Make sure nobody is using the instrument. The robot will move.**

### 8.1 Config

Update `test_real.py` with your actual EVOware credentials:

```python
from tools.freedom_evo.driver import FreedomEVODriver

driver = FreedomEVODriver(
    user_name="YOUR_EVOWARE_USER",      # <-- CHANGE
    password="YOUR_EVOWARE_PASSWORD",   # <-- CHANGE
    plus_mode=False,                     # True if you have EVOware Plus
    simulate=False,                      # REAL MODE
    hide_gui=False,                      # Keep GUI visible for first test
)

print("Driver created:", repr(driver))
```

### 8.2 Step-by-Step (Run Each Block Separately)

```python
# ── Step 1: Logon ──────────────────────────────────────────────
driver.logon()
print("Status:", hex(driver.get_system_status()))
# Expect: status includes STATUS_LOADING or higher

# ── Step 2: Initialize (blocks ~30s while hardware homes) ─────
driver.initialize()
print("Initialized:", driver._initialized)
print("Status:", hex(driver.get_system_status()))
# Expect: STATUS_INITIALIZED flag set

# ── Step 3: Query system info ─────────────────────────────────
info = driver.get_system_info()
print(f"EVOware v{info.version} | Plus={info.plus_mode} | Serial={info.serial_number}")

# ── Step 4: Query devices ─────────────────────────────────────
n = driver.get_device_count()
print(f"{n} devices found")
for i in range(n):
    name, ver = driver.get_device(i)
    print(f"  [{i}] {name} (driver v{ver})")

# ── Step 5: Query liquid classes ──────────────────────────────
n = driver.get_lc_count()
print(f"{n} liquid classes")
for i in range(min(n, 5)):
    lc = driver.get_lc_info(i)
    if lc:
        print(f"  [{i}] {lc.name} default={lc.is_default}")

# ── Step 6: Build and run a simple ESC script ─────────────────
from tools.freedom_evo import ESCBuilder

b = ESCBuilder()
b.add_comment("Integration test — real hardware")
b.add_get_diti(1)                                 # Pick up 1 tip
b.add_aspirate("Src", "S1", "MTP", 1, "A1",      # <-- replace with YOUR
    10.0, "Water", "200ul", 1)                    #      actual rack/liquid
b.add_dispense("Dst", "D1", "MTP", 1, "B1",
    10.0, "Water", "200ul", 1)
b.add_wash("Wash1")
b.add_drop_diti("TipRack", "TR1", "DiTi_200ul", 1)

esc = b.build()
print("Running script:\n", esc)

ok = driver.run_esc_script(esc, "integration_test.esc")
print("Script completed:", ok)

# ── Step 7: Cleanup ───────────────────────────────────────────
driver.stop()
driver.logoff()
driver.close()
print("Done")
```

### 8.3 What to Watch

| Signal | Meaning | Action |
|--------|---------|--------|
| `STATUS_LOGON_ERROR` in status | Wrong credentials | Check user/password |
| `STATUS_NOLICENSE` | Hardlock not found | Is the license dongle plugged in? |
| Script times out | Robot waiting for user interaction | Check EVOware GUI for dialog boxes |
| `EVO_E_ONLY_IN_PLUS` error | Trying Plus-only function in Standard | Set `plus_mode=False` |
| `EVO_E_SYSTEM_COMMAND_EXECUTION` | Invalid .esc command syntax | Review the generated ESC script |
| Physical error (tip crash etc.) | Wrong rack/labware configuration | Halt immediately, verify deck layout |

---

## 9. Troubleshooting

### COM Registration Issues

**Symptom:** `CreateObject('evoapi.system')` → `COMError`

```powershell
# Check if Evoapi.exe exists
Test-Path "C:\Program Files\Tecan\EVOware\Evoapi.exe"
Test-Path "C:\Program Files (x86)\Tecan\EVOware\Evoapi.exe"

# Re-register
& "C:\Program Files\Tecan\EVOware\Evoapi.exe" /regserver
```

### Script Not Found

**Symptom:** `PrepareScript` fails with "file not found"

EVOware looks for scripts in `Database\Scripts\` relative to the EVOware installation. The driver writes temp .esc files to the system temp directory — if EVOware can't read from there, set up a shared directory or write to EVOware's Scripts folder.

### Script Execution Hangs

**Symptom:** `run_esc_script` never returns

- Check EVOware GUI: is there an error dialog? Click it to see.
- Check if the script requires a carrier/labware that doesn't exist on deck
- Run `driver.get_script_status(script_id)` to get the current state
- If `SS_ERROR` (0x07), an error dialog is open — needs manual intervention

### Hidden GUI Risks

If you set `hide_gui=True`, EVOware error dialogs are invisible. You MUST handle them programmatically via `EVOApiErrorMsg.dll` / `IReceiveMsg`. For first tests, keep `hide_gui=False`.

---

## 10. Running the Full gRPC Server

Once driver-level tests pass, run the gRPC server:

```powershell
python -m tools.freedom_evo.server --port 50051
```

Configure it via gRPC client:

```python
import grpc
from tools.grpc_interfaces.freedom_evo_pb2 import Command, Config

# Send Config first
config = Config(
    evoware_user="admin",
    evoware_password="admin",
    plus_mode=False,
    simulate=False,
    hide_gui=False,
    remote_mode=False,
)
# ... gRPC Configure call ...

# Then Logon
cmd = Command(logon=Command.Logon(
    user_name="admin", password="admin",
    plus_mode=False, simulation=False,
))
# ... gRPC ExecuteCommand ...
```

---

## 11. Safety Checklist

Before running on real hardware:

- [ ] Simulation mode tests pass (28/28)
- [ ] No one else is using the instrument
- [ ] Deck is clear of obstacles
- [ ] Waste is empty, tips are loaded
- [ ] Emergency stop is reachable
- [ ] First script uses small volumes (≤10 µL)
- [ ] First script uses minimal arm movement
- [ ] EVOware GUI is visible (`hide_gui=False`)
- [ ] You know where the hardware STOP button is
