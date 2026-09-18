<img width="1308" height="1025" alt="image" src="https://github.com/user-attachments/assets/8820ab77-545d-4a87-b93d-e47d4e33ad87" />

System settings for Hyprland. Themes opens GTK Theme Editor; Configs edits `~/configs`.

- WiFi
    - requires nmcli (NetworkManager)
    - connect / disconnect / forget known networks
    - autoconnect
    - shows IP, subnet, gateway, and DNS when connected
- Ethernet
    - requires nmcli (NetworkManager)
    - wired interfaces (skips docker/veth bridges)
    - connect / disconnect, autoconnect
    - IPv4 Automatic (DHCP) or Manual (address / gateway / DNS)
- Bluetooth
    - requires bluetoothctl
    - connect / disconnect / pair / unpair devices
    - toggle trusted flag per device
- Displays
    - requires hyprctl (Hyprland)
    - visual drag-to-arrange monitor layout
    - set position and mirror targets per display and remember them
    - set workspace rules for displays on the fly
    - apply changes live
- Sound
    - requires pipewire + wpctl
    - per-device output and input volume with mute
    - per-application stream volume with mute
- Apps
    - set default apps
    - configure autostart
- Themes
    - opens `gtk-theme-editor` (suite color profile)
- Configs (file editor — former gtk-configs)
    - edits `~/configs` (Hyprland, Waybar, Fuzzel, Mako, GTK/cursors, Terminal, MIME, Files, Raw)
    - no color pickers — those live in Themes
    - Save / Apply reloads Hyprland, Waybar, and Mako when needed
- Screensaver
    - configures `default/services/screensaver` idle daemon (`neuronix-screensaver-idle`)
    - idle timeout presets / custom seconds, style (clock / stars / aurora / matrix)
    - enable/disable + restart user service; preview screensaver now
    - writes `~/.config/neuronix-screensaver/config.ini`
- System Info
    - hostname, OS, kernel, uptime
    - CPU model, core count, memory usage
    - GPU (via lspci)

Run script
```bash
  ./run
```

Run script support installing/uninstalling on NixOS only
```bash
./run --install
./run --uninstall
```
