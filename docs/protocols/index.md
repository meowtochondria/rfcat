# RFCat Sub-GHz Protocol Implementation

This directory contains the implementation of Sub-GHz RF protocols for rfcat, ported from the Flipper Zero firmware. The implementation supports both receiving/decoding and sending/encoding of static (fixed code) RF protocols.

## Overview

The protocol system uses a **parallel decoding architecture** where all protocol decoders simultaneously attempt to decode every incoming signal. The first decoder to successfully decode a complete, valid signal triggers a callback.

## Quick Start

```python
from rflib.protocols import (
    PROTOCOL_REGISTRY, PROTOCOL_LIST,
    Receiver, Transmitter,
)

# RECEIVING: Create a receiver and feed it signal data
rx = Receiver(PROTOCOL_LIST)
rx.set_rx_callback(on_protocol_decoded)

# Feed (level, duration) pairs from your RF hardware
for level, duration in rf_signal_data:
    rx.feed(level, duration)

# SENDING: Create a transmitter and encode data
tx = Transmitter(PROTOCOL_REGISTRY)
tx.load('Princeton', {'key': 0xDEADBEEF, 'bit': 24, 'repeat': 10})

# Yield LevelDuration pairs to send via your RF hardware
while True:
    ld = tx.yield_()
    if ld.duration == 0:  # End of transmission
        break
    send_rf_signal(ld.level, ld.duration)
```

## Core Concepts

### Signal Representation

All RF signals are represented as streams of `(level, duration)` pairs:
- `level`: `True` = high/on, `False` = low/off
- `duration`: Time in microseconds the level lasts

Example signal: `(True, 350), (False, 700), (True, 350), (False, 700)...`

### Protocol Types

| Type | Description | Example |
|------|-------------|---------|
| `STATIC` | Fixed code (same data each transmission) | Princeton, GateTX |
| `DYNAMIC` | Rolling code (encrypted, changes each press) | Keeloq, Somfy |
| `RAW` | Raw waveform capture/replay | RAW protocol |

### Timing Constants

Each protocol defines timing constants via `SubGhzBlockConst`:

```python
@dataclass
class SubGhzBlockConst:
    te_short: int      # Short pulse duration (µs)
    te_long: int        # Long pulse duration (µs)
    te_delta: int       # Tolerance for matching (µs)
    min_count_bit_for_found: int  # Minimum bits for valid decode
```

### LevelDuration

Represents a single unit of RF signal:

```python
@dataclass
class LevelDuration:
    level: bool      # True = high, False = low
    duration: int    # Microseconds
```

## Architecture

### Class Hierarchy

```
Protocol (ABC)
├── PrincetonProtocol
└── GateTXProtocol

Decoder (ABC)
├── PrincetonDecoder
└── GateTXDecoder

Encoder (ABC)
├── PrincetonEncoder
└── GateTXEncoder

Receiver
└── Manages multiple Decoder instances (one per protocol)

Transmitter
└── Manages a single Encoder instance for selected protocol
```

### Protocol Class

Each protocol provides:

```python
class Protocol(ABC):
    @property
    def name(self) -> str:  # Protocol name (e.g., "Princeton")

    @property
    def type(self) -> SubGhzProtocolType:  # STATIC, DYNAMIC, RAW

    @property
    def flag(self) -> SubGhzProtocolFlag:  # Frequency, modulation, capabilities

    @property
    def decoder_cls(self):  # Decoder class for this protocol

    @property
    def encoder_cls(self):  # Encoder class for this protocol
```

### Decoder Class

Decoders process `(level, duration)` signal streams and detect valid protocol messages.

```python
class Decoder(ABC):
    def __init__(self, environment=None):
        self.parser_step = 0       # Current state in decode state machine
        self.te_last = 0          # Last recorded duration
        self.decode_data = 0       # Accumulated decoded bits
        self.decode_count_bit = 0  # Number of bits accumulated
        self.callback = None       # Called on successful decode
        self.context = None

    def feed(self, level: bool, duration: int) -> None:
        """Process a level/duration pair"""

    def reset(self) -> None:
        """Reset decoder state machine"""

    def get_hash_data(self) -> int:
        """Get hash of last decoded data"""

    def get_string(self) -> str:
        """Get human-readable representation"""
```

### Encoder Class

Encoders generate `(level, duration)` signal streams from data.

```python
class Encoder(ABC):
    def __init__(self, environment=None):
        self.is_running = False    # Currently transmitting
        self.repeat = 10           # Repetitions remaining
        self.front = 0             # Current position in upload buffer
        self.upload = []            # List[LevelDuration]
        self.generic = SubGhzBlockGeneric()

    def deserialize(self, data: Dict[str, Any]) -> bool:
        """Load parameters and generate upload buffer"""

    def stop(self) -> None:
        """Stop transmission"""

    def yield_(self) -> LevelDuration:
        """Get next level/duration to transmit"""
```

### Receiver Class

Manages parallel decoding across all protocols:

```python
class Receiver:
    def __init__(self, protocol_registry: List[Protocol], environment=None):
        self.slots = []          # List of (Protocol, Decoder) tuples
        self.filter = SubGhzProtocolFlag(0xFFFFFFFF)  # Protocol filter
        self.callback = None     # Called on successful decode
        self.context = None

    def feed(self, level: bool, duration: int):
        """Feed signal to ALL decoders (parallel decoding)"""

    def reset(self):
        """Reset all decoders"""

    def set_filter(self, flag: SubGhzProtocolFlag):
        """Filter which protocols attempt to decode"""

    def set_rx_callback(self, callback, context=None):
        """Set callback for successful decode: callback(receiver, decoder, context)"""
```

### Transmitter Class

Manages encoding and transmission of a single protocol:

```python
class Transmitter:
    def __init__(self, protocol_registry: Dict[str, Protocol], environment=None):
        self.protocol = None           # Selected protocol
        self.protocol_instance = None  # Encoder instance
        self.protocol_registry = protocol_registry

    def load(self, protocol_name: str, data: Dict[str, Any]) -> bool:
        """Load protocol and configure with data dict:
        - key: The data to encode
        - bit: Number of bits
        - repeat: Repetitions (default 10)
        - te: Timing element (optional, protocol default)
        - guard_time: Guard time multiplier (optional)
        """

    def stop(self) -> bool:
        """Stop transmission"""

    def yield_(self) -> LevelDuration:
        """Get next level/duration; returns LevelDuration(level=False, duration=0) when done"""
```

## Implemented Protocols

### Princeton

- **Type**: Static (fixed code)
- **Timing**: TE_SHORT=390µs, TE_LONG=1170µs, TE_DELTA=300µs
- **Encoding**: Pulse Distance (short+long=0, long+short=1)
- **Format**: [Preamble ~14ms] [24 bits data] [Stop bit] [Guard time]
- **Frequencies**: 315MHz, 433MHz, 868MHz
- **Modulation**: AM/ASK

```python
tx.load('Princeton', {
    'key': 0x123456,     # 24-bit key
    'bit': 24,           # Bit count
    'repeat': 10,         # Repetitions
    'te': 390,           # Timing element (optional)
    'guard_time': 30     # Guard time multiplier (optional)
})
```

### GateTX

- **Type**: Static (fixed code)
- **Timing**: TE_SHORT=350µs, TE_LONG=700µs, TE_DELTA=100µs
- **Encoding**: Manchester-style (short+long=0, long+short=1)
- **Format**: [Header 17ms] [Start bit] [24 bits data]
- **Frequencies**: 433MHz
- **Modulation**: AM/ASK

```python
tx.load('GateTX', {
    'key': 0x123456,     # 24-bit key
    'bit': 24,           # Bit count
    'repeat': 10         # Repetitions
})
```

## Block Utilities

The `blocks` module provides mathematical utilities:

```python
from rflib.protocols.blocks.math import (
    bit_read, bit_set, bit_clear, bit_write,
    duration_diff, reverse_key, get_parity, parity8,
    crc4, crc7, crc8, crc8le, crc16, crc16lsb,
    lfsr_digest8, lfsr_digest8_reflect, lfsr_digest16,
    add_bytes, xor_bytes, add_bit, get_hash_data,
)
```

## Adding a New Protocol

To add a new static protocol (e.g., "MyProtocol"):

### 1. Create the protocol file: `my_protocol.py`

```python
from typing import Dict, Any
from enum import IntEnum

from .base import (
    Protocol, Decoder, Encoder, LevelDuration,
    SubGhzProtocolType, SubGhzProtocolFlag, SubGhzBlockConst
)
from .blocks.math import duration_diff, bit_read, add_bit

SUBGHZ_PROTOCOL_MY_PROTOCOL_NAME = "MyProtocol"

MY_PROTOCOL_CONST = SubGhzBlockConst(
    te_short=350,        # Short pulse (µs)
    te_long=700,         # Long pulse (µs)
    te_delta=100,        # Tolerance (µs)
    min_count_bit_for_found=24,  # Minimum valid bits
)

class MyProtocolDecoderStep(IntEnum):
    RESET = 0
    SAVE_DURATION = 1
    CHECK_DURATION = 2

class MyProtocolDecoder(Decoder):
    def __init__(self, environment=None):
        super().__init__(environment)
        self.generic.protocol_name = SUBGHZ_PROTOCOL_MY_PROTOCOL_NAME

    def reset(self):
        self.parser_step = MyProtocolDecoderStep.RESET
        self.decode_data = 0
        self.decode_count_bit = 0

    def feed(self, level: bool, duration: int):
        # Implement state machine to decode signal
        if self.parser_step == MyProtocolDecoderStep.RESET:
            # Look for preamble
            pass
        elif self.parser_step == MyProtocolDecoderStep.SAVE_DURATION:
            # Save high duration
            pass
        elif self.parser_step == MyProtocolDecoderStep.CHECK_DURATION:
            # Check low duration, decode bits
            pass

    def get_string(self) -> str:
        return f"{self.generic.protocol_name} {self.generic.data_count_bit}bit"

class MyProtocolEncoder(Encoder):
    def __init__(self, environment=None):
        super().__init__(environment)
        self.generic.protocol_name = SUBGHZ_PROTOCOL_MY_PROTOCOL_NAME

    def deserialize(self, data: Dict[str, Any]) -> bool:
        self.generic.data = data.get('key', 0)
        self.generic.data_count_bit = data.get('bit', 24)
        self.repeat = data.get('repeat', 10)
        return self._generate_upload()

    def _generate_upload(self) -> bool:
        self.upload = []
        # Generate LevelDuration list from self.generic.data
        # ...
        self.is_running = True
        return True

    def stop(self):
        self.is_running = False

class MyProtocolProtocol(Protocol):
    @property
    def name(self) -> str:
        return SUBGHZ_PROTOCOL_MY_PROTOCOL_NAME

    @property
    def type(self) -> SubGhzProtocolType:
        return SubGhzProtocolType.STATIC

    @property
    def flag(self) -> SubGhzProtocolFlag:
        return (SubGhzProtocolFlag.FREQ_433 |
                SubGhzProtocolFlag.MOD_AM |
                SubGhzProtocolFlag.DECODABLE |
                SubGhzProtocolFlag.SEND)

    @property
    def decoder_cls(self):
        return MyProtocolDecoder

    @property
    def encoder_cls(self):
        return MyProtocolEncoder

subghz_protocol_my_protocol = MyProtocolProtocol()
```

### 2. Update the registry: `registry.py`

```python
from .my_protocol import subghz_protocol_my_protocol, MyProtocolProtocol

PROTOCOL_REGISTRY = {
    # ... existing entries ...
    subghz_protocol_my_protocol.name: subghz_protocol_my_protocol,
}

PROTOCOL_LIST = [
    # ... existing entries ...
    subghz_protocol_my_protocol,
]
```

### 3. Update package exports: `__init__.py`

```python
from .my_protocol import MyProtocolDecoder, MyProtocolEncoder, MyProtocolProtocol
```

## Decoder State Machine Pattern

Static protocol decoders typically use a state machine like:

```
RESET -> SAVE_DURATION -> CHECK_DURATION
   ^          |                |
   |          |                |
   +----------+----------------+
```

1. **RESET**: Wait for preamble pattern (specific low duration)
2. **SAVE_DURATION**: Save high duration of first part of bit
3. **CHECK_DURATION**: Check low duration to decode bit, look for end-of-message

When end-of-message is detected:
- Check if we have minimum required bits
- Check if this matches the last message (for deduplication)
- If valid, trigger callback
- Reset for next message

## Integration with rfcat Hardware

The protocol system works with level/duration pairs. To integrate with actual rfcat hardware:

```python
from rflib.protocols import Receiver, Transmitter, PROTOCOL_LIST, PROTOCOL_REGISTRY

# RECEIVE MODE: Configure rfcat for OOK/ASK reception
d.setMdmModulation(MOD_ASK_OOK)
d.setFreq(433920000)

rx = Receiver(PROTOCOL_LIST)
rx.set_rx_callback(on_decoded)

# In your receive loop:
while True:
    data = d.RFrecv()[0]  # Get raw bytes
    # Convert bytes to (level, duration) pairs based on your signal format
    # Then feed to rx.feed(level, duration)

# TRANSMIT MODE: Configure rfcat for OOK/ASK transmission
tx = Transmitter(PROTOCOL_REGISTRY)
tx.load('Princeton', {'key': 0xDEADBEEF, 'bit': 24, 'repeat': 10})

d.setMdmModulation(MOD_ASK_OOK)
d.setFreq(433920000)

# In your transmit loop:
while True:
    ld = tx.yield_()
    if ld.duration == 0:
        break
    # Convert LevelDuration to your transmission format
    # d.RFxmit(...) or use low-level access
```

## File Structure

```
rflib/protocols/
├── __init__.py           # Package exports
├── base.py               # Base classes (Protocol, Decoder, Encoder, Receiver, Transmitter)
├── registry.py           # Protocol registry
├── princeton.py          # Princeton protocol
├── gate_tx.py            # GateTX protocol
└── blocks/
    ├── __init__.py       # Block utilities exports
    └── math.py           # Math/bit operations
```

## Reference

- Flipper Zero Sub-GHz implementation: `/home/dev/src/flipperzero-firmware/lib/subghz/`
- Documentation: `/home/dev/src/rfcat/docs/flipper-subghz.md`