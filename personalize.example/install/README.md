# personalize/install/

Optional scripts run during **Calamares Desktop** install (target chroot), after
Chrome. Stock Neuronix does not ship these.

```text
personalize/install/
  cursor.sh     # example: wrap /usr/share/neuronix/install-cursor.sh
```

Each `*.sh` is copied to `/usr/share/neuronix/personalize-install/` and appended to
`contextualprocess_neuronix_desktop.conf` by `merge-personalize-dropins.sh`.

Cursor is **not** a stock Desktop package — add `cursor.sh` here only on
personal machines.
