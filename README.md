# LocalTuyaIR Remote Control integration for Home Assistant

Many users rely on the [LocalTuya](https://github.com/rospogrigio/localtuya) integration for Home Assistant to control Tuya-based devices locally, without relying on cloud services. However, this popular integration currently does not support IR remote controller emulators. As a result, those wishing to integrate Tuya’s Wi-Fi-based IR remote emulators into their smart home environment are left without a straightforward solution.

![image](https://github.com/user-attachments/assets/a7f441d4-75b2-4a68-aadd-288f4f013149)

This integration addresses that gap. It provides full local control of Tuya Wi-Fi IR remote controllers within Home Assistant, entirely bypassing the Tuya cloud. By doing so, you gain:
* Local Control: No external cloud services required. All communication remains within your local network, improving reliability and responsiveness.
* Flexible IR Control: Seamlessly integrate Wi-Fi-based IR remote emulators from Tuya, enabling you to manage a wide range of IR-controlled devices—such as TVs, air conditioners, and audio systems—directly from Home Assistant.

## Integration setup

Just like other Tuya devices controlled locally, you’ll need to obtain the device’s “local key” (the encryption key) to manage the IR remote emulator without relying on the cloud. If you already know the local key, you can provide it manually. Otherwise, let the setup wizard guide you through retrieving it via the Tuya API. Unfortunately, this still requires creating a developer account at iot.tuya.com and linking it to your existing Tuya account. After linking, the integration uses your API credentials (Access ID and Access Secret) to automatically fetch the local key.

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
You can make integration to remember the button code by passing a `device` parameter. If you don't pass it, the button code will be shown in the notification only.

![image](https://github.com/user-attachments/assets/055d5bdd-7f35-4df0-9554-f00791a11b81)

After calling the service, you will receive a notification which asks you to press the button on your real remote controller. Point your remote controller at the IR receiver of your Wi-Fi IR remote emulator and press the button you want to learn. If the learning process is successful, you will receive a notification with the button code with some additional instructions.

![image](https://github.com/user-attachments/assets/6fdd7928-86cb-4f3c-9c95-8bab40e708d9)

This integration tries to decode the button code using different IR protocols. If it fails, you will receive a notification with the raw button code. See below for more information on how to format IR codes.

Please note that this Tuya device is a crappy one (at least my one) and it may require multiple attempts to learn a command. Sometimes it may not work at all until you restart the device. If you have any issues with learning commands, please try to restart the device and try again.

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


## IR Code Formatting

When defining IR commands for the Tuya IR remote emulator in Home Assistant, each code is represented as a single string. This string encodes the precise details of the IR command you want to send—either as a sequence of low-level raw timing values or by referencing a known IR protocol with corresponding parameters.

Because different devices and remotes may use various encoding schemes and timing, this flexible format ensures you can accurately represent a broad range of commands. Whether you’re dealing with a fully supported protocol like NEC or need to reproduce a custom signal captured from an unusual remote, these strings give you the necessary control and versatility.

Below are the two main formats you can use, along with details on how to specify parameters and numerical values.

### Raw Timing Format

The raw format allows you to directly specify the sequence of pulses and gaps as a list of timing values, measured in microseconds (or another timing unit depending on your configuration). This is useful when no known protocol fits your device, or if you have already captured the IR pattern and simply need to replay it.

```
raw:9000,4500,560,560,560,1690,560,1690,560
```

In this example, the comma-separated list of numbers represents the duration of each pulse or gap in the IR signal. The first number is the duration of the first pulse, the second number is the duration of the first gap, and so on. The values are in pairs, with the first number representing the pulse duration and the second number representing the gap duration.

### Protocol-Based Format

If your device uses a known IR protocol (like NEC, RC5, RC6, etc.), you can define the code using the protocol’s name followed by a series of key-value parameters. This approach is cleaner and more readable, and it leverages standard IR timing and data structures.

Example (NEC Protocol):
```
nec:addr=0x25,cmd=0x1E
```
Here, `addr` and `cmd` represent the address and command bytes defined by the NEC protocol. By using a recognized protocol, the integration takes care of the underlying timing details, making it easier to specify and understand the command.

For both raw and protocol-based formats, you can specify numeric values in either decimal or hexadecimal form. Hexadecimal values are prefixed with `0x`.

### Supported IR Protocols and Parameters

Below is a list of supported IR protocols with brief descriptions to help you choose the one suitable for your device.

#### NEC Protocols

- **nec**: The standard NEC protocol using a 32-bit code, widely used in consumer electronics. Requires parameters `addr` (address) and `cmd` (command).

- **nec-ext**: An extended version of the NEC protocol with a 32-bit code and a different structure for address and command. Also requires parameters `addr` and `cmd`.

- **nec42**: A 42-bit variant of the NEC protocol, providing a larger address range. Parameters: `addr` and `cmd`.

- **nec42-ext**: An extended version of the 42-bit NEC protocol for devices requiring additional address space. Requires `addr` and `cmd`.

#### RC Protocols

- **rc5**: The RC5 protocol is used in Philips devices and some other brands. Requires parameters `addr` and `cmd`, as well as an optional `toggle` parameter. RC5X is a variant of RC5 with a different toggle bit, it's supported and used for `cmd >= 64` (toggle bit is used as the 7th bit).

- **rc6**: An improved version of RC5, the RC6 protocol supports higher data transmission rates and more commands. Necessary parameters: `addr` and `cmd`. The `toggle` parameter is optional.

The `toggle` parameter can be 0 or 1 and is optional. It helps to distinguish between repeated commands. By default, the integration toggles the `toggle` parameter automatically.

#### Sony SIRC Protocols

- **sirc**: The standard Sony Infrared Remote Control (SIRC) protocol, usually using 12 bits. Requires `addr` and `cmd`.

- **sirc15**: The 15-bit variant of the SIRC protocol, providing more commands. Parameters: `addr` and `cmd`.

- **sirc20**: The 20-bit version of the SIRC protocol for devices with extended address and command space. Requires `addr` and `cmd`.

#### Other Protocols

- **samsung32**: Used in Samsung devices, this 32-bit protocol requires `addr` and `cmd`.

- **kaseikyo**: A complex protocol used by Panasonic and other companies, requires parameters `vendor_id`, `genre1`, `genre2`, `data`, and `id`.

- **rca**: The RCA protocol used in RCA brand devices. Requires `addr` and `cmd`.

- **pioneer**: Used in Pioneer devices, this protocol requires `addr` and `cmd`.

- **ac**: Some air conditioners use this protocol (at least Gorenie and MDV). Usually 16-bit command contains 4-bit mode, 4-bit fan speed, 4-bit temperature and some other bits. Requires `addr` and `cmd`.


## Credits

* This integration is based on the TinyTuya https://github.com/jasonacox/tinytuya by Jason Cox


## Donate

* [Become a sponsor on GitHub](https://github.com/sponsors/ClusterM)
* [Buy Me A Coffee](https://www.buymeacoffee.com/cluster)
* [Donation Alerts](https://www.donationalerts.com/r/clustermeerkat)
* [Boosty](https://boosty.to/cluster)
