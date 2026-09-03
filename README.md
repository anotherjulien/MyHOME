# MyHOME

MyHOME integration for Home Assistant, adding support for BTicino/Legrand MyHOME (OpenWebNet) systems.

This is a maintained fork of [anotherjulien/MyHOME](https://github.com/anotherjulien/MyHOME), which the original author is no longer able to actively maintain. All credit for the original design and implementation goes to anotherjulien — see the [fork changelog](https://github.com/davmapo/MyHOME/wiki/Fork-changelog) on the wiki for what has changed here.

Licensed under [AGPLv3](LICENSE), same as upstream.

## Installation

The integration can install the gateway via the Home Assistant graphical user interface; configuring the individual devices needs to be done in a YAML file, see [Configuration](https://github.com/davmapo/MyHOME/wiki/Configuration) on the wiki.

Some common gateways should be auto-discovered, but it is still possible to force the inclusion of a gateway not discovered. One limitation is that the gateway needs to be on the same network as your Home Assistant instance.

It is possible that on first install (and after updates), the OWNd listener process crashes and you do not get any status feedback on your devices. If that happens, restarting Home Assistant should solve the issue.

## BEWARE

If you've been using this integration in version 0.8 or prior, the configuration structure has changed and you need to create and populate the appropriate config file — see [Legacy configuration](https://github.com/davmapo/MyHOME/wiki/Legacy-configuration-(before-v0.9)) on the wiki.

## Configuration and use

Please find the [configuration](https://github.com/davmapo/MyHOME/wiki/Configuration) on this repository's wiki!
[Advanced uses](https://github.com/davmapo/MyHOME/wiki/Advanced-uses) are also listed there.
