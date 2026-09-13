# Argon-only compatibility

Target: Particle Argon, Device OS 1.5.2, SYSTEM_MODE(MANUAL). No Wire/I2C, Xenons, GPIO peripherals, or network setup. Only USB serial and RGB are used. This retains the reviewed target, not a claim that Argon requires an obsolete OS. Particle cloud compilation succeeded for this target. Flashing and physical serial behavior remain unverified here.

USB APIs retained from the prior source audit: Serial.begin(115200), blockOnOverrun(false), isConnected(), availableForWrite(). Boot correlation uses HAL_RNG_GetRandomNumber. See official Device OS v1.5.2 wiring/src/spark_wiring_usbserial.cpp, hal/src/nRF52840/usb_hal.cpp, wiring/inc/spark_wiring_rgb.h, and hal/inc/rng_hal.h in https://github.com/particle-iot/device-os/tree/v1.5.2 . The Particle cloud toolchain compiled this application successfully; see VALIDATION.md.
