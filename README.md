# MyHOME
MyHOME integration for Home-Assistant

## Installation
The integration is able to install the gateway via the Home-Assistant graphical user interface, configuring the different devices needs to be done in YAML files however.

Some common gateways should be auto-discovered, but it is still possible to force the inclusion of a gateway not discovered. One limitation however is that the gateway needs to be in the same network as your Home-Assistant instance.

It is possible that upon first install (and updates), the OWNd listener process crashes and you do not get any status feedback on your devices. If such is the case, a restart of Home Assistant should solve the issue.

## BEWARE

If you've been using this integration in version 0.8 and prior, configuration structure has changed and you need to create and populate the appropriate config file. See below for instructions.


## Configuration and use

Please find the [configuration](https://github.com/anotherjulien/MyHOME/wiki/Configuration) on the project's wiki!  
[Advanced uses](https://github.com/anotherjulien/MyHOME/wiki/Advanced-uses) are also listed in the wiki.
