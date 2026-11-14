# ===================================================================
# HLK-LD2420 MicroPython Examples for Waveshare ESP32-S3-Pico
# University of Buea - College of Technology
# Prof. MOFFO LONLA Bertrand - May 2026
#
# Sensor fw v1.6.1 outputs ASCII: "ON\r\n" / "OFF\r\n" / "Range XX\r\n"
# Driver auto-detects mode. Gate XX * 70 cm = distance.
# ===================================================================


def example_basic_callbacks():
    """Example 1: Basic presence with callbacks."""
    from ld2420 import LD2420
    import time

    radar = LD2420(uart_id=1, tx_pin=15, rx_pin=16)

    def on_detect(dist):
        print(f"  -> Target at {dist} cm")

    def on_state(old, new):
        print(f"STATE: {'PRESENT' if old else 'EMPTY'}"
              f" -> {'PRESENT' if new else 'EMPTY'}")

    radar.on_detection(on_detect)
    radar.on_state_change(on_state)

    # Read firmware
    if radar.open_command_mode():
        print(f"Firmware: {radar.read_firmware_version()}")
        radar.close_command_mode()

    print("\n=== Monitoring (callbacks) ===\n")
    while True:
        radar.update()
        time.sleep_ms(20)


def example_polling():
    """Example 2: Simple polling without callbacks."""
    from ld2420 import LD2420
    import time

    radar = LD2420(uart_id=1, tx_pin=15, rx_pin=16)

    print("=== Polling Mode ===\n")
    while True:
        radar.update()
        if radar.is_fresh():
            if radar.presence:
                print(f"[PRESENT] gate={radar.gate}"
                      f"  dist={radar.distance} cm"
                      f"  mode={radar.mode}")
            else:
                print("[  EMPTY ]")
        time.sleep_ms(500)


def example_smart_led():
    """Example 3: NeoPixel LED control based on presence."""
    from ld2420 import LD2420
    from machine import Pin
    from neopixel import NeoPixel
    import time

    NUM_LEDS = 8
    OFF_DELAY = 20000

    radar = LD2420(uart_id=1, tx_pin=15, rx_pin=16)
    np = NeoPixel(Pin(5), NUM_LEDS)

    last_on = 0
    light_on = False

    def set_leds(r, g, b):
        for i in range(NUM_LEDS):
            np[i] = (r, g, b)
        np.write()

    def on_detect(dist):
        nonlocal last_on, light_on
        last_on = time.ticks_ms()
        if dist < 150:    set_leds(0, 40, 0)
        elif dist < 400:  set_leds(40, 30, 0)
        else:             set_leds(40, 0, 0)
        if not light_on:
            print(f"LEDs ON - {dist} cm")
            light_on = True

    radar.on_detection(on_detect)
    set_leds(0, 0, 0)
    print("=== Smart LED ===\n")

    while True:
        radar.update()
        if light_on and not radar.presence:
            if time.ticks_diff(time.ticks_ms(), last_on) > OFF_DELAY:
                set_leds(0, 0, 0)
                light_on = False
                print("LEDs OFF")
        time.sleep_ms(50)


def example_mqtt():
    """Example 4: MQTT presence reporter."""
    from ld2420 import LD2420
    import network, time, json
    from umqtt.simple import MQTTClient

    WIFI_SSID = "YOUR_SSID"
    WIFI_PASS = "YOUR_PASSWORD"
    MQTT_BROKER = "192.168.1.100"
    MQTT_TOPIC = "home/room1/presence"

    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(WIFI_SSID, WIFI_PASS)
    while not wlan.isconnected(): time.sleep_ms(500)
    print(f"IP: {wlan.ifconfig()[0]}")

    mqtt = MQTTClient("esp32_ld2420", MQTT_BROKER)
    mqtt.connect()

    radar = LD2420(uart_id=1, tx_pin=15, rx_pin=16)

    last_pub = 0

    def on_data(r):
        nonlocal last_pub
        now = time.ticks_ms()
        if time.ticks_diff(now, last_pub) < 2000: return
        last_pub = now
        payload = json.dumps({
            "presence": r.presence,
            "distance_cm": r.distance,
            "gate": r.gate
        })
        mqtt.publish(MQTT_TOPIC, payload)
        print(f"Published: {payload}")

    radar.on_data_update(on_data)
    print("=== MQTT Reporter ===\n")

    while True:
        radar.update()
        time.sleep_ms(50)


def example_config():
    """Example 5: Read sensor configuration."""
    from ld2420 import LD2420

    radar = LD2420(uart_id=1, tx_pin=15, rx_pin=16)

    if not radar.open_command_mode():
        print("ERROR: Cannot enter command mode")
        return

    print(f"Firmware: {radar.read_firmware_version()}\n")

    cfg = radar.read_config()
    if cfg:
        print(f"Min Gate : {cfg['min_gate']}")
        print(f"Max Gate : {cfg['max_gate']}")
        print(f"Timeout  : {cfg['timeout']} s\n")
        print("Gate | Trigger | Hold")
        print("-----|---------|--------")
        for g in range(16):
            print(f"  {g:2d} | {cfg['trigger_thresh'][g]:7d}"
                  f" | {cfg['hold_thresh'][g]:6d}")

    radar.close_command_mode()


def example_async():
    """Example 6: Async with uasyncio."""
    from ld2420 import LD2420
    from machine import Pin
    import uasyncio as asyncio

    radar = LD2420(uart_id=1, tx_pin=15, rx_pin=16)
    led = Pin(2, Pin.OUT)

    def on_state(old, new):
        led.value(1 if new else 0)
        tag = '>> ARRIVED' if new else '<< DEPARTED'
        print(f"{tag} ({radar.distance} cm)")

    radar.on_state_change(on_state)

    async def poll():
        while True:
            radar.update()
            await asyncio.sleep_ms(20)

    async def heartbeat():
        while True:
            if radar.valid:
                s = "PRESENT" if radar.presence else "empty"
                print(f"[HB] {s} gate={radar.gate} dist={radar.distance} cm")
            await asyncio.sleep(5)

    async def main():
        print("=== Async LD2420 ===\n")
        await asyncio.gather(poll(), heartbeat())

    asyncio.run(main())
