# Drop nginx.conf, sites-available/, sites-enabled/ here (personalize only —
# not shipped under default/configs; nginx is not in the stock install-list).
# Symlinked to /etc/nginx/* via links.json "system" map; staged at /etc/neuronix/configs/nginx/.
# Presence of site trees triggers chroot hook to apt-install nginx.
