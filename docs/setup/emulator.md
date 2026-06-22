# MacBook Emulator Testing Guide

This guide covers testing the Android app on MacBook using Android Studio emulator.

## Prerequisites

- Android Studio installed on MacBook
- Android SDK configured
- At least one AVD (Android Virtual Device) created

## Setting Up Android Emulator

### 1. Install Android Studio

```bash
# Using Homebrew
brew install --cask android-studio
```

### 2. Create AVD

1. Open Android Studio
2. Go to Tools → AVD Manager
3. Create Virtual Device
4. Select Pixel 5 or similar
5. Download system image (API 35 recommended)
6. Create AVD

### 3. Run the App

```bash
# Start emulator from terminal (optional)
emulator -avd Pixel_5_API_35 -no-snapshot-load

# Build APK
./gradlew assembleDebug

# Install on emulator
./gradlew installDebug
```

## Emulator Test Mode

The app automatically detects emulator environment and switches to **Gallery Selection Mode**:

- **Production mode**: Live camera capture required
- **Emulator mode**: File/image selection from gallery

When testing on emulator:
1. Gallery picker opens instead of camera
2. Select test car images from gallery
3. Plate recognition still works via mock provider
4. All other features function identically

## Test Images

Sample car images are provided in `scripts/seed/test-images/` with pre-defined plates:

| Image | Expected Plate |
|-------|---------------|
| car1.jpg | A12345 (UAE) |
| car2.jpg | MH01AB1234 (India) |
| car3.jpg | B67890 (UAE) |
| car4.jpg | DL02CD5678 (India) |

## Debugging Tips

```bash
# View logs
adb logcat | grep "Workshop"

# Clear app data
adb shell pm clear com.workshop.click2track

# Force stop
adb shell am force-stop com.workshop.click2track
```

## Troubleshooting

- **Camera not working on emulator**: Expected! Use gallery mode
- **Network errors**: Ensure backend is running on localhost:8000
- **Slow emulator**: Enable hardware acceleration in BIOS/EFI settings
- **Gallery empty**: Pull test images to emulator first