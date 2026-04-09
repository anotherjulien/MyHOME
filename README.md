# What's up?

I'm afraid it's time to be blunt, I cannot maintain this integration any longer, not in any meaningful way at least.

I'm open for someone to take over this and OWNd's repositories.  
I'd strongly prefer someone who has extensive experience with a proper development workflow, since I feel that's something that has been missing from this project.  
I'd love for this to become a core integration one day but I have no idea how much work would be needed to achieve that.

Anyway, If you think you can take over code ownership for this, let me know.

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

## Extended OpenWebNet coverage

This branch also expands the integration around reusable OpenWebNet service families that were previously missing or only reachable through raw frames:

- gateway helpers and structured WHO=13 readbacks
- advanced thermoregulation WHO=4 and WHO=1004 helpers
- burglar alarm WHO=5 readbacks and AUX WHO=9 controls
- audio, radio and video helpers for WHO=22 and WHO=7
- scenario, scene programmer and virtual command helpers for WHO=0, WHO=15, WHO=17 and WHO=25
- lighting management and energy helpers for WHO=24 and WHO=18

The canonical service definitions remain in [custom_components/myhome/services.yaml](custom_components/myhome/services.yaml).

## Sanitized examples

Reusable Home Assistant examples are included under [examples](examples):

- `myhome.example.yaml` for gateway and entity configuration
- `configuration.example.yaml` for package and dashboard includes
- `packages/` for Google Home bridges, service wrappers and scenario status helpers
- `lovelace/` for audio and climate dashboard examples
- `google_assistant/` for entity exposure examples

All example files use placeholders and generic entity names. They are intentionally sanitized and should be copied and adapted instead of used as-is.

## Tests

Pure parser and builder tests that do not require a running Home Assistant instance are included under [tests](tests). They cover the reusable OpenWebNet helper modules added in this branch and can run in GitHub Actions with a lightweight Python environment.
