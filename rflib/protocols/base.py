from dataclasses import dataclass, field
from enum import Enum, IntFlag
from typing import Callable, Optional, List, Dict, Any, Protocol as TypingProtocol
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
    level: bool
    duration: int

    @staticmethod
    def reset():
        return LevelDuration(level=False, duration=0)

    @staticmethod
    def make(level: bool, duration: int) -> 'LevelDuration':
        return LevelDuration(level=level, duration=duration)


@dataclass
class SubGhzBlockConst:
    te_short: int
    te_long: int
    te_delta: int
    min_count_bit_for_found: int


@dataclass
class SubGhzBlockGeneric:
    protocol_name: str = ""
    data: int = 0
    serial: int = 0
    data_count_bit: int = 0
    btn: int = 0
    cnt: int = 0


class Protocol(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def type(self) -> SubGhzProtocolType:
        pass

    @property
    @abstractmethod
    def flag(self) -> SubGhzProtocolFlag:
        pass

    @property
    @abstractmethod
    def decoder_cls(self):
        pass

    @property
    @abstractmethod
    def encoder_cls(self):
        pass


class Decoder(ABC):
    def __init__(self, environment: Optional[Any] = None):
        self.parser_step = 0
        self.te_last = 0
        self.decode_data = 0
        self.decode_count_bit = 0
        self.callback: Optional[Callable] = None
        self.context: Any = None
        self.generic = SubGhzBlockGeneric()

    @abstractmethod
    def feed(self, level: bool, duration: int) -> None:
        pass

    @abstractmethod
    def reset(self) -> None:
        pass

    def get_hash_data(self) -> int:
        data_bytes = self.decode_data.to_bytes(
            (self.decode_count_bit + 7) // 8 if self.decode_count_bit > 0 else 1, 'little'
        )
        return sum(data_bytes) ^ data_bytes[0] if data_bytes else 0

    @abstractmethod
    def get_string(self) -> str:
        pass


class Encoder(ABC):
    def __init__(self, environment: Optional[Any] = None):
        self.is_running = False
        self.repeat = 10
        self.front = 0
        self.upload: List[LevelDuration] = []
        self.generic = SubGhzBlockGeneric()

    @abstractmethod
    def deserialize(self, data: Dict[str, Any]) -> bool:
        pass

    @abstractmethod
    def stop(self) -> None:
        pass

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


class Receiver:
    def __init__(self, protocol_registry: List[Protocol], environment: Optional[Any] = None):
        self.slots: List[Decoder] = []
        self.filter = SubGhzProtocolFlag(0xFFFFFFFF)
        self.callback: Optional[Callable] = None
        self.context = None
        self.environment = environment

        for protocol in protocol_registry:
            if protocol.decoder_cls:
                decoder = protocol.decoder_cls(environment)
                decoder.callback = self._rx_callback
                decoder.context = self
                self.slots.append((protocol, decoder))

    def feed(self, level: bool, duration: int):
        for protocol, slot in self.slots:
            if protocol.flag & self.filter:
                slot.feed(level, duration)

    def reset(self):
        for _, slot in self.slots:
            slot.reset()

    def set_filter(self, flag: SubGhzProtocolFlag):
        self.filter = flag

    def set_rx_callback(self, callback: Callable, context=None):
        self.callback = callback
        self.context = context

    def _rx_callback(self, decoder: Decoder, context):
        if self.callback:
            self.callback(self, decoder, self.context)

    def search_decoder_by_name(self, name: str) -> Optional[Decoder]:
        for protocol, slot in self.slots:
            if protocol.name == name:
                return slot
        return None


class Transmitter:
    def __init__(self, protocol_registry: Dict[str, Protocol], environment: Optional[Any] = None):
        self.protocol: Optional[Protocol] = None
        self.protocol_instance: Optional[Encoder] = None
        self.environment = environment
        self.protocol_registry = protocol_registry

    def load(self, protocol_name: str, data: Dict[str, Any]) -> bool:
        self.protocol = self.protocol_registry.get(protocol_name)
        if self.protocol and self.protocol.encoder_cls:
            self.protocol_instance = self.protocol.encoder_cls(self.environment)
            return self.protocol_instance.deserialize(data)
        return False

    def stop(self) -> bool:
        if self.protocol_instance:
            self.protocol_instance.stop()
            return True
        return False

    def yield_(self) -> LevelDuration:
        if self.protocol_instance:
            return self.protocol_instance.yield_()
        return LevelDuration.reset()