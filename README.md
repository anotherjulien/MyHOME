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
`dimmable` is an optional boolean defaulting to `False` that you need to set to `True` if your device supports dimming. (Only "F418" and "F418U2" DIN modules seem to do to this day)  
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
The configuration is largely the same as lights, except here they cannot be dimmable, and you can specify the `class` if you wish to distinguish between `outlet` and `switch`.  
Here is an opportunity to touch on the `where`; which by OpenWebNet standard needs to be either 2 or 4 digits if you used virtual configuration and went beyond the "usual" numbering.  
It can never be 3 as the bus could not tell if `010` would be "A=01, PL=0" or "A=0, PL=10" for instance.

### Covers
Moving on to WHO 2, covers:

```yaml
cover:
  - platform: myhome
    devices:
      living_shutter:
        where: '11'
        name: Living room shutter
        advanced: True
        manufacturer: Legrand
        model: 67557
      kitchen_shutter:
        where: '12'
        name: Kitchen shutter
        advanced: True
        manufacturer: Legrand
        model: 67557
      dining_room_shutter:
        where: '13'
        name: Dining room shutter
        advanced: True
        manufacturer: Legrand
        model: 67557
```
The configuration remains similar to lights and switches.  
The specificity is the optional `advanced` boolean (defaulting to `False`), you need to set it to `True` if you have 'advanced' cover modules that keep track of and return position values. (Only "Céliane 67557", "Axolute H4661M2", "Livinglight LN4661M2" and the "F401" DIN module are capable of this)

### Binary sensors
Dry contacts and IR sensors are part of WHO 25

```yaml
binary_sensor:
  - platform: myhome
    devices:
      garage_door:
        where: '31'
        name: Garage door
        class: garage_door
        manufacturer: BTicino
        model: 3477
```
`where` for these is one of a few special cases, as per specification, they are always "3" followed by the sensor number assigned "[1-201]".  
`class` allows you to specify any supported Home-Assistant binary sensor `device_class`, this will affect the way the device is presented in the interface.

### Sensors
At this point, only energy sensors are supported as part of WHO 18:

```yaml
sensor:
  - platform: myhome
    devices:
      general_power:
        where: '51'
        name: Total power
        class: power
        manufacturer: BTicino
        model: F520
      water_heater_power:
        where: '52'
        name: Water heater
        class: power
        manufacturer: BTicino
        model: F520
```
`where` is also a special case for those as well since power meters are always "5" followed by the sensor number assigned "[1-255]".  
`class` is a required element as it will be used to tell apart other types of sensors once implemented, for now `power` is the only admissible value.

### CEN/CEN+ events
A powerful feature is to be able to assign CEN or CEN+ commands to your wall switches and use the events it generates in Home-Assistant to trigger automations.  
CEN/CEN+ devices do not need to be configured in Home-Assistant, as all CEN/CEN+ messages received will alway trigger an event.  
All you need is to create an automation with a trigger like follows:
```yaml
platform: event
event_type: myhome_cenplus_event
event_data:
  event: pushbutton_short_press
  object: 33
  pushbutton: 7
```
or
```yaml
platform: event
event_type: myhome_cen_event
event_data:
  event: pushbutton_long_release
  object: 10
  pushbutton: 1
```
`object` and `pushbutton` are the ones defined in the OpenWebNet CEN or CEN+ configuration.
Supported `events` varies between CEN and CEN+:  
* CEN events:
  * `pushbutton_short_press`
  * `pushbutton_short_release`
  * `pushbutton_long_press`
  * `pushbutton_long_release`  
* CEN+ events:
  * `pushbutton_short_press`
  * `pushbutton_long_press`
  * `pushbutton_long_release`

This is a really useful feature, it allows you to have wall switches turn WLED strips ON and OFF; Play/Pause Skip track on your SONOS... The only limit is your imagination!

### Services
#### Power sensor services
WHO 18 power meters are working in a way that is not always obvious. They will report the "instantaneous power consumption"; but only if requested and only for a given amount of time.  
This means you will periodically need to send a specific command to ask the sensor to start sending its power consumption in real time for a given duration not exceeding 255 minutes.  
This can be done with a service call on the appropriate device.

You can create an automation running on Home-Assistant's startup and every 2 hours to call this service:
```yaml
service: myhome.start_sending_instant_power
data:
  duration: 125
  entity_id: sensor.general_power
```

#### Gateway services
There are very few settings that can be written to the gateway through OpenWebNet, but one of them is the current time.  
You can ensure a for of time synchronization with your gateway by calling the following service on a regular basis:
```yaml
service: myhome.sync_time
data: {}
```
This will write the current system time of your Home-Assistant instance to your gateway.