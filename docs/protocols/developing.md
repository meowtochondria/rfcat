# Protocol Development Guide

This guide walks through implementing a new static RF protocol for the rfcat protocol system.

## Prerequisites

1. Understand the Flipper Zero implementation for your target protocol:
   ```
   /home/dev/src/flipperzero-firmware/lib/subghz/protocols/<protocol_name>.c
   /home/dev/src/flipperzero-firmware/lib/subghz/protocols/<protocol_name>.h
   ```

2. Read the protocol documentation:
   ```
   /home/dev/src/rfcat/docs/flipper-subghz.md
   ```

3. Review existing implementations:
   ```
   /home/dev/src/rfcat/rflib/protocols/princeton.py
   /home/dev/src/rfcat/rflib/protocols/gate_tx.py
   ```

## Implementation Steps

### 1. Analyze the Flipper C Implementation

For a new protocol, examine:

- **Timing constants** (`SubGhzBlockConst`):
  ```c
  static const SubGhzBlockConst subghz_protocol_xxx_const = {
      .te_short = 350,
      .te_long = 700,
      .te_delta = 100,
      .min_count_bit_for_found = 24,
  };
  ```

- **Decoder state machine** (the `feed` function):
  ```c
  typedef enum {
      XxxDecoderStepReset = 0,
      XxxDecoderStepSaveDuration,
      XxxDecoderStepCheckDuration,
  } XxxDecoderStep;

  void subghz_protocol_decoder_xxx_feed(void* context, bool level, uint32_t duration) {
      // State machine implementation
  }
  ```

- **Encoder upload generation** (the `get_upload` function):
  ```c
  static bool subghz_protocol_encoder_xxx_get_upload(SubGhzProtocolEncoderXxx* instance) {
      // Generate LevelDuration list from instance->generic.data
  }
  ```

### 2. Create Protocol File

Create `rflib/protocols/<protocol_name>.py`:

```python
from typing import Dict, Any
from enum import IntEnum

from .base import (
    Protocol, Decoder, Encoder, LevelDuration,
    SubGhzProtocolType, SubGhzProtocolFlag, SubGhzBlockConst
)
from .blocks.math import duration_diff, bit_read, add_bit

SUBGHZ_PROTOCOL_<PROTOCOL>_NAME = "<ProtocolName>"

# Timing constants from Flipper implementation
<PROTOCOL>_CONST = SubGhzBlockConst(
    te_short=350,
    te_long=700,
    te_delta=100,
    min_count_bit_for_found=24
)

# Decoder state machine states
class <Protocol>DecoderStep(IntEnum):
    RESET = 0
    SAVE_DURATION = 1
    CHECK_DURATION = 2
```

### 3. Implement Decoder Class

```python
class <Protocol>Decoder(Decoder):
    def __init__(self, environment=None):
        super().__init__(environment)
        self.generic.protocol_name = SUBGHZ_PROTOCOL_<PROTOCOL>_NAME

    def reset(self):
        """Reset state machine - called at start and after errors"""
        self.parser_step = <Protocol>DecoderStep.RESET
        self.decode_data = 0
        self.decode_count_bit = 0

    def feed(self, level: bool, duration: int):
        """Process signal - this is the core decode logic"""
        if self.parser_step == <Protocol>DecoderStep.RESET:
            # Look for preamble
            if not level and duration_diff(duration, <PROTOCOL>_CONST.te_short * <preamble_count>) < <PROTOCOL>_CONST.te_delta * <preamble_count>:
                self.parser_step = <Protocol>DecoderStep.SAVE_DURATION
                self.decode_data = 0
                self.decode_count_bit = 0

        elif self.parser_step == <Protocol>DecoderStep.SAVE_DURATION:
            if level:
                self.te_last = duration
                self.parser_step = <Protocol>DecoderStep.CHECK_DURATION

        elif self.parser_step == <Protocol>DecoderStep.CHECK_DURATION:
            if not level:
                # Check for end-of-message
                if duration >= <PROTOCOL>_CONST.te_long * 2:
                    # Process end of message
                    if self.decode_count_bit == <PROTOCOL>_CONST.min_count_bit_for_found:
                        self.generic.data = self.decode_data
                        self.generic.data_count_bit = self.decode_count_bit
                        if self.callback:
                            self.callback(self, self.context)
                    self.decode_data = 0
                    self.decode_count_bit = 0
                    self.parser_step = <PROTOCOL>DecoderStep.SAVE_DURATION
                    return

                # Decode bit based on timing
                if (duration_diff(self.te_last, <PROTOCOL>_CONST.te_short) < <PROTOCOL>_CONST.te_delta and
                    duration_diff(duration, <PROTOCOL>_CONST.te_long) < <PROTOCOL>_CONST.te_delta * 3):
                    add_bit(self, 0)
                    self.parser_step = <Protocol>DecoderStep.SAVE_DURATION
                elif (duration_diff(self.te_last, <PROTOCOL>_CONST.te_long) < <PROTOCOL>_CONST.te_delta * 3 and
                      duration_diff(duration, <PROTOCOL>_CONST.te_short) < <PROTOCOL>_CONST.te_delta):
                    add_bit(self, 1)
                    self.parser_step = <Protocol>DecoderStep.SAVE_DURATION
                else:
                    self.parser_step = <Protocol>DecoderStep.RESET
            else:
                self.parser_step = <Protocol>DecoderStep.RESET

    def get_string(self) -> str:
        """Return human-readable decoded data"""
        return f"{self.generic.protocol_name} {self.generic.data_count_bit}bit Key:0x{self.generic.data:X}"
```

### 4. Implement Encoder Class

```python
class <Protocol>Encoder(Encoder):
    def __init__(self, environment=None):
        super().__init__(environment)
        self.generic.protocol_name = SUBGHZ_PROTOCOL_<PROTOCOL>_NAME

    def deserialize(self, data: Dict[str, Any]) -> bool:
        """Load configuration and generate upload buffer"""
        self.generic.data = data.get('key', 0)
        self.generic.data_count_bit = data.get('bit', 24)
        self.repeat = data.get('repeat', 10)
        return self._generate_upload()

    def _generate_upload(self) -> bool:
        """Generate LevelDuration list from generic.data"""
        self.upload = []

        # Optional: Add preamble/header
        # self.upload.append(LevelDuration(False, <header_duration>))

        # Encode each bit
        for i in range(self.generic.data_count_bit - 1, -1, -1):
            bit = bit_read(self.generic.data, i)
            if bit:
                # Encode bit 1
                self.upload.append(LevelDuration(True, <te_long>))
                self.upload.append(LevelDuration(False, <te_short>))
            else:
                # Encode bit 0
                self.upload.append(LevelDuration(True, <te_short>))
                self.upload.append(LevelDuration(False, <te_long>))

        self.is_running = True
        return True

    def stop(self):
        self.is_running = False
```

### 5. Implement Protocol Class

```python
class <Protocol>Protocol(Protocol):
    @property
    def name(self) -> str:
        return SUBGHZ_PROTOCOL_<PROTOCOL>_NAME

    @property
    def type(self) -> SubGhzProtocolType:
        return SubGhzProtocolType.STATIC

    @property
    def flag(self) -> SubGhzProtocolFlag:
        return (SubGhzProtocolFlag.FREQ_433 |  # Add appropriate frequencies
                SubGhzProtocolFlag.MOD_AM |    # Add appropriate modulation
                SubGhzProtocolFlag.DECODABLE |
                SubGhzProtocolFlag.SEND)

    @property
    def decoder_cls(self):
        return <Protocol>Decoder

    @property
    def encoder_cls(self):
        return <Protocol>Encoder

# Global protocol instance
subghz_protocol_<protocol> = <Protocol>Protocol()
```

### 6. Update Registry

Edit `rflib/protocols/registry.py`:

```python
from .<protocol> import subghz_protocol_<protocol>, <Protocol>Protocol

PROTOCOL_REGISTRY = {
    'Princeton': subghz_protocol_princeton,
    'GateTX': subghz_protocol_gate_tx,
    'ProtocolName': subghz_protocol_<protocol>,  # Add new entry
}

PROTOCOL_LIST = [
    subghz_protocol_princeton,
    subghz_protocol_gate_tx,
    subghz_protocol_<protocol>,  # Add new entry
]
```

### 7. Update Package Exports

Edit `rflib/protocols/__init__.py`:

```python
from .<protocol> import (
    <Protocol>Decoder,
    <Protocol>Encoder,
    <Protocol>Protocol,
)

# Add to __all__ list
__all__ = [
    # ... existing exports ...
    '<Protocol>Decoder',
    '<Protocol>Encoder',
    '<Protocol>Protocol',
]
```

## Testing Your Implementation

### Unit Test Template

```python
def test_<protocol>_encoder():
    """Test encoder produces correct output"""
    from rflib.protocols import <Protocol>Encoder

    encoder = <Protocol>Encoder()
    result = encoder.deserialize({'key': 0x123456, 'bit': 24, 'repeat': 1})

    assert result is True
    assert encoder.is_running is True
    assert len(encoder.upload) > 0
    # Add more specific assertions

def test_<protocol>_decoder():
    """Test decoder processes signal correctly"""
    from rflib.protocols import <Protocol>Decoder

    decoder = <Protocol>Decoder()
    decoder.callback = lambda d, ctx: set_decoded(d.decode_data)

    # Feed test signal
    # ...

    # Check decoded data
    assert decoder.decode_data == expected_value

def test_<protocol>_round_trip():
    """Test encoder output can be decoded"""
    from rflib.protocols import <Protocol>Encoder, <Protocol>Decoder

    test_key = 0x123456

    # Encode
    encoder = <Protocol>Encoder()
    encoder.deserialize({'key': test_key, 'bit': 24, 'repeat': 1})

    # Decode
    decoder = <Protocol>Decoder()
    decoder.callback = lambda d, ctx: None

    for ld in encoder.upload:
        decoder.feed(ld.level, ld.duration)

    # For protocols requiring duplicate messages
    for ld in encoder.upload:
        decoder.feed(ld.level, ld.duration)

    assert decoder.decode_data == test_key
```

### Debugging Tips

1. **Print state transitions**:
   ```python
   def feed(self, level: bool, duration: int):
       print(f"  State {self.parser_step}: level={level}, duration={duration}")
       # ... rest of implementation
   ```

2. **Verify timing constants**:
   ```python
   print(f"te_short={<PROTOCOL>_CONST.te_short}, te_long={<PROTOCOL>_CONST.te_long}")
   ```

3. **Check encoder output**:
   ```python
   for i, ld in enumerate(encoder.upload):
       print(f"{i}: {'HIGH' if ld.level else 'LOW'} {ld.duration}µs")
   ```

## Common Patterns

### Manchester Encoding

For protocols using Manchester encoding (like Nice FLO):

```python
# Decoder: Check if short+long or long+short
if (duration_diff(self.te_last, te_short) < te_delta and
    duration_diff(duration, te_long) < te_delta * 3):
    add_bit(self, 0)
elif (duration_diff(self.te_last, te_long) < te_delta * 3 and
      duration_diff(duration, te_short) < te_delta):
    add_bit(self, 1)

# Encoder: Encode bit 0 as short-long, bit 1 as long-short
if bit:
    upload.append(LevelDuration(True, te_long))
    upload.append(LevelDuration(False, te_short))
else:
    upload.append(LevelDuration(True, te_short))
    upload.append(LevelDuration(False, te_long))
```

### Pulse Width Encoding

For protocols using pulse width (bit determined by high duration):

```python
# Decoder: Check if high duration is short or long
if level:
    if duration_diff(duration, te_short) < te_delta:
        # Bit 0
    elif duration_diff(duration, te_long) < te_delta:
        # Bit 1
```

### Preamble Detection

```python
# Decoder: Reset state waits for specific pattern
if self.parser_step == RESET:
    # Princeton-style: single long low period
    if not level and duration_diff(duration, te_short * 36) < te_delta * 36:
        self.parser_step = SAVE_DURATION

    # GateTX-style: specific preamble followed by start bit
    if not level and duration_diff(duration, te_short * 47) < te_delta * 47:
        self.parser_step = FOUND_START_BIT
```

## Checklist

Before considering implementation complete:

- [ ] Decoder processes correct number of bits
- [ ] Decoder triggers callback on valid message
- [ ] Decoder handles duplicate messages (if required)
- [ ] Decoder resets properly after errors
- [ ] Encoder produces correct LevelDuration count
- [ ] Encoder output can be decoded back to original data
- [ ] Protocol registered and importable
- [ ] Documentation updated
- [ ] Test cases pass