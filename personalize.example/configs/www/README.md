# configs/www/

Site files for the installed system. **Skipped** from `~/configs` and installed
as real files under `/var/www`. A home shortcut points back:

`~/www` → `/var/www`

(via merge staging + `links.json` `abs_symlink`)

## Layout

```text
www/
  html/          # → /var/www/html (typical DocumentRoot)
  my-site/       # → /var/www/my-site
```

Put real site trees here (not only this README). Apache/nginx vhosts should use
paths under `/var/www/...`.

