# home-assistant-config
My [Home Assistant](https://home-assistant.io/) config files

Home Assistant runs on my Raspberry Pi 3 with a UPS APC Back-UPS 650VA and a AEOTEC Z-Stick Gen5 attached.

## Software on the Pi:
* [Nmap](https://nmap.org/)
* [Apache2](https://httpd.apache.org/)
* [Shell In a Box](https://code.google.com/archive/p/shellinabox/)
* [NUT](http://networkupstools.org/)
* [Mosquitto](https://mosquitto.org/)
* [vsftpd FTP server](https://security.appspot.com/vsftpd.html)
* [incron](http://inotify.aiken.cz/)
* [CUPS](https://wiki.archlinux.org/index.php/CUPS)
* [HPLIP](http://hplipopensource.com/hplip-web/index.html)
* [Home Assistant](https://home-assistant.io/)
* [Dasher](https://github.com/maddox/dasher)
* [Let's Encrypt](https://letsencrypt.org/)

## Devices I have:
* WeMo Link (to control outside bulbs)
* WeMo Insight (to control swimming pool pump)
* WeMo Switch (to control night light)
* WeMo Maker (to control outside fence)
* Foscam C1 camera
* Foscam Fi9853EP camera
* Foscam Fi9900P camera
* Linksys WVC54GCA camera
* Netatmo Presence Security camera
* Netatmo weather station with rainmeter and windmeter
* Netatmo thermostat
* APC Back-UPS 650VA UPS
* Chromecast2
* Chromecast audio
* Logitech Squeezebox
* Efergy energy meter
* HP Photosmart 5520 printer
* QNAP TS-110 NAS
* Amazon Dash button

### Z-Wave devices:
* AEOTEC Z-Stick Gen5
* 2 x Fibaro Door / Window Sensor FGK-10x (one of them with a DS18B20 temperature sensor)
* 1 x Fibaro Door / Window Sensor FGK-10x with a waterproof DS18B20 temperature sensor to measure swimming pool water temperature
* Fibaro FGMS-001 Motion Sensor
* Fibaro FGS-223 Double switch 2
* Swiid Swiidinter switch
* Nodon Octan remote

## Automations (among others)
* Activate/deactivate motion detection, heating and Chrismas tree lights based on presence
* Turn on outside lights at sunset (+15 minutes)
* Turn off outside lights at night (at 00:15)
* When the outside lights have been turned on at late night (later than 00:15) and before 9AM, turn them off after 5 minutes
* Turn off outside lights after 10 seconds when the sun is not set (this is because when there is a power outage, WeMo Link turn on the light when the power is back).
* Turn on outside lights when fence is opened and the sun is set. This is useful when I arrive home after 00:15 that light have been turned off automatically.
* Notify when a power outage is detected by the UPS.
* Notify when the power is back to normal.
* Notify when the UPS battery has to be replaced.
* Notify if fence is open for more than 10 minutes.
* Turn on swimming pool pump based on water temperature (colder water less time on based ion a formula) and turn it off just before the peak electricity price.

**Note that the following configuration is not used any more. Since version 0.53 a season sensor was released. I leave it here only for information purpose.**

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

## Screenshot Inside
![Inside](https://raw.githubusercontent.com/hokus15/home-assistant-config/master/hass-config3.png)

## Screenshot Outside
![Outside](https://raw.githubusercontent.com/hokus15/home-assistant-config/master/hass-config4.png)

## Screenshot Misc
![Misc](https://raw.githubusercontent.com/hokus15/home-assistant-config/master/hass-config5.png)

## Presence detection
Since I found owntracks was draining my phone battery I decided to use another approach for presence detection. In my case it's pretty accurate.
I use three different sensors, if one of them is set as 'home' it means that I'm at home. If all of them are 'not_home' it means that I'm not at home.

### Nmap
This is the Nmap component.

### Wifi connection
When I connect to my home WiFi I use a [Tasker](http://tasker.dinglisch.net/) profile to send a MQTT message to tell home-assistant that I'm at home and another MQTT message when I disconnect from my home WiFi.

### iBeacon:
I've configured my RaspberryPi to transmit as an iBeacon. When my phone detects the RaspberryPi iBeacon I use a [Tasker](http://tasker.dinglisch.net/) profile to send a MQTT message to tell home-assistant that I'm at home and another MQTT message when iBeacon is not detected anyomore.

## Home security description
I've configured the system to get instant notifications using telegram including snapshots when one of the cameras triggers a motion detection.

### Motion detection activation
Motion detection is activated automatically as soon as no one is at home.

I have an assistant that doesn't use the WiFi so (appart from legal implications) I cannot track her device with nmap.

My wife and I share a Google Calendar where she introduces her working shifts. As the assistant working hours varies depending on my wife's working shift I use the Google Calendar component to automatically set her presence.

I also have a virtual device to temporarily set as 'home' when actually no one of the family is at home. To do so, I've created a switch to enable a delay to activate motion detection and a slider to configure the delay in minutes.

![Security activation delay](https://raw.githubusercontent.com/hokus15/home-assistant-config/master/security_activation_delay.png)

### Cameras configuration
The configuration for my cameras has been set to upload a snapshot to an FTP every time a motion is detected.

You have to tweak the camera configuration (sensibility, motion detection zones, number of snapshots taken,...) to fit your needs (and not get too many notifications).

Each camera uploads the snapshots into a different folder in the same FTP.

### FTP
The FTP is configured in the same Raspberry Pi Home-Assistant is installed.

To avoid draining the SD space I've set a daily crontab to delete snapshots older than 7 days.

This is how the crontab configuration looks like:
```
0 0 * * * sudo find /home/camera/* -mtime +7 -exec sudo rm {} \;
```

### incron

We need to connect the FTP with home-assistant. To achieve this I've used incron.

As described in [iNotify website] (http://inotify.aiken.cz/?section=incron&page=about&lang=en): *This program is an "inotify cron" system. It consists of a daemon and a table manipulator. You can use it a similar way as the regular cron. The difference is that the inotify cron handles filesystem events rather than time periods.*

I've configured incron to execute a script called `motion_detected.sh` every time a new file is written and closed in the FTP folders.

This is how it looks like my incrontab configuration:
```
/home/camera/C1/snap IN_CLOSE_WRITE sudo bash /home/pi/motion_detected.sh $@/$# recibidor
/home/camera/FI9853EP/snap IN_CLOSE_WRITE sudo bash /home/pi/motion_detected.sh $@/$# piscina
/home/camera/WVC54CGA/snap IN_CLOSE_WRITE sudo bash /home/pi/motion_detected.sh $@/$# caseta
```

### Send pictures using telegram
The script `motion-detected.sh` check the current status of the alarm, if it's already triggered, it exits, otherwise calls home-assistant API to turn on the `notify_motion_detection_script`.
It waits for 10 seconds and publishes alarm status 1 to MQTT topic `home/camera/<camera name>/alarm` (that means, alarm triggered). After that, a notification is sent using Telegram including the snapshot.

It gets 2 parameters:
  1. Name of the snapshot file name
  2. Name of the camera that triggered the alarm

To run the script without providing a password to Home-Assistant, I've added `127.0.0.1` to `trusted_networks` list in `configuration.yaml` file.

This is how the script looks like:
```
#!/bin/sh
alarm_status=`mosquitto_sub --cafile /etc/ssl/certs/ca-certificates.crt -h <mqtt_host> -p <mqtt_port> -u <mqtt_user> -P <mqtt_password> -t "home/camera/$2/alarm" -C 1`
if [ $alarm_status -eq 0 ]; then
    curl -s -X POST -H "Content-Type: application/json" -d '{"data": {"file": "'$1'", "camera": "'$2'"}}' "http://localhost:8123/api/services/script/notify_motion_detection"
fi
```

The `home/camera/<camera name>/alarm` topic is back to 0 after 30 seconds using an automation.

## Monitor UPS status

I have a APC Back-UPS 650VA UPS attached to my raspberry pi.

This UPS gives power to my main internet router, my raspberry pi and my QNAP NAS.

Monitor the UPS status is very useful to know when a power outage has occured (and receive a telegram notification) and also know when the power is back to normal.

**Note that the following configuration is not used any more. Since version 0.34 a nut sensor was released. I leave it here only for information purpose.**

To monitor the UPS status in Home Assistant I use a MQTT sensor.

### Publish the UPS status to MQTT

To publish the UPS status to MQTT I use [NUT] (http://networkupstools.org/).

Once you have NUT installed an running you can configure it to publish UPS status to MQTT topic.

To do this, just edit `/etc/nut/upsmon.conf` file and set the `NOTIFYCMD` command top publish the status to MQTT:

```
NOTIFYCMD "mosquitto_pub --cafile /etc/ssl/certs/ca-certificates.crt -h <mqtt_host> -p <mqtt_port> -u <mqtt_user> -P <mqtt_password> -t \"home/ups/status\" -r -m $NOTIFYFLAG"
```

I've also adapted the `NOTIFYMSG` values:

```
NOTIFYMSG ONLINE        "ONLINE"
NOTIFYMSG ONBATT        "ONBATT"
NOTIFYMSG LOWBATT       "LOWBATT"
NOTIFYMSG FSD           "FSD"
NOTIFYMSG COMMOK        "COMMOK"
NOTIFYMSG COMMBAD       "COMMBAD"
NOTIFYMSG SHUTDOWN      "SHUTDOWN"
NOTIFYMSG REPLBATT      "RPLBATT"
NOTIFYMSG NOCOMM        "NOCOMM"
NOTIFYMSG NOPARENT      "NOPARENT"
```

and `NOTIFYFLAG` values:

```
NOTIFYFLAG ONLINE       EXEC+SYSLOG
NOTIFYFLAG ONBATT       EXEC+SYSLOG
NOTIFYFLAG LOWBATT      EXEC+SYSLOG
NOTIFYFLAG FSD  EXEC+SYSLOG
NOTIFYFLAG COMMOK       EXEC+SYSLOG
NOTIFYFLAG COMMBAD      SYSLOG
NOTIFYFLAG SHUTDOWN     EXEC+SYSLOG
NOTIFYFLAG REPLBATT     EXEC+SYSLOG
NOTIFYFLAG NOCOMM       EXEC+SYSLOG
NOTIFYFLAG NOPARENT     EXEC+SYSLOG
```

![UPS Monitor](https://raw.githubusercontent.com/hokus15/home-assistant-config/master/UPS_monitor.png)

## Monitor printer ink levels

You need to install [CUPS](https://wiki.archlinux.org/index.php/CUPS) and [HPLIP](http://hplipopensource.com/hplip-web/index.html).

Once the printer is configured you can read the ink levels using the `hp-info` utility.

To monitor the ink levels in Home Assistant I use one MQTT sensor per each color.

### Publish the ink levels to MQTT

I've created a script to publish each color ink level to a different MQTT topic (`home/printer/<color>`). This script only publishes to MQTT if something is returned from `hp-info` utility.

The script looks like:
```
#!/bin/sh
ink_levels=$(hp-info 2>&1 | grep -oP "(?<=agent[1-4]-level\s{18})(.*\S)" | tr "\n" ",")
colors=(
     'magenta'
     'cyan'
     'yellow'
     'black'
   )
if [ -n "${ink_levels}" ]; then
    IFS=',' read -r -a ink_levels_array <<< "$ink_levels"
    for index in "${!ink_levels_array[@]}"
    do
        if [ -n "${ink_levels_array[index]}" ]; then
           mosquitto_pub --cafile /etc/ssl/certs/ca-certificates.crt -h <mqtt_host> -p <mqtt_port> -u <mqtt_user> -P <mqtt_password> -t "home/printer/${colors[index]}" -r -m "${ink_levels_array[index]}"
        fi
    done
fi
```

Note `hp-info` takes more than 20 seconds to execute. If you try to execute direcly from Home Assistant you will get a timeout error.

I've added the script to crontab to check every 5 minutes the ink levels (keep in mind that it only publishes when the `hp-info` utility returns data and this only occurs when the printer is on):

```
*/5 * * * * bash /home/pi/ink_levels.sh
```

![Ink level monitor](https://raw.githubusercontent.com/hokus15/home-assistant-config/master/ink_level_monitor.png)

## Amazon Dash button
To use the Amazon dash button with your Home-Assistant you can follow the video tutorial from BRUH Automation:

<a href="http://www.youtube.com/watch?feature=player_embedded&v=qZpJ9W0wCks
" target="_blank"><img src="http://img.youtube.com/vi/qZpJ9W0wCks/0.jpg" 
alt="Dash button config" width="240" height="180" border="10" /></a>

**Be sure you have the latest version of node.js installed.**

I push the dash button every day just before go to sleep, it triggers a security check that includes:
* Close outside fence if open
* Check for opened windows / doors (if any door or window is open it tells me using text-to-speech service)
* Turn off outside lights
* Turn on stairs lamp for two minutes
* Turn off hall lamp
* Turn off Chrismas tree lights (during Chrismas)

