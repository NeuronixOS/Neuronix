# personalize/configs/apache/

Apache2 configs (personalize-only — not under `default/configs/`). Files live under
`~/configs/apache/`; the `links.json` `system` map makes `/etc/apache2/*` →
`~/configs/apache/*` via `neuronix-link-system-configs.sh`.
Presence of site trees triggers the chroot hook to apt-install **apache2**.

Also list `apache2` under `personalize/install-list` `# --- server ---` if you want
the package without relying on the hook.

## Example layout

```text
apache/
  apache2.conf
  envvars
  sites-available/
    000-default.conf
    my-site.conf
  sites-enabled/
    000-default.conf -> ../sites-available/000-default.conf
```

## Example `sites-available/my-site.conf` (snippet)

```apache
<VirtualHost *:80>
    ServerName my-site.local
    DocumentRoot /var/www/my-site
    <Directory /var/www/my-site>
        AllowOverride All
        Require all granted
    </Directory>
</VirtualHost>
```
