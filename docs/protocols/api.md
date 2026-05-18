# Protocol API Reference

## Base Classes

### LevelDuration

```python
@dataclass
class LevelDuration:
    level: bool      # True = high, False = low
    duration: int    # Duration in microseconds

    @staticmethod
    def make(level: bool, duration: int) -> 'LevelDuration':
        """Create a LevelDuration"""

    @staticmethod
    def reset() -> 'LevelDuration':
        """Create an end-of-transmission signal (level=False, duration=0)"""
```

### SubGhzBlockConst

```python
@dataclass
class SubGhzBlockConst:
    te_short: int              # Short pulse duration (µs)
    te_long: int               # Long pulse duration (µs)
    te_delta: int              # Tolerance for matching (µs)
    min_count_bit_for_found: int  # Minimum bits for valid decode
```

### SubGhzBlockGeneric

```python
@dataclass
class SubGhzBlockGeneric:
    protocol_name: str = ""    # Protocol name
    data: int = 0              # Decoded/encoded data
    serial: int = 0            # Serial/remote ID
    data_count_bit: int = 0    # Number of data bits
    btn: int = 0               # Button code
    cnt: int = 0               # Counter (for rolling codes)
```

### SubGhzProtocolType

```python
class SubGhzProtocolType(Enum):
    UNKNOWN = 0
    STATIC = 1        # Fixed code protocols
    DYNAMIC = 2       # Rolling code protocols
    RAW = 3           # Raw waveform capture
    WEATHER_STATION = 4
    CUSTOM = 5
```

### SubGhzProtocolFlag

```python
class SubGhzProtocolFlag(IntFlag):
    RAW = 1 << 0
    DECODABLE = 1 << 1
    FREQ_315 = 1 << 2    # 315 MHz band
    FREQ_433 = 1 << 3    # 433 MHz band
    FREQ_868 = 1 << 4    # 868 MHz band
    MOD_AM = 1 << 5      # AM modulation
    MOD_FM = 1 << 6      # FM modulation
    SAVE = 1 << 7        # Can save to file
    LOAD = 1 << 8        # Can load from file
    SEND = 1 << 9         # Can transmit
    BIN_RAW = 1 << 10    # Binary RAW format
```

---

## Protocol (ABC)

Base class for all protocols.

```python
class Protocol(ABC):

    @property
    @abstractmethod
    def name(self) -> str:
        """Protocol name string (e.g., 'Princeton')"""

    @property
    @abstractmethod
    def type(self) -> SubGhzProtocolType:
        """Protocol type (STATIC, DYNAMIC, RAW)"""

    @property
    @abstractmethod
    def flag(self) -> SubGhzProtocolFlag:
        """Protocol flags (frequencies, modulation, capabilities)"""

    @property
    @abstractmethod
    def decoder_cls(self):
        """Decoder class for this protocol"""

    @property
    @abstractmethod
    def encoder_cls(self):
        """Encoder class for this protocol"""
```

---

## Decoder (ABC)

Base class for protocol decoders. Handles converting (level, duration) streams to protocol data.

```python
class Decoder(ABC):

    def __init__(self, environment: Optional[Any] = None):
        # Internal state
        self.parser_step: int = 0       # Current state machine state
        self.te_last: int = 0            # Last recorded duration
        self.decode_data: int = 0         # Accumulated decoded bits
        self.decode_count_bit: int = 0    # Number of bits accumulated
        self.callback: Optional[Callable] = None  # Success callback
        self.context: Any = None          # Callback context
        self.generic: SubGhzBlockGeneric  # Generic decoded data

    @abstractmethod
    def feed(self, level: bool, duration: int) -> None:
        """Process a level/duration pair from the signal stream"""

    @abstractmethod
    def reset(self) -> None:
        """Reset decoder state machine to initial state"""

    def get_hash_data(self) -> int:
        """Get hash of last decoded data (for deduplication)"""
        # Default implementation provided

    @abstractmethod
    def get_string(self) -> str:
        """Get human-readable representation of decoded data"""
```

### Decoder Callback

When a decoder successfully decodes a message, it calls:

```python
if self.callback:
    self.callback(self, self.context)
```

The callback receives `(decoder_instance, context)`.

---

## Encoder (ABC)

Base class for protocol encoders. Handles converting protocol data to (level, duration) streams.

```python
class Encoder(ABC):

    def __init__(self, environment: Optional[Any] = None):
        # Internal state
        self.is_running: bool = False     # Currently transmitting
        self.repeat: int = 10             # Repetitions remaining
        self.front: int = 0               # Current position in upload buffer
        self.upload: List[LevelDuration]   # Pre-generated signal buffer
        self.generic: SubGhzBlockGeneric  # Generic data

    @abstractmethod
    def deserialize(self, data: Dict[str, Any]) -> bool:
        """Load parameters and generate upload buffer.

        Expected data dict keys:
        - key: int          # Data to encode
        - bit: int          # Number of bits
        - repeat: int       # Repetitions (optional, default 10)
        - te: int           # Timing element (optional, protocol default)
        - guard_time: int   # Guard time multiplier (optional)
        """

    @abstractmethod
    def stop(self) -> None:
        """Stop transmission"""

    def yield_(self) -> LevelDuration:
        """Get next level/duration for transmission.

        Returns LevelDuration(level=False, duration=0) when:
        - All repetitions exhausted
        - Transmission stopped
        """
```

### Yield Pattern

```python
def yield_(self) -> LevelDuration:
    if self.repeat == 0 or not self.is_running:
        self.is_running = False
        return LevelDuration.reset()

    result = self.upload[self.front]
    self.front += 1
    if self.front >= len(self.upload):
        self.repeat -= 1
        self.front = 0
    return result
```

---

## Receiver

Manages parallel decoding across multiple protocols.

```python
class Receiver:

    def __init__(self,
                 protocol_registry: List[Protocol],
                 environment: Optional[Any] = None):
        """Create receiver with list of protocols to decode.

        Creates a decoder instance for each protocol.
        """
        self.slots: List[tuple] = []   # List of (Protocol, Decoder)
        self.filter: SubGhzProtocolFlag  # Protocol filter (default: all)
        self.callback: Optional[Callable] = None
        self.context: Any = None
        self.environment = environment

    def feed(self, level: bool, duration: int) -> None:
        """Feed level/duration to ALL protocol decoders.

        All decoders receive every signal - parallel decoding.
        First successful decoder triggers callback.
        """

    def reset(self) -> None:
        """Reset all protocol decoders"""

    def set_filter(self, flag: SubGhzProtocolFlag) -> None:
        """Set protocol filter to limit which protocols attempt decode.

        Example:
            receiver.set_filter(SubGhzProtocolFlag.FREQ_433 | SubGhzProtocolFlag.MOD_AM)
        """

    def set_rx_callback(self, callback: Callable, context=None) -> None:
        """Set callback for successful decode.

        Callback signature: callback(receiver, decoder, context)
        - receiver: The Receiver instance
        - decoder: The Decoder that successfully decoded
        - context: User-provided context
        """

    def search_decoder_by_name(self, name: str) -> Optional[Decoder]:
        """Find decoder instance by protocol name"""
```

---

## Transmitter

Manages encoding and transmission for a single protocol.

```python
class Transmitter:

    def __init__(self,
                 protocol_registry: Dict[str, Protocol],
                 environment: Optional[Any] = None):
        """Create transmitter with protocol registry"""
        self.protocol: Optional[Protocol] = None
        self.protocol_instance: Optional[Encoder] = None
        self.protocol_registry = protocol_registry
        self.environment = environment

    def load(self, protocol_name: str, data: Dict[str, Any]) -> bool:
        """Load protocol and configure for transmission.

        Args:
            protocol_name: Name of protocol (e.g., 'Princeton')
            data: Configuration dict with keys:
                - key: int          # Data to encode
                - bit: int          # Number of bits
                - repeat: int       # Repetitions
                - te: int           # Timing element (optional)
                - guard_time: int   # Guard time (optional)

        Returns:
            True if successful, False if protocol not found
        """

    def stop(self) -> bool:
        """Stop transmission.

        Returns True if stopped, False if no active transmission.
        """

    def yield_(self) -> LevelDuration:
        """Get next level/duration for transmission.

        Returns LevelDuration(level=False, duration=0) when done.
        """
```

---

## Protocol Registry

```python
PROTOCOL_REGISTRY: Dict[str, Protocol] = {
    # protocol_name -> Protocol instance
}

PROTOCOL_LIST: List[Protocol] = [
    # Ordered list of all protocols
]

def get_protocol(name: str) -> Optional[Protocol]:
    """Get protocol by name"""

def list_protocols() -> List[str]:
    """Get list of all protocol names"""
```

---

## Block Math Functions

```python
# Bit operations
bit_read(value: int, bit: int) -> int           # Read bit (0 or 1)
bit_set(value: int, bit: int) -> int            # Set bit to 1
bit_clear(value: int, bit: int) -> int           # Set bit to 0
bit_write(value: int, bit: int, bitvalue: int) -> int  # Set bit

# Timing utilities
duration_diff(x: int, y: int) -> int             # abs(x - y)

# Key manipulation
reverse_key(key: int, bit_count: int) -> int     # Reverse bit order
get_parity(key: int, bit_count: int) -> int      # Calculate parity
parity8(byte: int) -> int                        # Parity of byte

# CRC functions
crc4(data: bytes, polynomial: int, init: int = 0) -> int
crc7(data: bytes, polynomial: int, init: int = 0) -> int
crc8(data: bytes, polynomial: int, init: int = 0) -> int
crc8le(data: bytes, polynomial: int, init: int = 0) -> int
crc16(data: bytes, polynomial: int, init: int = 0) -> int
crc16lsb(data: bytes, polynomial: int, init: int = 0) -> int

# LFSR digest (for rolling code protocols)
lfsr_digest8(data: bytes, gen: int, key: int) -> int
lfsr_digest8_reflect(data: bytes, gen: int, key: int) -> int
lfsr_digest16(data: bytes, gen: int, key: int) -> int

# Byte operations
add_bytes(data: bytes) -> int                    # Sum bytes
xor_bytes(data: bytes) -> int                    # XOR bytes

# Decoder helpers
add_bit(decoder, bit: int) -> None              # Add bit to decoder buffer
get_hash_data(decode_data: int, decode_count_bit: int) -> int
```