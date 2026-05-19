# Protocol Usage Examples

## Basic Encoding (Sending)

### Encode and Transmit Princeton Signal

```python
from rflib.protocols import (
    PROTOCOL_REGISTRY,
    Transmitter,
)

# Create transmitter
tx = Transmitter(PROTOCOL_REGISTRY)

# Load Princeton protocol with data
tx.load('Princeton', {
    'key': 0xDEADBEEF,
    'bit': 24,
    'repeat': 10,
})

# Transmit by yielding LevelDuration pairs
print("Transmitting Princeton signal...")
while True:
    ld = tx.yield_()
    if ld.duration == 0:
        break
    # Here you would send ld.level and ld.duration via your RF hardware
    print(f"  level={ld.level}, duration={ld.duration}us")
```

### Encode and Transmit GateTX Signal

```python
from rflib.protocols import (
    PROTOCOL_REGISTRY,
    Transmitter,
)

tx = Transmitter(PROTOCOL_REGISTRY)
tx.load('GateTX', {
    'key': 0x123456,
    'bit': 24,
    'repeat': 5,
})

while True:
    ld = tx.yield_()
    if ld.duration == 0:
        break
    send_rf_signal(ld.level, ld.duration)
```

### Using Custom Timing

```python
tx = Transmitter(PROTOCOL_REGISTRY)
tx.load('Princeton', {
    'key': 0xAABBCC,
    'bit': 24,
    'repeat': 10,
    'te': 400,           # Custom timing element (default 390)
    'guard_time': 40,     # Custom guard time multiplier (default 30)
})
```

---

## Basic Decoding (Receiving)

### Simple Decode Example

```python
from rflib.protocols import (
    PROTOCOL_LIST,
    Receiver,
)

# Create receiver with all protocols
rx = Receiver(PROTOCOL_LIST)

# Set callback for successful decode
def on_protocol_decoded(receiver, decoder, context):
    print(f"Decoded {decoder.generic.protocol_name}!")
    print(decoder.get_string())
    # decoder.generic.data contains the decoded key
    # decoder.generic.data_count_bit contains bit count

rx.set_rx_callback(on_protocol_decoded)

# Simulate receiving RF signal (in practice, this comes from hardware)
# Example: Princeton preamble (low ~14ms) followed by bits
rx.feed(False, 14040)  # Preamble low
rx.feed(True, 390)    # First bit start
rx.feed(False, 1170)  # First bit end (long = 1)
# ... continue feeding bits ...
```

### Decode with Protocol Filtering

```python
from rflib.protocols import (
    PROTOCOL_LIST,
    Receiver,
    SubGhzProtocolFlag,
)

rx = Receiver(PROTOCOL_LIST)

# Only decode 433MHz AM protocols
rx.set_filter(SubGhzProtocolFlag.FREQ_433 | SubGhzProtocolFlag.MOD_AM)

rx.set_rx_callback(on_protocol_decoded)
```

### Find Specific Decoder

```python
rx = Receiver(PROTOCOL_LIST)

# Find Princeton decoder
princeton_decoder = rx.search_decoder_by_name('Princeton')
if princeton_decoder:
    print(f"Found: {princeton_decoder.generic.protocol_name}")
```

---

## Full RF Hardware Integration

### Send Mode with rfcat Dongle

```python
from rflib import RfCat
from rflib.protocols import PROTOCOL_REGISTRY, Transmitter

# Initialize rfcat dongle
d = RfCat()
d.setFreq(433920000)  # 433.92 MHz
d.setMdmModulation(MOD_ASK_OOK)

# Setup transmitter
tx = Transmitter(PROTOCOL_REGISTRY)
tx.load('Princeton', {
    'key': 0xDEADBEEF,
    'bit': 24,
    'repeat': 10,
})

# Transmit
print("Transmitting...")
while True:
    ld = tx.yield_()
    if ld.duration == 0:
        break

    # For OOK, we modulate the carrier on/off
    # The duration tells us how long to hold each level
    # This is a simplified example - actual implementation
    # would need proper timing control
    if ld.level:
        d.RFxmit(b'\xFF' * (ld.duration // 8 + 1))
    else:
        time.sleep(ld.duration / 1e6)
```

### Receive Mode with rfcat Dongle

```python
from rflib import RfCat
from rflib.protocols import PROTOCOL_LIST, Receiver

# Initialize rfcat dongle
d = RfCat()
d.setFreq(433920000)
d.setMdmModulation(MOD_ASK_OOK)

# Setup receiver
rx = Receiver(PROTOCOL_LIST)

def on_decoded(receiver, decoder, context):
    print(f"Decoded: {decoder.get_string()}")
    print(f"Key: 0x{decoder.generic.data:08X}")

rx.set_rx_callback(on_decoded)

# Receive loop
# Note: This would need proper signal processing to convert
# packet data to (level, duration) pairs
print("Receiving...")
while True:
    try:
        data, timestamp = d.RFrecv(timeout=1000)
        # Convert data to level/duration pairs
        # This is protocol/hardware specific
        for byte in data:
            for bit in range(8):
                level = bool((byte >> bit) & 1)
                # These durations would need calibration
                rx.feed(level, 390)
    except ChipconUsbTimeoutException:
        pass
```

---

## Working with Encoded Data

### Get Protocol Information

```python
from rflib.protocols import (
    PROTOCOL_REGISTRY,
    get_protocol,
    PrincetonProtocol,
)

# Get protocol by name
protocol = get_protocol('Princeton')
print(f"Name: {protocol.name}")
print(f"Type: {protocol.type.name}")
print(f"Flags: {protocol.flag}")

# Create instance to access properties
instance = PrincetonProtocol()
print(f"Can send: {bool(protocol.flag & SubGhzProtocolFlag.SEND)}")
print(f"Can decode: {bool(protocol.flag & SubGhzProtocolFlag.DECODABLE)}")
```

### Inspect Encoder Output

```python
from rflib.protocols import PrincetonEncoder

encoder = PrincetonEncoder()
encoder.deserialize({
    'key': 0x123456,
    'bit': 24,
    'repeat': 1,
})

print(f"Upload size: {len(encoder.upload)} LevelDurations")
print(f"Will repeat: {encoder.repeat} times")

# Show first few signals
print("\nFirst 10 signals:")
for i, ld in enumerate(encoder.upload[:10]):
    print(f"  {i}: {'HIGH' if ld.level else 'LOW'} for {ld.duration}µs")
```

### Manually Feed Signals to Decoder

```python
from rflib.protocols import PrincetonDecoder, PrincetonEncoder, PROTOCOL_REGISTRY

# Create encoder and generate signal
encoder = PrincetonEncoder()
encoder.deserialize({'key': 0x123456, 'bit': 24, 'repeat': 1})

# Create decoder
decoder = PrincetonDecoder()
decoder.callback = lambda d, ctx: print(f"Decoded: 0x{d.decode_data:08X}")

# Feed encoder output to decoder
print("Feeding encoded signal to decoder...")
for ld in encoder.upload:
    decoder.feed(ld.level, ld.duration)

# Feed again (Princeton requires two matching messages)
for ld in encoder.upload:
    decoder.feed(ld.level, ld.duration)
```

---

## Multiple Protocol Operations

### List All Protocols

```python
from rflib.protocols import list_protocols

for name in list_protocols():
    print(f"  {name}")
```

### Create Selective Receiver

```python
from rflib.protocols import (
    PrincetonProtocol,
    GateTXProtocol,
    Receiver,
)

# Only decode specific protocols
protocols = [PrincetonProtocol(), GateTXProtocol()]
rx = Receiver(protocols)

rx.set_rx_callback(on_decoded)
```

### Switch Transmitter Between Protocols

```python
from rflib.protocols import PROTOCOL_REGISTRY, Transmitter

tx = Transmitter(PROTOCOL_REGISTRY)

# Send Princeton
tx.load('Princeton', {'key': 0x111111, 'bit': 24})
# ... transmit Princeton ...

# Switch to GateTX
tx.load('GateTX', {'key': 0x222222, 'bit': 24})
# ... transmit GateTX ...
```

---

## Error Handling

```python
from rflib.protocols import PROTOCOL_REGISTRY, Transmitter

tx = Transmitter(PROTOCOL_REGISTRY)

# Invalid protocol
success = tx.load('InvalidProtocol', {'key': 0x123})
print(f"Load success: {success}")  # False

# Valid protocol, missing required field
tx.load('Princeton', {})  # Will use defaults
print(f"Key default: 0x{tx.protocol_instance.generic.data:08X}")  # 0x0
```

---

## Debugging Tips

### Print Decoder State

```python
decoder = PrincetonDecoder()
print(f"Initial state: step={decoder.parser_step}, "
      f"data={decoder.decode_data}, "
      f"bits={decoder.decode_count_bit}")
```

### Check Encoder Configuration

```python
encoder = PrincetonEncoder()
encoder.deserialize({'key': 0xDEAD, 'bit': 16, 'repeat': 5})
print(f"is_running: {encoder.is_running}")
print(f"repeat: {encoder.repeat}")
print(f"front: {encoder.front}")
print(f"upload size: {len(encoder.upload)}")
```

### Inspect Protocol Flags

```python
from rflib.protocols import PrincetonProtocol, SubGhzProtocolFlag

p = PrincetonProtocol()
print(f"Flag value: {p.flag}")
print(f"Is 433MHz: {bool(p.flag & SubGhzProtocolFlag.FREQ_433)}")
print(f"Can send: {bool(p.flag & SubGhzProtocolFlag.SEND)}")
print(f"Can decode: {bool(p.flag & SubGhzProtocolFlag.DECODABLE)}")
```
