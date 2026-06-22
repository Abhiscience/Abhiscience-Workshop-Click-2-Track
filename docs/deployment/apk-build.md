# APK Build Guide

This guide covers building the Android APK for production and testing.

## Prerequisites

- Android Studio installed
- Java JDK 11+
- Android SDK configured
- (Optional) Generate Signed APK requires keystore

## Building Debug APK

For testing and development:

```bash
# Navigate to mobile app directory
cd apps/mobile-android

# Build debug APK
./gradlew assembleDebug

# Find the APK
ls app/build/outputs/apk/debug/app-debug.apk
```

## Building Release APK

For production deployment:

### 1. Generate Keystore (if not exists)

```bash
# Create keystore directory
mkdir -p ~/.android-keys

# Generate keystore
keytool -genkeypair \
  -v \
  -keystore ~/.android-keys/workshop-release-key.jks \
  -alias workshop-key \
  -keyalg RSA \
  -keysize 2048 \
  -validity 10000
```

### 2. Configure Signing

Create `app/keystore.properties`:
```properties
storePassword=YOUR_STORE_PASSWORD
keyPassword=YOUR_KEY_PASSWORD
keyAlias=workshop-key
storeFile=/full/path/to/workshop-release-key.jks
```

### 3. Build Release

```bash
./gradlew assembleRelease

# Find release APK
ls app/build/outputs/apk/release/app-release.apk
```

## APK Output Variants

| Variant | Command | Purpose |
|---------|---------|---------|
| debug | `./gradlew assembleDebug` | Development, emulator testing |
| release | `./gradlew assembleRelease` | Production distribution |
| emulator-test | `./gradlew assembleDebug -PemuMode=true` | Specialized emulator build |

## Installing the APK

### On Physical Device

```bash
# Enable USB debugging
# Connect device via USB

adb install -r app/build/outputs/apk/debug/app-debug.apk
```

### On Emulator

```bash
# Start emulator
emulator -avd Pixel_5_API_35

# Install
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

## APK Verification

```bash
# Check APK details
aapt dump badging app-debug.apk

# Verify signature
jarsigner -verify -verbose app-release.apk
```

## CI/CD Build

The `build.gradle` is configured for GitHub Actions. Add these secrets:

- `SIGNING_KEY_ALIAS`: workshop-key
- `SIGNING_KEY_PATH`: Base64 encoded keystore
- `SIGNING_STORE_PASSWORD`: Your store password
- `SIGNING_KEY_PASSWORD`: Your key password

## Versioning

Update in `app/build.gradle`:
```gradle
defaultConfig {
    versionCode 1  // Increment for each release
    versionName "1.0.0"  // Semantic version
}
```

## Troubleshooting

- **Build fails**: Check Java version (11+ required)
- **Missing SDK**: Run SDK manager in Android Studio
- **Permission denied**: chmod +x gradlew
- **Emulator camera**: Use emulator testing mode instead