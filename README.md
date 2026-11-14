# MicroPython drivers — ESP32-S3

MicroPython drivers and teaching examples for displays, sensors and radio modules,
written for the ESP32-S3 and used in embedded-systems courses and labs at the
University of Buea (College of Technology) and the University of Douala (GIA laboratory).

*Pilotes MicroPython et exemples pédagogiques pour écrans, capteurs et modules radio,
écrits pour l'ESP32-S3 et utilisés en cours et en TP de systèmes embarqués.*

Most drivers come in two flavours:

- **`sync/`** — classic blocking API, simplest to start with;
- **`async/`** — non-blocking version built on `asyncio` (`uasyncio`), so the display,
  sensors and communication can run as concurrent tasks.

## Contents

| Folder | Hardware | Bus | What is inside |
|---|---|---|---|
| [`oled-ssd1351/`](oled-ssd1351/) | Waveshare 1.5" RGB OLED, SSD1351, 128 × 128, RGB565 | SPI | Driver (sync + async with double buffering) and 10 examples: colours, text UI, animation, sensor dashboard, sprites, a small game |
| [`oled-ssd1357/`](oled-ssd1357/) | Waveshare 0.96" RGB OLED, SSD1357, 64 × 128, RGB565 | SPI | Driver (sync + async) and 10 examples, including rotation and a menu |
| [`radar-ld2420/`](radar-ld2420/) | HiLink HLK-LD2420 24 GHz mmWave presence radar | UART | Driver that auto-detects the ASCII and binary output modes, command mode (read/write parameters), callbacks; examples incl. polling, callbacks and MQTT |
| [`lora-sx1262-t3s3/`](lora-sx1262-t3s3/) | LILYGO T3-S3 V1.2, Semtech SX1262 LoRa (915 MHz) | SPI | SX1262 driver and a point-to-point TX/RX lab with RSSI/SNR on the on-board OLED (sync + async) |
| [`pico-sensor-kit-b/`](pico-sensor-kit-b/) | Waveshare Pico-Sensor-Kit-B on an ESP32-S3 | I²C | SHTC3 (temp./humidity), SGP40 (VOC), QMI8658 (IMU), PCA9685 (PWM), TB6612FNG (motors), 24C01 (EEPROM), SSD1327 (grey OLED), plus the board pin map |

Each file starts with a header giving the default wiring, the target board and how to use it.

## Getting started

1. Flash MicroPython (v1.21 or later) on your ESP32-S3.
2. Copy the driver and one example to the board, for instance with `mpremote`:

   ```bash
   mpremote cp oled-ssd1351/sync/ssd1351.py :
   mpremote cp oled-ssd1351/sync/exemple_01_hello_world.py :
   mpremote run oled-ssd1351/sync/exemple_01_hello_world.py
   ```

3. Adjust the pin numbers in the constructor if your wiring differs from the defaults in the file header.

Two examples use standard MicroPython libraries that are not copied here; install them on the board with `mip`:

- the LoRa lab displays on the T3-S3's OLED with **`ssd1306`** — `mpremote mip install ssd1306`;
- the LD2420 MQTT example uses **`umqtt.simple`** — `mpremote mip install umqtt.simple`.

Replace the `YOUR_SSID` / `YOUR_PASSWORD` placeholders before running network examples.

## Credits

These drivers are original MicroPython code. Where a manufacturer's or another author's
work served as reference, it is acknowledged in the file header:

- SSD1351, SSD1357 and SSD1327 drivers: register sequences follow the **Waveshare** reference drivers
  ([1.5inch-RGB-OLED-Module](https://github.com/waveshare/1.5inch-RGB-OLED-Module) and the Waveshare OLED module code);
- SX1262 driver: inspired by Stuart Robinson's **SX12XX-LoRa** library
  ([StuartsProjects/SX12XX-LoRa](https://github.com/StuartsProjects/SX12XX-LoRa), MIT License);
- LD2420 driver: based on the HLK-LD2420 product manual and serial protocol document.

## Author

**Bertrand Moffo Lonla** — Associate Professor (Maître de conférences), Department of Computer
Engineering, College of Technology, University of Buea.
Website: <https://moffobertrand.github.io> · ORCID: [0000-0002-1060-9560](https://orcid.org/0000-0002-1060-9560)

## Licence

MIT — see [LICENSE](LICENSE).
