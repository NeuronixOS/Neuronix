# Drop apache2.conf, envvars, sites-available/, sites-enabled/ here (personalize only —
# not shipped under default/configs; apache2 is not in the stock install-list).
# Symlinked to /etc/apache2/* via links.json "system" map; staged at /etc/neuronix/configs/apache/.
# Presence of site trees triggers chroot hook to apt-install apache2.
