# ESP32-S3 Touch AMOLED 1.75 Microphone Test - Session Consolidation
## Date: February 1, 2026
## ESPHome Version: 2026.1.3

---

## Executive Summary

This session focused on resolving an ESPHome validation error for the ES7210 audio ADC `mic_gain` parameter on the Waveshare ESP32-S3-Touch-AMOLED-1.75 development board, followed by a comprehensive documentation review that identified additional configuration issues and best practices.

---

## Problem Statement

### Initial Error
```
Failed config
audio_adc.es7210:
  Expected decibel with unit, got 37.5DB.
  mic_gain: 37.5DB
```

### Context
- **Hardware**: Waveshare ESP32-S3-Touch-AMOLED-1.75
- **ESPHome Version**: 2026.1.3
- **Previous Session**: Created mic diagnostic firmware v4 with 5 documentation-based corrections
- **Firmware Purpose**: Microphone level meter to diagnose audio input issues on the Sage voice assistant satellite device

---

## Root Cause Analysis

### The `mic_gain` Format Conundrum

The error message "Expected decibel with unit, got 37.5DB" presents a contradiction:

| Source | Format Shown | Notes |
|--------|--------------|-------|
| ESPHome ES7210 Docs (2025.12.5) | `37.5DB` (uppercase) | Documented as enum type |
| Error Message | "Expected decibel with unit" | Suggests templatable value expected |
| Waveshare Device Page | *Not specified* | Example omits `mic_gain` entirely |

**Hypothesis**: ESPHome 2026.1.x changed the `mic_gain` validation from a strict enum to a templatable decibel unit, but the documentation hasn't been updated. The validator now expects a specific format like `37.5 dB` (with space) or `37.5dB` (lowercase).

### Testing Strategy
Since the exact format is uncertain, three configurations were created:
1. **v4.2**: Uses `mic_gain: 37.5DB` (per current docs)
2. **v4.2-DEFAULT**: Omits `mic_gain` entirely (uses default 24DB)
3. **v4.1 (previous)**: Had `mic_gain: 37.5dB` (lowercase, attempted fix)

---

## Documentation Review Findings

### 1. Display Configuration Issues

**Previous Configuration (v4.1):**
```yaml
display:
  - platform: mipi_spi
    id: disp1
    spi_id: display_qspi  # NOT A DOCUMENTED PARAMETER
    model: CO5300         # Driver chip, not board preset
    bus_mode: quad
    reset_pin: GPIO39
    cs_pin: GPIO12
    dimensions:
      height: 466
      width: 466
```

**Issues Found:**
- `spi_id` is NOT listed as a configuration variable in the MIPI SPI display documentation
- `model: CO5300` uses the driver chip name; the board has a dedicated preset
- Manual pin configuration is unnecessary when using board preset

**Corrected Configuration (v4.2):**
```yaml
display:
  - platform: mipi_spi
    id: disp1
    model: WAVESHARE-ESP32-S3-TOUCH-AMOLED-1.75  # Board preset auto-configures all pins
    update_interval: 100ms
```

### 2. Audio ADC Configuration

**ES7210 Component Documentation (https://esphome.io/components/audio_adc/es7210/):**

| Parameter | Type | Default | Valid Values |
|-----------|------|---------|--------------|
| `bits_per_sample` | enum | 16bit | 16bit, 24bit, 32bit |
| `mic_gain` | enum | 24DB | 0DB, 3DB, 6DB, 9DB, 12DB, 15DB, 18DB, 21DB, 24DB, 27DB, 30DB, 33DB, 34.5DB, 36DB, 37.5DB |
| `sample_rate` | int | 16000 | Positive integer |
| `address` | int | 0x40 | I²C address |
| `i2c_id` | ID | - | Reference to I²C bus |

**Note**: The documentation example for ESP32-S3-Box-3 omits `mic_gain`, relying on the 24DB default.

### 3. Microphone Component Verification

**Verified Parameters (https://esphome.io/components/microphone/i2s_audio/):**

| Parameter | Our Value | Documentation |
|-----------|-----------|---------------|
| `adc_type` | external | ✓ Required for external ADC |
| `i2s_din_pin` | GPIO10 | ✓ Correct per Waveshare |
| `sample_rate` | 16000 | ✓ Default |
| `bits_per_sample` | 16bit | ✓ Valid (default is 32bit) |
| `pdm` | false | ✓ Correct for I²S |
| `channel` | right | ✓ Default per docs |
| `use_apll` | true | ✓ Better clock accuracy |
| `correct_dc_offset` | true | ✓ Helps center audio signal |

### 4. Speaker Component Verification

**Verified Parameters (https://esphome.io/components/speaker/i2s_audio/):**

| Parameter | Our Value | Notes |
|-----------|-----------|-------|
| `channel` | mono | ✓ ES8311 is mono codec |
| `use_apll` | true | ✓ Per Waveshare reference config |
| `timeout` | never | ✓ Prevents bus release |
| `buffer_duration` | 200ms | ✓ Default is 500ms |
| `audio_dac` | es8311_dac | ✓ Links to DAC component |

### 5. SPI Bus Configuration

**Current Configuration:**
```yaml
spi:
  - id: display_qspi
    type: quad
    clk_pin: GPIO38
    data_pins:
      - GPIO4
      - GPIO5
      - GPIO6
      - GPIO7
```

**Verification**: Matches Waveshare device page exactly. The `type: quad` is required for QSPI displays.

### 6. I²S Audio Bus Configuration

**Verified Against Waveshare Reference:**

| Bus | LRCLK | BCLK | MCLK | DIN/DOUT |
|-----|-------|------|------|----------|
| i2s_out (speaker) | GPIO45 | GPIO9 | GPIO42 | GPIO8 |
| i2s_in (mic) | GPIO45 | GPIO9 | (shared) | GPIO10 |

**Note**: `allow_other_uses: true` is required because LRCLK and BCLK are shared between input and output buses.

---

## Files Created/Modified

### New Files (v4.2)

| File | Purpose |
|------|---------|
| `sage-mic-test-v4.2.yaml` | Primary version with `mic_gain: 37.5DB` (uppercase) and board preset |
| `sage-mic-test-v4.2-DEFAULT.yaml` | Fallback version with default gain (no `mic_gain` specified) |

### Key Changes from v4.1

1. **Display model**: Changed from `CO5300` to `WAVESHARE-ESP32-S3-TOUCH-AMOLED-1.75`
2. **Display config**: Removed `spi_id`, `bus_mode`, `reset_pin`, `cs_pin`, `dimensions` (auto-configured by preset)
3. **mic_gain format**: Changed to uppercase `37.5DB` per documentation
4. **Comments**: Added comprehensive documentation references throughout

### Files Location

```
/mnt/user-data/outputs/
├── sage-mic-test-v4.2.yaml         # Primary - try this first
└── sage-mic-test-v4.2-DEFAULT.yaml # Fallback if mic_gain fails
```

---

## Testing Recommendations

### Step 1: Try Primary Configuration
```bash
# In ESPHome Dashboard, upload sage-mic-test-v4.2.yaml
# Watch for validation errors
```

### Step 2: If mic_gain Validation Fails
If you see "Expected decibel with unit" error again:
1. Use `sage-mic-test-v4.2-DEFAULT.yaml` (omits mic_gain)
2. The default 24DB gain should still be sufficient for testing

### Step 3: Verify Microphone Operation
After successful flash:
1. Device should auto-start mic test on boot (2 second delay)
2. Watch display for:
   - "SPEAK NOW!" status (green = active)
   - Bytes counter increasing (proves I²S data flow)
   - Level bar responding to sound
3. Check logs for:
   ```
   [mic] Level: XX% | Peak: XX% | Bytes: XXXXX
   ```

### Step 4: If Bytes Increase but Level Stays 0%
This indicates data is flowing but on wrong channel:
1. Switch to LEFT channel version (create by changing `channel: right` to `channel: left`)
2. Or create a new file with `channel: stereo` to capture both

---

## Outstanding Issues / Uncertainties

### 1. mic_gain Format (UNRESOLVED)
The exact format ESPHome 2026.1.3 expects is unclear:
- Documentation shows uppercase `DB` suffix
- Error message suggests different format expected
- May be a bug in ESPHome 2026.1.x validation

**Recommended Action**: If uppercase fails, try lowercase `dB`, then fall back to default.

### 2. Display Board Preset Compatibility
The `WAVESHARE-ESP32-S3-TOUCH-AMOLED-1.75` preset was documented in MIPI SPI driver docs (release 2025.12.2), but should verify it exists in ESPHome 2026.1.3.

**Fallback**: If preset not found, revert to manual configuration:
```yaml
display:
  - platform: mipi_spi
    model: CO5300
    bus_mode: quad
    reset_pin: GPIO39
    cs_pin: GPIO12
    dimensions:
      height: 466
      width: 466
```

### 3. GPIO45 Strapping Pin Warning
GPIO45 is used for I²S LRCLK but is also an ESP32-S3 strapping pin. The warning is expected and safe for this hardware design per Waveshare documentation.

---

## Reference Documentation

| Component | URL |
|-----------|-----|
| ES7210 Audio ADC | https://esphome.io/components/audio_adc/es7210/ |
| I²S Audio Microphone | https://esphome.io/components/microphone/i2s_audio/ |
| I²S Audio Speaker | https://esphome.io/components/speaker/i2s_audio/ |
| MIPI SPI Display | https://esphome.io/components/display/mipi_spi/ |
| SPI Bus | https://esphome.io/components/spi/ |
| Waveshare Device | https://devices.esphome.io/devices/waveshare-esp32-s3-touch-amoled-1.75/ |
| ESPHome Core | https://esphome.io/components/esphome/ |

---

## Previous Session Context

This work continues from session documented in:
```
/mnt/transcripts/2026-02-01-23-02-00-esp32-mic-test-v4-gain-format-fix.txt
```

Previous session created v4/v4.1 with these corrections:
1. Changed microphone channel from `left` to `right` (default per docs)
2. Added `use_apll: true` to microphone and speaker
3. Added `correct_dc_offset: true` to microphone
4. Changed speaker channel to `mono` (ES8311 is mono codec)
5. Used `mic_gain: 37.5DB` format (which then failed validation)

---

## Summary of Configuration Evolution

| Version | mic_gain | Display Model | Status |
|---------|----------|---------------|--------|
| v4 | 37.5DB | CO5300 + manual pins | Validation error |
| v4.1 | 37.5dB | CO5300 + manual pins + spi_id | Attempted fix |
| v4.2 | 37.5DB | Board preset | **Current - to test** |
| v4.2-DEFAULT | (omitted) | Board preset | Fallback |

---

## Next Steps

1. **Test v4.2** - Flash and check for validation errors
2. **Test microphone** - Verify bytes received and level response
3. **Report back** - Which configuration compiled successfully
4. **If working** - Proceed with Sage voice assistant integration
5. **If still failing** - Open ESPHome GitHub issue about mic_gain validation

---

*Document generated: February 1, 2026*
*Session focus: ESPHome ES7210 mic_gain validation and comprehensive configuration review*
