# personalize/browser-extensions/

Unpacked Chrome/Chromium extensions. Each folder with a `manifest.json` is staged to
`/usr/share/neuronix/browser-extensions/<Name>/` and registered via
`neuronix-chrome` / `neuronix-chromium` (also External Extensions JSON when those
browsers are installed).

## Example layout

```text
browser-extensions/
  MyExtension/
    manifest.json
    background.js
    icons/icon128.png
```

## Example `manifest.json` (MV3)

```json
{
  "manifest_version": 3,
  "name": "My Extension",
  "version": "1.0.0",
  "description": "Example Neuronix browser extension",
  "action": {
    "default_title": "My Extension"
  },
  "background": {
    "service_worker": "background.js"
  },
  "permissions": []
}
```

No per-extension install script — drop the folder and rebuild.
