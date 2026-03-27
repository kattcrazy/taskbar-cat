# Taskbar Cat

Taskbar Cat is an idea I've had since August 2024.

It was inspired by [RunCat 365](https://github.com/Kyome22/RunCat365), a program that makes a running cat icon appear inside your Windows taskbar and goes faster depending on your cpu speed. My idea was more of a companion, not a pc monitor. I wanted a cat, watching me as I did whatever I was doing!

And now, just over a year later, I release Taskbar Cat for Windows. A small (or large, if you change the size) silhouetted cat that sits on top of your taskbar and watches you study, relax, or work.


![Taskbar Cat](docs/1.gif) ![Taskbar Cat](docs/2.png)

## Configuration

| Option | Default |
| --- | --- |
| Size | 150 px |
| Vertical offset | 15 px |
| Horizontal offset | −10 px |
| Monitor mode | Primary monitor only |
| Autostart | Off |

Settings are saved as YAML under your Windows profile at  `%APPDATA%\TaskbarCat\config.yaml`

## Requirements

- Windows 11
- Taskbar not set to auto-hide