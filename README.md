# home-assistant-config
My Home-Assistant config (https://home-assistant.io)

## Screenshot Home
![Home](https://raw.githubusercontent.com/hokus15/home-assistant-config/master/hass-config1.jpg)

## Screenshot Security
![Security](https://raw.githubusercontent.com/hokus15/home-assistant-config/master/hass-config2.jpg)

## Screenshot Misc
![Misc](https://raw.githubusercontent.com/hokus15/home-assistant-config/master/hass-config3.jpg)

## Home security description

I've configured the system to get instant notifications using telegram including snapshots when some of the cameras detect motion.

### Motion detection activation
Motion detection is activated automatically as soon as no one is at home.
I have an assistant that doesn't use the WiFi so I cannot track her device (appart from legal implications).
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

To run the script without providing a password to Home-Assistant, I've added `127.0.0.1` to `approved_ips` list in `configuration.yaml` file.

This is how the script looks like:
```
#!/bin/sh
curl -s -X POST -H "Content-Type: application/json" -d '{"message": "text", "data": {"photo": {"file": "'$1'", "caption": "Movimiento detectado en '$2'"}}}' "http://localhost:8123/api/services/notify/telegram"
```

### Other ideas
* Have the incron as a sensor in home-assistant would avoid the need to do some of the configurations.
* iCal integration in Home-Assistant could be used enable or disable motion sensor based on a schedule. This can be also achieved using other additional tools like tasker in your mobile phone.