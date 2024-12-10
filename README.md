# LocalTuyaIR Remote Control integration for Home Assistant

Many users rely on the "LocalTuya" integration for Home Assistant to control Tuya-based devices locally, without the need for a cloud connection.
However, this popular integration does not offer support for IR remote controller emulators, leaving a significant gap for those who wish to seamlessly integrate Wi-Fi-based IR remote emulators into their smart home setup.

This integration is designed specifically to address that limitation. It provides full local control of Tuya Wi-Fi IR remote controller emulators within Home Assistant, entirely bypassing the Tuya cloud. By doing so, it ensures:
* Local Control: No external cloud services required. All communication stays within your local network, improving reliability and responsiveness.
* Flexible IR Control: Seamlessly integrate Wi-Fi-based IR remote emulators from Tuya, enabling you to automate and manage various IR-controlled devices — such as TVs, air conditioners, and audio systems — directly through Home Assistant.

## Integration setup

Just like other Tuya devices controlled locally, you’ll need to obtain the device’s “local key” (the encryption key) to manage the IR remote emulator without relying on the cloud. You can provide this key manually if you already know it, or let the setup wizard guide you through the process of retrieving it via the Tuya API. Unfortunately, this still requires you to create a developer account at iot.tuya.com and link it to your existing Tuya account. Once linked, the integration can use your API credentials (Access ID and Access Secret) to automatically fetch the local key.

### Providing the Local Key Manually

If you have already obtained the local key for your IR remote device through other means, simply select "Enter the local key manually" and follow the prompts to input the key during the integration setup.

### Automated Retrieval via Tuya API

If you don’t have the local key at hand, the setup wizard can retrieve it for you — but you must supply the necessary Tuya API credentials. Here’s what you need to do:
* Add your Tuya IR remote emulator device to the Tuya Smart or Smart Life app ([for Android](https://play.google.com/store/apps/details?id=com.tuya.smartlife) or [for iOS](https://apps.apple.com/us/app/smart-life-smart-living/id1115101477)). Yes, you need to do it even if you want to control it locally.
* Create a Tuya IoT Developer Account at [iot.tuya.com](https://iot.tuya.com) and log in to access the Tuya IoT Platform dashboard.
* Click on `Cloud`

  ![image](https://user-images.githubusercontent.com/4236181/139099858-ad859219-ae39-411d-8b6f-7edd39684c90.png)

* Click on the `Create Cloud Project` button

  ![image](https://user-images.githubusercontent.com/4236181/139100737-7d8f5784-9e2f-492e-a867-b8f6765b3397.png)

* Enter any name for your project, select "Smart Home" for industry and development method. You can select any data center but you **must** remember which one you chose.

  ![image](https://user-images.githubusercontent.com/4236181/139101390-2fb4e88f-235c-4872-91a1-3e78ee6217f8.png)

* Skip Configuration Wizard.

  ![image](https://user-images.githubusercontent.com/4236181/139154750-690cf86a-98ac-4428-8aa8-467ef8b96d32.png)

* Copy and save your **Client ID** and **Client Secret**.

  ![image](https://user-images.githubusercontent.com/4236181/139103527-0a048527-ddc2-40c3-aa99-29db0d3cb94c.png)

* Select `Devices`.

  ![image](https://user-images.githubusercontent.com/4236181/139103834-927c6c02-5860-40d6-829d-5a5dfc9091b6.png)

* Select `Link Tuya App Account`.

  ![image](https://user-images.githubusercontent.com/4236181/139103967-45cf78f0-375b-49db-a111-7c8509abc5c0.png)

* Click on `Add App Account` and it will display a QR code.

  ![image](https://user-images.githubusercontent.com/4236181/139104100-e9b25366-2feb-489b-9044-322ca1dad9c6.png)

* Scan the QR code using your mobile phone and Smart Life app by going to the "Me" tab and clicking on the QR code button [..] in the upper right hand corner of the app. Your account should appear on the list.

  ![image](https://user-images.githubusercontent.com/4236181/139104842-b93b5285-bf76-4eb2-b01b-8f6aa54fdcd9.png)

  You can check the 'Devices' tab to see if your device is listed.

* Now, you have your Tuya API credentials. Go to the Home Assistant integration setup and select "Obtain the local key using the Tuya Cloud API". Enter your **Client ID** and **Client Secret** and select the data center you chose earlier.

  ![image](https://github.com/user-attachments/assets/c28ac38f-2154-496c-8fd9-2c0b8f3b4ab1)

* If everything is correct, the integration will find your device on the local network and fill all the necessary information for you. Just click "Submit" and you're done!

## How to use

This integration creates a new "remote.*" entity for your IR remote controller. But "Remote" entities are not directly controllable. You must use the `remote.send_command` service to send IR commands to your device and `remote.learn_command` service to learn new commands (read button codes from your remote). So, you can create scripts, automations, or even use the `remote.send_command` service directly from the Developer Tools to control your IR devices.

### Learn new commands (how to get button codes)

To learn new commands, call the `remote.learn_command` service and pass the entity_id of your remote controller. You can do it from the Developer Tools. You must specify a `command` parameter with the name of the command you want to learn. 
You can make integration to remember the button code by passing a `device` parameter. If you don't pass it, the button code will be shown in the notification only. After calling the service, you will receive a notification which asks you to press the button on your real remote controller. When you press the button, the button code will be shown in the notification with some additional instructions.

### Send commands

To send commands, call the `remote.send_command` service and pass the entity_id of your remote controller. You can use it in scripts and automations. Of course, you can try it from the Developer Tools as well. There are two methods to send commands: specifying a name of the previously learned command or passing a button code. To send a command by name, you must specify a `device` parameter with the name of the device you specified during learning:

```yaml
service: remote.send_command
data:
  entity_id: remote.my_remote
  command: Power
  device: TV
```

To send a command by button code, just pass the `command` parameter with the button code:

```yaml
service: remote.send_command
data:
  entity_id: remote.my_remote
  command: nec:addr=0xde,cmd=0xed
```
