# Desktop Cat

A little white-and-grey cat who lives on the Windows desktop. She naps, wanders, keeps a to-do
list, and shows messages from a Google Sheet.

## Install

1. Download **DesktopCat-windows** from the latest run on the **Actions** tab and unzip it.
2. Put `DesktopCat.exe` somewhere permanent and double-click it. If Windows warns about it, click
   **More info → Run anyway**.
3. Right-click the cat (or the paw in the tray) and tick **Start with Windows**.

## Using her

- Hover over her for a little trick; click her for a message; drag her anywhere.
- Right-click her for the menu: to-do note, Sleep Mode (tucked under a blanket), Quiet Mode,
  reminders, size, and more.

## Messages

She reads the Google Sheet linked in `windows/data/config.json`. Edit the sheet any time:

- **Messages** tab: her everyday lines, one per row.
- **Live** tab: type a new line and it pops up on his screen in about 10 seconds.
- **Control** tab: **Nudge** (a message that stays up until clicked), **Check-in times**, and
  **From** (the name messages are signed with).

Keep the sheet shared as *Anyone with the link → Viewer*, and keep this repo private.

## Building

Pushing to `main` builds `DesktopCat.exe` on GitHub. To build on a Windows PC instead, install
Python 3.11+ and run `windows\build.bat`.
