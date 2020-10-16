# MyHOME
MyHOME integration for Home-Assistant

## Installation
The integration is able to install the gateway via the Home-Assistant graphical user interface, configuring the different devices needs to be done in YAML files however.

Some common gateways should be auto-discovered, but it is still possible to force the inclusion of a gateway not discovered. One limitation however is that the gateway needs to be in the same network as your Home-Assistant instance.

At the moment, the underlying library does not support the 'HMAC' password scheme; a workaround is to put the IP of your Home-Assistant instance in the authorized IPs in your gateway configuration.

## Configuration

Once your gateway is integrated in Home-Assistant, you can start adding your different devices.  
This configuration needs to take place in your `configuration.yaml` file; split by domains.

### Lights
For clarity, the OpenWebNet elements of WHO 1 have been split in two domains, first and obvious one is lights:

```yaml
light:
  - platform: myhome
    devices:
      garage:
        where: '01'
        name: Garage
        dimmable: False
        manufacturer: Arnould
        model: 64391
      dining_room:
        where: '17'
        name: Dining room
        dimmable: False
        manufacturer: BTicino
        model: F411U2
        model: 64391
      main_bedroom_1:
        where: '23'
        name: Main bedroom
        dimmable: True
        manufacturer: BTicino
        model: F418
```
Here, as almost everywhere throughout this configuration, `where` is the OpenWebNet address of your device (the 'APL').  
`name` is an optional "friendly name".  
`dimmable` is an optional boolean defaulting to `False` that you need to set to `True` if your device supports dimming. (To my knowledge, only F418 and F418U2 do to this day)  
`manufacturer` and `model` are optional and purely cosmetic (as they are reported in the device detail in Home-Assistant's interface).

### Switches
The second part of WHO 1 is switches, it is a domain that you will use if you have controller not attached to lights, but rather to power outlets for instance.

```yaml
switch:
  - platform: myhome
    devices:
      bed_heater:
        where: '0211'
        name: Mattress heating pad
        class: outlet
        manufacturer: BTicino
        model: F411U2
      door_bell:
        where: '0515'
        name: Doorbell
        class: switch
        manufacturer: BTicino
        model: 3476
      hvac_relay_1:
        where: '08'
        name: HVAC relay 1
        class: switch
        manufacturer: Arnould
        model: 64391
```
The configuration is largely the same as lights, except here they cannot be dimmable, and you can specify the `device_class` if you wish to distinguish between `outlet` and `switch`.  
Here is an opportunity to touch on the `where`; wich by OpenWebNet standard needs to be either 2 or 4 digits if you used virtual configuration and went beyond the "usual" numbering.  
It can never be 3 as the bus could not tell if `010` would be "A=01, PL=0" or "A=0, PL=10" for instance.
