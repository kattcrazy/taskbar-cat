# Taskbar Cat

Taskbar Cat is an idea I've had since August 2024.

It was inspired by [RunCat 365](https://github.com/Kyome22/RunCat365), a program that makes a running cat icon appear inside your Windows taskbar and goes faster depending on your cpu speed. My idea was more of a companion, not a pc monitor. I wanted a cat, watching me as I did whatever I was doing!

And now, just over a year later, I release Taskbar Cat for Windows. A small (or large, if you change the size) silhouetted cat that sits on top of your taskbar and watches you study, relax, or work.

## Features

- Configure cat size, vertical offset, and horizontal offset from the tray menu (type values or use the arrows)
- Choose primary monitor only or all monitors (when more than one display is connected)
- Auto start on boot (if enabled)
- Portable app (no installer/uninstaller required)

## Images

![Taskbar Cat](docs/1.gif) ![Taskbar Cat](docs/2.png)

## Configuration

| Option | Default |
| --- | --- |
| Size | 150 px |
| Vertical offset | 15 px |
| Horizontal offset | −10 px |
| Monitor mode | Primary monitor only |
| Autostart | Off (not added to Windows startup until you enable it) |

Settings are saved as YAML under your Windows profile:

- `%APPDATA%\TaskbarCat\config.yaml`

The first time you run a newer build, an older `taskbar_cat_settings.json` next to the app (if present) is migrated into that folder.

Logs: `%APPDATA%\TaskbarCat\taskbar_cat.log`

## Requirements

- Windows 11
- Taskbar not set to auto-hide

## Development

```powershell
python -m pip install -r requirements.txt
pyinstaller taskbar_cat.spec
```

The release workflow automatically builds `TaskbarCat.exe` and uploads a `.sha256` checksum file for verification.

## Portable usage

Taskbar Cat is intentionally portable:

- Run `TaskbarCat.exe` directly
- No installer is required
- To remove it, quit the app and delete the executable/folder
- If you enabled “Start on boot”, disable that option from the tray menu before deleting
