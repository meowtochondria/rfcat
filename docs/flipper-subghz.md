# Technical Document: Flipper Zero Sub-GHz Protocol System

## Porting from C to Python 3 for rflib/rfcat Integration

---

## 1. Executive Summary

The Flipper Zero Sub-GHz system provides comprehensive support for encoding and decoding 50+ sub-1GHz RF protocols. The architecture uses a **parallel decoding approach** where all protocol decoders simultaneously attempt to decode every incoming signal, with the first successful decoder winning.

This document describes the system architecture, all protocol types, encoding/decoding patterns, and provides detailed guidance for implementing a Python 3 port.

---

## 2. System Architecture Overview

### 2.1 Core Components

```
┌─────────────────────────────────────────────────────────────────────┐
│                         SubGhzEnvironment                           │
│  - protocol_registry (list of all protocols)                        │
│  - keystore (encryption keys for Keeloq, etc.)                      │
│  - rainbow tables (Came Atomo, Nice Flor-S, Alutech AT-4N)          │
└─────────────────────────────────────────────────────────────────────┘
                                    │
            ┌───────────────────────┼───────────────────────┐
            ▼                       ▼                       ▼
    ┌───────────────┐      ┌───────────────┐      ┌───────────────┐
    │   Receiver    │      │  Transmitter  │      │  File Worker  │
    │ (decode only) │      │ (encode only) │      │ (RAW files)   │
    └───────────────┘      └───────────────┘      └───────────────┘
            │                       │                       │
            ▼                       │                       │
    ┌──────────────────────────────────────────────────────────────────┐
    │              Protocol Registry (50+ protocols)                   │
    │  Each protocol provides:                                         │
    │    - Decoder: alloc, free, feed, reset, get_hash_data, serialize │
    │    - Encoder: alloc, free, deserialize, stop, yield              │
    │    - Metadata: name, type, flags                                 │
    └──────────────────────────────────────────────────────────────────┘
```

### 2.2 Key Design Decision: "Let Everything Try" Parallel Decoding

Unlike a hierarchical protocol detection system, Flipper uses **parallel decoding**:

1. On `subghz_receiver_alloc_init()`, creates a decoder instance for **every** protocol
2. When raw signal data arrives via `subghz_receiver_decode(level, duration)`, **ALL** decoders receive the data
3. Each decoder independently processes the data through its own state machine
4. The first decoder to successfully decode a complete, valid signal wins and triggers a callback
5. Subsequent decoders continue running for subsequent signals

This approach works because:
- Each protocol has specific timing tolerances and signal patterns
- A decoder will reject invalid signals naturally (state machine won't reach "complete" state)
- False positives are filtered by requiring a complete, valid message

---

## 3. Core Type Definitions

### 3.1 Protocol Types (from `types.h`)

```c
enum SubGhzProtocolType {
    SubGhzProtocolTypeUnknown = 0,
    SubGhzProtocolTypeStatic,     // Fixed code (e.g., Princeton, Nice)
    SubGhzProtocolTypeDynamic,    // Rolling code (e.g., Keeloq, Somfy)
    SubGhzProtocolTypeRAW,        // Raw waveform recording
    SubGhzProtocolWeatherStation, // Weather station data
    SubGhzProtocolCustom,
};
```

### 3.2 Protocol Flags

```c
enum SubGhzProtocolFlag {
    SubGhzProtocolFlag_RAW       = (1 << 0),  // RAW protocol
    SubGhzProtocolFlag_Decodable = (1 << 1),  // Can decode
    SubGhzProtocolFlag_315       = (1 << 2),  // 315 MHz band
    SubGhzProtocolFlag_433       = (1 << 3),  // 433 MHz band
    SubGhzProtocolFlag_868       = (1 << 4),  // 868 MHz band
    SubGhzProtocolFlag_AM        = (1 << 5),  // AM modulation
    SubGhzProtocolFlag_FM        = (1 << 6),  // FM modulation
    SubGhzProtocolFlag_Save      = (1 << 7),  // Can save to file
    SubGhzProtocolFlag_Load      = (1 << 8),  // Can load from file
    SubGhzProtocolFlag_Send      = (1 << 9),  // Can transmit
    SubGhzProtocolFlag_BinRAW    = (1 << 10), // Binary RAW format
};
```

### 3.3 Status Codes

```c
enum SubGhzProtocolStatus {
    SubGhzProtocolStatusOk = 0,
    SubGhzProtocolStatusError = (-1),
    SubGhzProtocolStatusErrorParserHeader = (-2),
    SubGhzProtocolStatusErrorParserFrequency = (-3),
    SubGhzProtocolStatusErrorParserPreset = (-4),
    SubGhzProtocolStatusErrorParserCustomPreset = (-5),
    SubGhzProtocolStatusErrorParserProtocolName = (-6),
    SubGhzProtocolStatusErrorParserBitCount = (-7),
    SubGhzProtocolStatusErrorParserKey = (-8),
    SubGhzProtocolStatusErrorParserTe = (-9),
    SubGhzProtocolStatusErrorParserOthers = (-10),
    SubGhzProtocolStatusErrorValueBitCount = (-11),
    SubGhzProtocolStatusErrorEncoderGetUpload = (-12),
    SubGhzProtocolStatusErrorProtocolNotFound = (-13),
};
```

---

## 4. Signal Representation

### 4.1 Level and Duration

Flipper represents all RF signals as a stream of `(level, duration)` pairs:

- `level`: `True` = high/on, `False` = low/off
- `duration`: Time in **microseconds** the level lasts

Example signal:
```
(True, 350), (False, 700), (True, 350), (False, 700), (True, 1050), ...
```

### 4.2 LevelDuration Type

```c
// Represents one unit of signal (level + duration)
// Used for both encoding and decoding
typedef struct {
    bool level;       // high (true) or low (false)
    uint32_t duration; // time in microseconds
} LevelDuration;
```

### 4.3 Timing Constants (SubGhzBlockConst)

Each protocol defines timing constants:

```c
static const SubGhzBlockConst subghz_protocol_xxx_const = {
    .te_short = 390,       // Short pulse duration (µs)
    .te_long = 1170,       // Long pulse duration (µs)
    .te_delta = 300,       // Tolerance for matching (µs)
    .min_count_bit_for_found = 24, // Minimum bits for valid decode
};
```

---

## 5. Decoder Architecture

### 5.1 Decoder Interface

```c
typedef struct {
    void* (*alloc)(SubGhzEnvironment* environment);    // Create decoder instance
    void (*free)(void* context);                        // Destroy decoder instance
    void (*feed)(void* decoder, bool level, uint32_t duration); // Process signal
    void (*reset)(void* decoder);                       // Reset state machine
    uint8_t (*get_hash_data)(void* decoder);            // Get hash of last message
    SubGhzProtocolStatus (*serialize)(...);              // Serialize to file
    SubGhzProtocolStatus (*deserialize)(...);            // Deserialize from file
    void (*get_string)(void* decoder, FuriString* output); // Human-readable output
} SubGhzProtocolDecoder;
```

### 5.2 Decoder State Machine Structure

```c
struct SubGhzBlockDecoder {
    uint32_t parser_step;      // Current state in decoding state machine
    uint32_t te_last;          // Last recorded duration
    uint64_t decode_data;      // Accumulated decoded bits
    uint8_t decode_count_bit;  // Number of bits accumulated
};
```

### 5.3 Decoder Callback

```c
typedef void (*SubGhzProtocolDecoderBaseRxCallback)(
    SubGhzProtocolDecoderBase* instance, void* context);

// When decoder successfully decodes a message, it calls:
if (instance->base.callback)
    instance->base.callback(&instance->base, instance->base.context);
```

### 5.4 Receiver Implementation

```c
void subghz_receiver_decode(SubGhzReceiver* instance, bool level, uint32_t duration) {
    // Broadcast to ALL protocol decoders
    for (M_EACH(slot, instance->slots, SubGhzReceiverSlotArray_t)) {
        if ((slot->base->protocol->flag & instance->filter) != 0) {
            slot->base->protocol->decoder->feed(slot->base, level, duration);
        }
    }
}
```

---

## 6. Encoder Architecture

### 6.1 Encoder Interface

```c
typedef struct {
    void* (*alloc)(SubGhzEnvironment* environment);    // Create encoder instance
    void (*free)(void* context);                       // Destroy encoder instance
    SubGhzProtocolStatus (*deserialize)(void*, FlipperFormat*); // Load from file
    void (*stop)(void* encoder);                       // Stop transmission
    LevelDuration (*yield)(void* context);             // Get next level/duration
} SubGhzProtocolEncoder;
```

### 6.2 Encoder Block Structure

```c
typedef struct {
    bool is_running;            // Currently transmitting
    size_t repeat;              // Number of repetitions remaining
    size_t front;               // Current position in upload buffer
    size_t size_upload;         // Total size of upload buffer
    LevelDuration* upload;       // Buffer of LevelDuration values
} SubGhzProtocolBlockEncoder;
```

### 6.3 Yield Pattern for Transmission

```c
LevelDuration subghz_transmitter_yield(void* context) {
    SubGhzTransmitter* instance = context;
    
    if (instance->encoder.repeat == 0 || !instance->encoder.is_running) {
        instance->encoder.is_running = false;
        return level_duration_reset();  // Signal end of transmission
    }
    
    LevelDuration ret = instance->encoder.upload[instance->encoder.front];
    
    if (++instance->encoder.front == instance->encoder.size_upload) {
        instance->encoder.repeat--;
        instance->encoder.front = 0;
    }
    
    return ret;
}
```

---

## 7. Common Block Utilities (`blocks/`)

### 7.1 Generic Block Data

```c
struct SubGhzBlockGeneric {
    const char* protocol_name;   // Protocol name string
    uint64_t data;              // Decoded/encoded data
    uint32_t serial;            // Serial/remote ID
    uint16_t data_count_bit;    // Number of data bits
    uint8_t btn;                // Button code
    uint32_t cnt;               // Counter (for rolling codes)
};
```

### 7.2 Bit Manipulation Macros

```c
#define bit_read(value, bit) (((value) >> (bit)) & 0x01)
#define bit_set(value, bit) ((value) |= (1 << (bit)))
#define bit_clear(value, bit) ((value) &= ~(1 << (bit)))
#define bit_write(value, bit, bitvalue) (bitvalue ? bit_set(value, bit) : bit_clear(value, bit))
#define DURATION_DIFF(x, y) (((x) < (y)) ? ((y) - (x)) : ((x) - (y)))
```

### 7.3 CRC Functions

```c
// CRC-4
uint8_t subghz_protocol_blocks_crc4(uint8_t message[], size_t size, 
                                     uint8_t polynomial, uint8_t init);

// CRC-7  
uint8_t subghz_protocol_blocks_crc7(uint8_t message[], size_t size,
                                     uint8_t polynomial, uint8_t init);

// CRC-8
uint8_t subghz_protocol_blocks_crc8(uint8_t message[], size_t size,
                                     uint8_t polynomial, uint8_t init);

// CRC-8 Little Endian (LSB first)
uint8_t subghz_protocol_blocks_crc8le(uint8_t message[], size_t size,
                                       uint8_t polynomial, uint8_t init);

// CRC-16 LSB (LSB first)
uint16_t subghz_protocol_blocks_crc16lsb(uint8_t message[], size_t size,
                                          uint16_t polynomial, uint16_t init);

// CRC-16
uint16_t subghz_protocol_blocks_crc16(uint8_t message[], size_t size,
                                       uint16_t polynomial, uint16_t init);
```

### 7.4 LFSR Digest Functions

```c
// LFSR-based Toeplitz hash (forward)
uint8_t subghz_protocol_blocks_lfsr_digest8(uint8_t message[], size_t size,
                                             uint8_t gen, uint8_t key);

// LFSR-based Toeplitz hash (byte/bit reflected)
uint8_t subghz_protocol_blocks_lfsr_digest8_reflect(uint8_t message[], size_t size,
                                                      uint8_t gen, uint8_t key);

// 16-bit LFSR digest
uint16_t subghz_protocol_blocks_lfsr_digest16(uint8_t message[], size_t size,
                                                uint16_t gen, uint16_t key);
```

### 7.5 Parity and XOR Functions

```c
uint8_t subghz_protocol_blocks_parity8(uint8_t byte);           // Single byte parity
uint8_t subghz_protocol_blocks_parity_bytes(uint8_t message[], size_t size); // Multiple bytes
uint8_t subghz_protocol_blocks_xor_bytes(uint8_t message[], size_t size);    // XOR all bytes
uint8_t subghz_protocol_blocks_add_bytes(uint8_t message[], size_t size);     // Sum all bytes
uint8_t subghz_protocol_blocks_get_parity(uint64_t key, uint8_t bit_count);   // Bit parity
uint64_t subghz_protocol_blocks_reverse_key(uint64_t key, uint8_t bit_count); // Reverse bit order
```

### 7.6 Decoder Block Functions

```c
// Add bit to decode buffer
void subghz_protocol_blocks_add_bit(SubGhzBlockDecoder* decoder, uint8_t bit);

// Add bit to 128-bit decode buffer
void subghz_protocol_blocks_add_to_128_bit(SubGhzBlockDecoder* decoder, 
                                            uint8_t bit, uint64_t* head_64_bit);

// Get hash of decoded data
uint8_t subghz_protocol_blocks_get_hash_data(SubGhzBlockDecoder* decoder, size_t len);
```

### 7.7 Encoder Block Functions

```c
// Set bit in byte array
void subghz_protocol_blocks_set_bit_array(bool bit_value, uint8_t data_array[],
                                           size_t set_index_bit, size_t max_size_array);

// Get bit from byte array
bool subghz_protocol_blocks_get_bit_array(uint8_t data_array[], size_t read_index_bit);

// Generate upload from bit array (run-length encoding)
size_t subghz_protocol_blocks_get_upload_from_bit_array(
    uint8_t data_array[], size_t count_bit_data_array,
    LevelDuration* upload, size_t max_size_upload,
    uint32_t duration_bit, SubGhzProtocolBlockAlignBit align_bit);
```

---

## 8. Protocol Registry

### 8.1 All 50 Protocols

```c
const SubGhzProtocol* const subghz_protocol_registry_items[] = {
    &subghz_protocol_gate_tx,        // Gate TX (static)
    &subghz_protocol_keeloq,          // Keeloq (rolling code)
    &subghz_protocol_star_line,       // Star Line (rolling code)
    &subghz_protocol_nice_flo,        // Nice FLO (Manchester)
    &subghz_protocol_came,           // Came (static)
    &subghz_protocol_faac_slh,       // Faac SLH (rolling code)
    &subghz_protocol_nice_flor_s,    // Nice Flor-S (rolling code)
    &subghz_protocol_came_twee,      // Came Twee (Manchester)
    &subghz_protocol_came_atomo,      // Came Atomo (rolling code)
    &subghz_protocol_nero_sketch,     // Nero Sketch (rolling code)
    &subghz_protocol_ido,            // IDO (rolling code)
    &subghz_protocol_kia,            // Kia (rolling code)
    &subghz_protocol_hormann,        // Hormann (rolling code)
    &subghz_protocol_nero_radio,     // Nero Radio (rolling code)
    &subghz_protocol_somfy_telis,    // Somfy Telis (rolling code)
    &subghz_protocol_somfy_keytis,   // Somfy Keytis (rolling code)
    &subghz_protocol_scher_khan,     // Scher Khan (rolling code)
    &subghz_protocol_princeton,       // Princeton (static, simple)
    &subghz_protocol_raw,             // RAW (waveform capture)
    &subghz_protocol_linear,          // Linear (static)
    &subghz_protocol_secplus_v2,      // Security+ v2 (complex rolling)
    &subghz_protocol_secplus_v1,     // Security+ v1 (rolling code)
    &subghz_protocol_megacode,       // Megacode (rolling code)
    &subghz_protocol_holtek,         // Holtek (static)
    &subghz_protocol_chamb_code,     // Chamberlain Code (rolling code)
    &subghz_protocol_power_smart,    // Power Smart (static)
    &subghz_protocol_marantec,        // Marantec (static)
    &subghz_protocol_bett,           // Bett (static)
    &subghz_protocol_doitrand,       // Doitrand (static)
    &subghz_protocol_phoenix_v2,     // Phoenix v2 (rolling code)
    &subghz_protocol_honeywell_wdb,  // Honeywell WDB (rolling code)
    &subghz_protocol_magellan,       // Magellan (rolling code)
    &subghz_protocol_intertechno_v3, // Intertechno v3 (rolling code)
    &subghz_protocol_clemsa,         // Clemsa (rolling code)
    &subghz_protocol_ansonic,        // Ansonic (rolling code)
    &subghz_protocol_smc5326,        // SMC5326 (static)
    &subghz_protocol_holtek_th12x,   // Holtek HT12X (static)
    &subghz_protocol_linear_delta3,  // Linear Delta-3 (static)
    &subghz_protocol_dooya,          // Dooya (DCF)
    &subghz_protocol_alutech_at_4n,  // Alutech AT-4N (rolling code)
    &subghz_protocol_kinggates_stylo_4k, // KingGates Stylo 4K (rolling code)
    &subghz_protocol_bin_raw,        // Binary RAW (waveform)
    &subghz_protocol_mastercode,     // Mastercode (rolling code)
    &subghz_protocol_legrand,        // Legrand (rolling code)
    &subghz_protocol_dickert_mahs,   // Dickert Mahs (rolling code)
    &subghz_protocol_gangqi,         // Gangqi (static)
    &subghz_protocol_marantec24,     // Marantec 24 (rolling code)
    &subghz_protocol_hollarm,        // Hollarm (static)
    &subghz_protocol_hay21,          // Hay 21 (rolling code)
    &subghz_protocol_revers_rb2,     // Revers RB2 (static)
    &subghz_protocol_feron,         // Feron (static)
    &subghz_protocol_roger,          // Roger (rolling code)
};
```

---

## 9. Protocol Classification and Implementation Patterns

### 9.1 Static Protocols (Fixed Code)

Static protocols transmit the same data every time. These are typically simple garage door remotes, doorbells, etc.

**Example: Princeton**

```c
// Timing: TE_SHORT = 390µs, TE_LONG = 1170µs
// Encoding: Pulse Distance (short pulse = 0, long pulse = 1)
// Format: [Preamble ~14.6ms] [24 bits data] [Stop bit]

typedef enum {
    PrincetonDecoderStepReset = 0,
    PrincetonDecoderStepSaveDuration,
    PrincetonDecoderStepCheckDuration,
} PrincetonDecoderStep;

void subghz_protocol_decoder_princeton_feed(void* context, bool level, uint32_t duration) {
    SubGhzProtocolDecoderPrinceton* instance = context;
    
    switch (instance->decoder.parser_step) {
    case PrincetonDecoderStepReset:
        // Look for preamble: ~36 short pulses
        if ((!level) && (DURATION_DIFF(duration, TE_SHORT * 36) < TE_DELTA * 36)) {
            instance->decoder.parser_step = PrincetonDecoderStepSaveDuration;
            instance->decoder.decode_data = 0;
            instance->decoder.decode_count_bit = 0;
        }
        break;
    case PrincetonDecoderStepSaveDuration:
        if (level) {
            instance->decoder.te_last = duration;
            instance->decoder.parser_step = PrincetonDecoderStepCheckDuration;
        }
        break;
    case PrincetonDecoderStepCheckDuration:
        if (!level) {
            // Check for stop gap (long duration = end of message)
            if (duration >= TE_LONG * 2) {
                if (instance->decoder.decode_count_bit == min_count_bit_for_found) {
                    // Successfully decoded! Trigger callback
                    instance->generic.data = instance->decoder.decode_data;
                    instance->generic.data_count_bit = instance->decoder.decode_count_bit;
                    instance->base.callback(&instance->base, instance->base.context);
                }
                // Reset for next message
                instance->decoder.decode_data = 0;
                instance->decoder.decode_count_bit = 0;
            }
            
            // Manchester-style decoding:
            // short+long = 0, long+short = 1
            if (DURATION_DIFF(instance->decoder.te_last, TE_SHORT) < TE_DELTA &&
                DURATION_DIFF(duration, TE_LONG) < TE_DELTA * 3) {
                subghz_protocol_blocks_add_bit(&instance->decoder, 0);
            } else if (DURATION_DIFF(instance->decoder.te_last, TE_LONG) < TE_DELTA * 3 &&
                       DURATION_DIFF(duration, TE_SHORT) < TE_DELTA) {
                subghz_protocol_blocks_add_bit(&instance->decoder, 1);
            }
        }
        break;
    }
}
```

**Encoding (Princeton):**
```c
// For each bit:
//   0: high(TE) + low(TE*3)  
//   1: high(TE*3) + low(TE)
// Final: high(TE) + low(TE*GUARD_TIME)
```

### 9.2 Manchester Encoding Protocols

Manchester encoding ensures a clock transition in every bit, making synchronization easier.

**Example: Nice FLO**

```c
// Timing: TE_SHORT = 700µs, TE_LONG = 1400µs
// Encoding: Manchester (0 = short-low/high, 1 = long-low/short-high)
// Format: [Header 25ms] [Start bit] [12-24 bits data]

// Manchester encoding ensures clock transitions at bit boundaries
// Decoder checks: short-long = 0, long-short = 1
```

### 9.3 Rolling Code Protocols (Dynamic)

Rolling code protocols transmit a different code each time, preventing replay attacks. The code is encrypted using algorithms like Keeloq, Security+, etc.

**Example: Keeloq**

The Keeloq encryption algorithm uses:
- A 64-bit key (manufacturer key)
- A 16-bit counter that increments with each button press
- The serial number and button code

```c
// Keeloq structure
struct SubGhzProtocolDecoderKeeloq {
    SubGhzProtocolDecoderBase base;
    SubGhzBlockDecoder decoder;
    SubGhzBlockGeneric generic;
    uint16_t header_count;  // Sync counter
};

// Decrypted fields:
// - Serial number (28 bits)
// - Button code (4 bits)  
// - Rolling counter (16 bits)
// - Encrypted portion (32 bits)
```

### 9.4 Complex Rolling Code Protocols

**Security+ v2 (SecPlus V2)**

Uses a more complex encoding:
1. Manchester encoding for clock recovery
2. Buffer mixing and reordering
3. Header detection (0x3C0000000000)

```c
// Decoder uses Manchester decoder state machine
typedef struct {
    ManchesterState manchester_saved_state;
    uint64_t secplus_packet_1;  // First decoded packet
} SecPlus_v2Decoder;

typedef enum {
    SecPlus_v2DecoderStepReset = 0,
    SecPlus_v2DecoderStepDecoderData,
} SecPlus_v2DecoderStep;
```

### 9.5 RAW Protocol

The RAW protocol captures and replays exact waveform timing without decoding:

```c
struct SubGhzProtocolDecoderRAW {
    SubGhzProtocolDecoderBase base;
    int32_t* upload_raw;       // Signed level+durations
    uint16_t ind_write;         // Current write index
    // File I/O for large captures
    Storage* storage;
    FlipperFormat* flipper_file;
    // ...
};

void subghz_protocol_decoder_raw_feed(void* context, bool level, uint32_t duration) {
    // Just stores raw level/duration pairs, no decoding
    // Positive = high, Negative = low
    instance->upload_raw[instance->ind_write++] = (level ? duration : -duration);
}
```

---

## 10. File Format (SubGhz Flipper Format)

### 10.1 Regular Protocol File (.sub)

```
Filetype: Flipper SubGhz Key File
Version: 1
Frequency: 433920000
Preset: FuriHalSubGhzPresetOok650Async
Protocol: Princeton
Bit: 24
Key: 00112233445566778899AABBCC
```

### 10.2 RAW File Format

```
Filetype: Flipper SubGhz RAW File
Version: 1
Frequency: 433920000
Preset: FuriHalSubGhzPresetOok650Async
Protocol: RAW
RAW_Data: [array of signed 32-bit integers encoding (level, duration) pairs]
```

---

## 11. Python 3 Porting Recommendations

### 11.1 Project Structure

```
rfcat/
  protocols/
    __init__.py
    base.py              # Base classes (Protocol, Decoder, Encoder)
    registry.py          # Protocol registry
    blocks/
      __init__.py
      const.py           # SubGhzBlockConst equivalent
      decoder.py         # SubGhzBlockDecoder and helpers
      encoder.py         # SubGhzProtocolBlockEncoder and helpers
      generic.py         # SubGhzBlockGeneric
      math.py            # CRC, LFSR, parity functions
    protocols/
      __init__.py
      princeton.py
      nice_flo.py
      keeloq.py
      # ... all 50 protocols
```

### 11.2 Core Class Hierarchy

```python
# base.py
from dataclasses import dataclass
from enum import Enum, IntFlag
from typing import Callable, Optional, List, Dict, Any
from abc import ABC, abstractmethod

class SubGhzProtocolType(Enum):
    UNKNOWN = 0
    STATIC = 1
    DYNAMIC = 2
    RAW = 3
    WEATHER_STATION = 4
    CUSTOM = 5

class SubGhzProtocolFlag(IntFlag):
    RAW = 1 << 0
    DECODABLE = 1 << 1
    FREQ_315 = 1 << 2
    FREQ_433 = 1 << 3
    FREQ_868 = 1 << 4
    MOD_AM = 1 << 5
    MOD_FM = 1 << 6
    SAVE = 1 << 7
    LOAD = 1 << 8
    SEND = 1 << 9
    BIN_RAW = 1 << 10

@dataclass
class LevelDuration:
    level: bool      # True = high, False = low
    duration: int    # Microseconds

@dataclass 
class SubGhzBlockConst:
    te_short: int
    te_long: int
    te_delta: int
    min_count_bit_for_found: int

class Protocol(ABC):
    """Base class for all protocols"""
    
    @property
    @abstractmethod
    def name(self) -> str: ...
    
    @property
    @abstractmethod
    def type(self) -> SubGhzProtocolType: ...
    
    @property
    @abstractmethod
    def flag(self) -> SubGhzProtocolFlag: ...
    
    @property
    @abstractmethod
    def decoder(self) -> 'Decoder': ...
    
    @property
    @abstractmethod
    def encoder(self) -> 'Encoder': ...

class Decoder(ABC):
    """Base class for protocol decoders"""
    
    def __init__(self, environment: Optional['SubGhzEnvironment'] = None):
        self.parser_step = 0
        self.te_last = 0
        self.decode_data = 0
        self.decode_count_bit = 0
        self.callback: Optional[Callable] = None
        self.context: Any = None
    
    @abstractmethod
    def feed(self, level: bool, duration: int) -> None:
        """Process a level/duration pair"""
        pass
    
    @abstractmethod
    def reset(self) -> None:
        """Reset decoder state"""
        pass
    
    def get_hash_data(self) -> int:
        """Get hash of last decoded data"""
        data_bytes = self.decode_data.to_bytes(
            (self.decode_count_bit + 7) // 8, 'little')
        return sum(data_bytes) ^ data_bytes[0] if data_bytes else 0
    
    @abstractmethod
    def get_string(self) -> str:
        """Get human-readable representation"""
        pass

class Encoder(ABC):
    """Base class for protocol encoders"""
    
    def __init__(self, environment: Optional['SubGhzEnvironment'] = None):
        self.is_running = False
        self.repeat = 10
        self.front = 0
        self.upload: List[LevelDuration] = []
    
    @abstractmethod
    def deserialize(self, data: Dict[str, Any]) -> bool:
        """Load parameters from dict/file"""
        pass
    
    @abstractmethod
    def stop(self) -> None:
        """Stop transmission"""
        pass
    
    def yield_(self) -> LevelDuration:
        """Get next level/duration to transmit"""
        if self.repeat == 0 or not self.is_running:
            self.is_running = False
            return LevelDuration(level=False, duration=0)  # End signal
        
        result = self.upload[self.front]
        self.front += 1
        if self.front >= len(self.upload):
            self.repeat -= 1
            self.front = 0
        return result
```

### 11.3 Math Functions to Port

```python
# math.py

def bit_read(value: int, bit: int) -> int:
    return (value >> bit) & 1

def bit_set(value: int, bit: int) -> int:
    return value | (1 << bit)

def bit_clear(value: int, bit: int) -> int:
    return value & ~(1 << bit)

def duration_diff(x: int, y: int) -> int:
    return abs(x - y)

def reverse_key(key: int, bit_count: int) -> int:
    result = 0
    for i in range(bit_count):
        result = (result << 1) | bit_read(key, i)
    return result

def get_parity(key: int, bit_count: int) -> int:
    return sum(bit_read(key, i) for i in range(bit_count)) & 1

def crc8(data: bytes, polynomial: int, init: int = 0) -> int:
    remainder = init
    for byte in data:
        remainder ^= byte
        for _ in range(8):
            if remainder & 0x80:
                remainder = (remainder << 1) ^ polynomial
            else:
                remainder = remainder << 1
    return remainder

def crc8le(data: bytes, polynomial: int, init: int = 0) -> int:
    remainder = reverse_key(init, 8)
    polynomial = reverse_key(polynomial, 8)
    for byte in data:
        remainder ^= byte
        for _ in range(8):
            if remainder & 1:
                remainder = (remainder >> 1) ^ polynomial
            else:
                remainder = remainder >> 1
    return remainder

def crc16(data: bytes, polynomial: int, init: int = 0) -> int:
    remainder = init
    for byte in data:
        remainder ^= byte << 8
        for _ in range(8):
            if remainder & 0x8000:
                remainder = (remainder << 1) ^ polynomial
            else:
                remainder = remainder << 1
    return remainder

def crc16lsb(data: bytes, polynomial: int, init: int = 0) -> int:
    remainder = init
    for byte in data:
        remainder ^= byte
        for _ in range(8):
            if remainder & 1:
                remainder = (remainder >> 1) ^ polynomial
            else:
                remainder = remainder >> 1
    return remainder

def lfsr_digest8(data: bytes, gen: int, key: int) -> int:
    result = 0
    for byte in data:
        for i in range(7, -1, -1):
            if (byte >> i) & 1:
                result ^= key
            if key & 1:
                key = (key >> 1) ^ gen
            else:
                key = key >> 1
    return result

def lfsr_digest16(data: bytes, gen: int, key: int) -> int:
    result = 0
    for byte in data:
        for i in range(7, -1, -1):
            if (byte >> i) & 1:
                result ^= key
            if key & 1:
                key = (key >> 1) ^ gen
            else:
                key = key >> 1
    return result

def parity8(byte: int) -> int:
    byte ^= byte >> 4
    return (0x6996 >> (byte & 0xf)) & 1

def add_bytes(data: bytes) -> int:
    return sum(data) & 0xff
```

### 11.4 Example Protocol Implementation (Princeton)

```python
# protocols/princeton.py
from dataclasses import dataclass
from typing import Optional, Dict, Any
from protocols.base import (
    Protocol, Decoder, Encoder, LevelDuration,
    SubGhzProtocolType, SubGhzProtocolFlag, SubGhzBlockConst
)
from protocols.blocks.math import duration_diff, bit_read

SUBGHZ_PROTOCOL_PRINCETON_NAME = "Princeton"

PRINCETON_GUARD_TIME_DEFAULT = 30

PRINCETON_CONST = SubGhzBlockConst(
    te_short=390,
    te_long=1170,
    te_delta=300,
    min_count_bit_for_found=24
)

class PrincetonDecoder(Decoder):
    def __init__(self, environment=None):
        super().__init__(environment)
        self.generic.protocol_name = SUBGHZ_PROTOCOL_PRINCETON_NAME
        self.te = 0
        self.last_data = 0
        self.guard_time = PRINCETON_GUARD_TIME_DEFAULT
    
    def reset(self):
        self.parser_step = PrincetonDecoderStep.RESET
        self.last_data = 0
        self.te = 0
    
    def feed(self, level: bool, duration: int):
        if self.parser_step == PrincetonDecoderStep.RESET:
            # Look for preamble: ~36 short pulses at low level
            if (not level and 
                duration_diff(duration, PRINCETON_CONST.te_short * 36) < 
                    PRINCETON_CONST.te_delta * 36):
                self.parser_step = PrincetonDecoderStep.SAVE_DURATION
                self.decode_data = 0
                self.decode_count_bit = 0
                self.te = 0
                self.guard_time = PRINCETON_GUARD_TIME_DEFAULT
                
        elif self.parser_step == PrincetonDecoderStep.SAVE_DURATION:
            if level:
                self.te_last = duration
                self.te += duration
                self.parser_step = PrincetonDecoderStep.CHECK_DURATION
                
        elif self.parser_step == PrincetonDecoderStep.CHECK_DURATION:
            if not level:
                # Check for end gap
                if duration >= PRINCETON_CONST.te_long * 2:
                    self.parser_step = PrincetonDecoderStep.SAVE_DURATION
                    if (self.decode_count_bit == 
                            PRINCETON_CONST.min_count_bit_for_found):
                        if (self.last_data == self.decode_data and 
                                self.last_data != 0):
                            self.te //= (self.decode_count_bit * 4 + 1)
                            self.generic.data = self.decode_data
                            self.generic.data_count_bit = self.decode_count_bit
                            self.guard_time = round(duration / self.te)
                            if 15 <= self.guard_time <= 72:
                                if self.callback:
                                    self.callback(self, self.context)
                        self.last_data = self.decode_data
                    self.decode_data = 0
                    self.decode_count_bit = 0
                    self.te = 0
                    break
                
                self.te += duration
                
                # Check for 0 bit (short + long)
                if (duration_diff(self.te_last, PRINCETON_CONST.te_short) < 
                        PRINCETON_CONST.te_delta and
                    duration_diff(duration, PRINCETON_CONST.te_long) < 
                        PRINCETON_CONST.te_delta * 3):
                    self._add_bit(0)
                    self.parser_step = PrincetonDecoderStep.SAVE_DURATION
                    
                # Check for 1 bit (long + short)
                elif (duration_diff(self.te_last, PRINCETON_CONST.te_long) < 
                          PRINCETON_CONST.te_delta * 3 and
                      duration_diff(duration, PRINCETON_CONST.te_short) < 
                          PRINCETON_CONST.te_delta):
                    self._add_bit(1)
                    self.parser_step = PrincetonDecoderStep.SAVE_DURATION
                else:
                    self.parser_step = PrincetonDecoderStep.RESET
            else:
                self.parser_step = PrincetonDecoderStep.RESET
    
    def _add_bit(self, bit: int):
        self.decode_data = (self.decode_data << 1) | bit
        self.decode_count_bit += 1
    
    def get_string(self) -> str:
        serial = self.generic.data >> 4
        btn = self.generic.data & 0xF
        data_rev = reverse_key(self.generic.data, self.generic.data_count_bit)
        return (
            f"{self.generic.protocol_name} {self.generic.data_count_bit}bit\n"
            f"Key:0x{self.generic.data:08X}\n"
            f"Yek:0x{data_rev:08X}\n"
            f"Sn:0x{serial:05X} Btn:{btn:X}\n"
            f"Te:{self.te}us  GT:Te*{self.guard_time}"
        )

class PrincetonEncoder(Encoder):
    def __init__(self, environment=None):
        super().__init__(environment)
        self.generic.protocol_name = SUBGHZ_PROTOCOL_PRINCETON_NAME
        self.te = PRINCETON_CONST.te_short
        self.guard_time = PRINCETON_GUARD_TIME_DEFAULT
    
    def deserialize(self, data: Dict[str, Any]) -> bool:
        self.generic.data = data.get('key', 0)
        self.generic.data_count_bit = data.get('bit', 24)
        self.repeat = data.get('repeat', 10)
        self.te = data.get('te', PRINCETON_CONST.te_short)
        self.guard_time = data.get('guard_time', PRINCETON_GUARD_TIME_DEFAULT)
        return self._generate_upload()
    
    def _generate_upload(self) -> bool:
        self.upload = []
        # Send key data
        for i in range(self.generic.data_count_bit - 1, -1, -1):
            bit = bit_read(self.generic.data, i)
            if bit:
                self.upload.append(LevelDuration(True, self.te * 3))
                self.upload.append(LevelDuration(False, self.te))
            else:
                self.upload.append(LevelDuration(True, self.te))
                self.upload.append(LevelDuration(False, self.te * 3))
        # Send stop bit
        self.upload.append(LevelDuration(True, self.te))
        # Send guard time
        self.upload.append(LevelDuration(False, self.te * self.guard_time))
        self.is_running = True
        return True
    
    def stop(self):
        self.is_running = False

class PrincetonProtocol(Protocol):
    @property
    def name(self) -> str:
        return SUBGHZ_PROTOCOL_PRINCETON_NAME
    
    @property
    def type(self) -> SubGhzProtocolType:
        return SubGhzProtocolType.STATIC
    
    @property
    def flag(self) -> SubGhzProtocolFlag:
        return (SubGhzProtocolFlag.FREQ_433 | 
                SubGhzProtocolFlag.FREQ_868 |
                SubGhzProtocolFlag.FREQ_315 |
                SubGhzProtocolFlag.MOD_AM |
                SubGhzProtocolFlag.DECODABLE |
                SubGhzProtocolFlag.LOAD |
                SubGhzProtocolFlag.SAVE |
                SubGhzProtocolFlag.SEND)
    
    @property
    def decoder(self) -> PrincetonDecoder:
        return PrincetonDecoder
    
    @property
    def encoder(self) -> PrincetonEncoder:
        return PrincetonEncoder

# Global protocol instance
subghz_protocol_princeton = PrincetonProtocol()
```

### 11.5 Receiver Implementation

```python
# receiver.py
from typing import List, Optional, Callable, Dict
from protocols.base import Protocol, Decoder, Encoder, LevelDuration, SubGhzProtocolFlag

class Receiver:
    def __init__(self, environment: Optional['SubGhzEnvironment'] = None,
                 protocol_registry: List[Protocol] = None):
        self.slots: List[Decoder] = []
        self.filter = SubGhzProtocolFlag(0xFFFFFFFF)  # Enable all
        self.callback: Optional[Callable] = None
        self.context = None
        
        # Create decoder instance for each protocol
        for protocol in protocol_registry:
            if protocol.decoder:
                decoder = protocol.decoder(environment)
                decoder.callback = self._rx_callback
                decoder.context = self
                self.slots.append(decoder)
    
    def decode(self, level: bool, duration: int):
        """Feed level/duration to all decoders"""
        for slot in self.slots:
            if slot.protocol.flag & self.filter:
                slot.feed(level, duration)
    
    def reset(self):
        """Reset all decoders"""
        for slot in self.slots:
            slot.reset()
    
    def set_filter(self, flag: SubGhzProtocolFlag):
        """Set protocol filter"""
        self.filter = flag
    
    def set_rx_callback(self, callback: Callable, context=None):
        """Set callback for successful decode"""
        self.callback = callback
        self.context = context
    
    def _rx_callback(self, decoder: Decoder, context):
        if self.callback:
            self.callback(self, decoder, self.context)
    
    def search_decoder_by_name(self, name: str) -> Optional[Decoder]:
        for slot in self.slots:
            if slot.protocol.name == name:
                return slot
        return None
```

### 11.6 Transmitter Implementation

```python
# transmitter.py
from typing import Optional, Dict
from protocols.base import Protocol, Encoder, LevelDuration

class Transmitter:
    def __init__(self, environment: Optional['SubGhzEnvironment'] = None,
                 protocol_registry: Optional[Dict[str, Protocol]] = None):
        self.protocol: Optional[Protocol] = None
        self.protocol_instance: Optional[Encoder] = None
        
        if protocol_registry and protocol_name:
            self.protocol = protocol_registry.get(protocol_name)
            if self.protocol and self.protocol.encoder:
                self.protocol_instance = self.protocol.encoder(environment)
    
    def deserialize(self, data: Dict) -> bool:
        """Load protocol parameters and generate upload"""
        if self.protocol_instance:
            return self.protocol_instance.deserialize(data)
        return False
    
    def stop(self) -> bool:
        if self.protocol_instance:
            self.protocol_instance.stop()
            return True
        return False
    
    def yield_(self) -> LevelDuration:
        """Get next level/duration for transmission"""
        if self.protocol_instance:
            return self.protocol_instance.yield_()
        return LevelDuration(level=False, duration=0)
```

---

## 12. Rainbow Tables and Keeloq Support

The original Flipper firmware uses rainbow tables for some protocols that require pre-computed decryption keys. For the Python port:

```python
# keystore.py
class Keystore:
    """Simple key storage for encrypted protocols"""
    
    def __init__(self):
        self.keys: Dict[str, bytes] = {}  # manufacturer_id -> key
    
    def load_from_file(self, filename: str):
        """Load .keeloq_mfcodes files"""
        # Parse Flipper keystore format
        pass
    
    def get_key(self, manufacturer_id: str) -> Optional[bytes]:
        return self.keys.get(manufacturer_id)
    
    def set_key(self, manufacturer_id: str, key: bytes):
        self.keys[manufacturer_id] = key
```

---

## 13. Testing Recommendations

1. **Unit tests for each protocol**: Test encoding/decoding of known test vectors
2. **Round-trip testing**: Encode then decode, verify data matches
3. **Reference comparison**: Compare Python output with C implementation for same input
4. **Integration with rflib**: Test with actual hardware when available

---

## 14. Performance Considerations

1. **Object creation overhead**: Consider object pooling for frequently created/destroyed decoder instances
2. **Bit operations**: Python's integer operations are adequate; avoid excessive bit manipulation in hot paths
3. **CRC calculations**: Pre-compute lookup tables where possible
4. **Callback overhead**: Minimize function call overhead in decoder feed()

---

## 15. Future Enhancements

1. **Jit compilation**: Use Numba for hot paths if needed
2. **C extension**: Port critical math functions to C for performance
3. **Protocol inference**: Auto-detect protocol from signal characteristics
4. **Signal analysis**: Provide utilities for analyzing unknown signals

---

## 16. Appendix: Signal Format Reference

### Common Timing Values
- `TE_SHORT` typically 300-700µs
- `TE_LONG` typically 2-3x TE_SHORT
- `TE_DELTA` typically 30-50% of TE_SHORT
- Preamble typically 10-50 TE_SHORT durations
- Guard time typically 15-72x TE_SHORT

### Modulation Types
- **AM (On-Off Keying)**: Carrier on/off to represent data
- **FM (Frequency Shift)**: Two frequencies represent 0/1 (used in 2FSK)

### Encoding Types
- **Pulse Width**: Bit determined by high pulse duration
- **Pulse Distance**: Bit determined by low pulse duration
- **Manchester**: Clock transition in middle of each bit
- **Biphase**: Clock transition at start of each bit
```

---

**Summary of key points for the porting agent:**

1. **Core Architecture**: Parallel decoding where all protocols try to decode every signal
2. **Signal Representation**: Stream of `(level: bool, duration: int)` tuples in microseconds
3. **50+ Protocols** to implement, classified as Static, Dynamic (rolling code), or RAW
4. **Key patterns**: Princeton (simple), Nice FLO (Manchester), Keeloq/Somfy (encrypted rolling codes)
5. **Common utilities**: CRC functions, LFSR digests, parity calculations, Manchester encoding/decoding
6. **File format**: Simple text-based format with key=value pairs
7. **Python structure**: Classes for Protocol, Decoder, Encoder, Receiver, Transmitter
8. **Testing**: Round-trip encode/decode testing, reference comparison with C implementation
