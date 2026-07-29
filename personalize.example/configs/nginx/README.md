# personalize/configs/nginx/

Nginx configs (personalize-only). Symlinked to `/etc/nginx/*` via `links.json`
`system` map. Presence of site trees triggers apt-install of **nginx**.

## Example layout

```text
nginx/
  nginx.conf
  sites-available/
    default
    my-site
  sites-enabled/
    default -> ../sites-available/default
```

## Example `sites-available/my-site` (snippet)

```nginx
server {
    listen 80;
    server_name my-site.local;
    root /var/www/my-site;
    index index.html;
    location / {
        try_files $uri $uri/ =404;
    }
}
```
