# personalize/configs/crontab/

User crontab for the default (Calamares / autologin) user. Listed in `links.json`
`skip` so it is **not** copied into `~/configs`. Staged to
`/usr/share/neuronix/crontab.conf` and installed by `neuronix-install-crontab.sh`.

`personalize/configs/crontab/crontab.conf` wins over `default/configs/crontab/`.

## Example `crontab.conf`

```cron
# m h  dom mon dow   command
0 5 * * 1 tar -zcf /var/backups/home.tgz "$HOME"
*/15 * * * * "$HOME/bin/sync-notes.sh"
```
