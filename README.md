# home-assistant-config
My [Home Assistant](https://home-assistant.io/) config files

Home Assistant runs on my Raspberry Pi 3 with a UPS APC Back-UPS 650VA attached.

## Software on the Pi:
* [Nmap] (https://nmap.org/)
* [Apache2] (https://httpd.apache.org/)
* [Shell In a Box] (https://code.google.com/archive/p/shellinabox/)
* [NUT] (http://networkupstools.org/)
* [Mosquitto] (https://mosquitto.org/)
* [vsftpd FTP server] (https://security.appspot.com/vsftpd.html)
* [incron] (http://inotify.aiken.cz/)
* [Home Assistant](https://home-assistant.io/)

## Devices I have:
* WeMo Link (to control outside bulbs)
* WeMo Insight (to control swimming pool pump)
* WeMo Maker (to control outside fence)
* Foscam C1 camera
* Foscam Fi9853EP camera
* Linksys WVC54GCA camera
* Netatmo weather station with rainmeter
* Netatmo thermostat
* APC Back-UPS 650VA UPS
* Chromecast
* Logitech Squeezebox
* Efergy energy meter
* Fitbit Alta

## Automations (among others)
* Activate/deactivate motion detection and heating depending on the presence
* Turn on outside lights at sunset (+15 minutes)
* Turn off outside lights at night (at 00:15)
* When the outside lights have been turned on at late night (later than 00:15) and before 9AM, turn them off after 5 minutes
* Turn off outside lights after 10 seconds when the sun is not set (this is because when there is a power outage, WeMo Link turn on the light when the power is back).
* Turn on outside lights when fence is opened and the sun is set. This is useful when I arrive home after 00:15 that light have been turned off automatically.
* Notify when a power outage is detected by the UPS.
* Notify when the power is back to normal.
* Notify when the UPS battery has to be replaced.
* Notify if fence is open form more than 4 minutes.
* Turn on swimming pool pump at 7AM
* Turn on swimming pool pump at 8PM
* Stop the swimming pool pump depending on the season of the year (3 hours in summer, 2 hours in spring and autumn, 1 hour in winter).
I've created a sensor to determine roughly the season of the year:
```
- platform: template
  sensors:
    season:
      friendly_name: 'Estación'
      value_template:  >-
          {%- if now().month >= 3 and now().month <= 5 %}
              Spring
          {% elif now().month >= 6 and now().month <= 8 %}
              Summer
          {% elif now().month >= 9 and now().month <= 11 %}
              Autumn
          {% else %}
              Winter
          {%- endif %}
```

## Screenshot Home
![Home](https://raw.githubusercontent.com/hokus15/home-assistant-config/master/hass-config1.png)

## Screenshot Security
![Security](https://raw.githubusercontent.com/hokus15/home-assistant-config/master/hass-config2.png)

## Screenshot Misc
![Misc](https://raw.githubusercontent.com/hokus15/home-assistant-config/master/hass-config3.png)

## Home security description

I've configured the system to get instant notifications using telegram including snapshots when some of the cameras detect motion.

### Motion detection activation
Motion detection is activated automatically as soon as no one is at home.
I have an assistant that doesn't use the WiFi so (appart from legal implications) I cannot track her device.
My solution to this is to create a switch to enable a delay to activate motion detection and a slider to configure the delay in minutes.

![Security activation delay](https://raw.githubusercontent.com/hokus15/home-assistant-config/master/security_activation_delay.png)

### Cameras configuration
The configuration for my cameras has been set to upload a snapshot to an FTP every time a motion is detected.
You have to tweak the camera configuration (sensibility, motion detection zones, number of snapshots taken,...) to fit your needs (and not get too many notifications).
Each camera upload the snapshot into a different folder in the same FTP.

### FTP
The FTP is configured in the same Raspberry Pi Home-Assistant is installed.

To avoid draining the SD space I've set a daily crontab to delete snapshots older than 7 days.

This is how the crontab configuration looks like:
```
0 0 * * * sudo find /home/camera/* -mtime +7 -exec sudo rm {} \;
```

### incron

Now we need to connect the FTP with home-assistant.

For this I've used incron.

As described in their website (http://inotify.aiken.cz/?section=incron&page=about&lang=en): *This program is an "inotify cron" system. It consists of a daemon and a table manipulator. You can use it a similar way as the regular cron. The difference is that the inotify cron handles filesystem events rather than time periods.*

I've configured incron to execute a script called `motion_detected.sh` every time a new file is written and closed in the FTP folders.

This is how it looks like my incrontab configuration:
```
/home/camera/C1/snap IN_CLOSE_WRITE sudo bash /home/pi/motion_detected.sh $@/$# recibidor
/home/camera/FI9853EP/snap IN_CLOSE_WRITE sudo bash /home/pi/motion_detected.sh $@/$# piscina
/home/camera/WVC54CGA/snap IN_CLOSE_WRITE sudo bash /home/pi/motion_detected.sh $@/$# caseta
```

### Send pictures using telegram
The script `motion_detected.sh` calls home-assistant API to trigger a notification using Telegram including the snapshot.
It gets 2 parameters, first to get the name of the uploaded file (snapshot) and the other one the location of camera that uploaded the file (snapshot).

To run the script without providing a password to Home-Assistant, I've added `127.0.0.1` to `trusted_networks` list in `configuration.yaml` file.

This is how the script looks like:
```
#!/bin/sh
curl -s -X POST -H "Content-Type: application/json" -d '{"message": "text", "data": {"photo": {"file": "'$1'", "caption": "Movimiento detectado en '$2'"}}}' "http://localhost:8123/api/services/notify/telegram"
```