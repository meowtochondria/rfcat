from typing import Optional, Dict, Any
from dataclasses import dataclass
from enum import IntEnum

from .base import (
    Protocol, Decoder, Encoder, LevelDuration,
    SubGhzProtocolType, SubGhzProtocolFlag, SubGhzBlockConst,
    SubGhzBlockGeneric
)
from .blocks.math import duration_diff, bit_read, reverse_key, add_bit


SUBGHZ_PROTOCOL_GATE_TX_NAME = "GateTX"


GATE_TX_CONST = SubGhzBlockConst(
    te_short=350,
    te_long=700,
    te_delta=100,
    min_count_bit_for_found=24
)


class GateTXDecoderStep(IntEnum):
    RESET = 0
    FOUND_START_BIT = 1
    SAVE_DURATION = 2
    CHECK_DURATION = 3


class GateTXDecoder(Decoder):
    def __init__(self, environment=None):
        super().__init__(environment)
        self.generic.protocol_name = SUBGHZ_PROTOCOL_GATE_TX_NAME

    def reset(self):
        self.parser_step = GateTXDecoderStep.RESET
        self.decode_data = 0
        self.decode_count_bit = 0

    def feed(self, level: bool, duration: int):
        if self.parser_step == GateTXDecoderStep.RESET:
            if (not level and
                duration_diff(duration, GATE_TX_CONST.te_short * 47) <
                    GATE_TX_CONST.te_delta * 47):
                self.parser_step = GateTXDecoderStep.FOUND_START_BIT

        elif self.parser_step == GateTXDecoderStep.FOUND_START_BIT:
            if (level and
                duration_diff(duration, GATE_TX_CONST.te_long) <
                    GATE_TX_CONST.te_delta * 3):
                self.parser_step = GateTXDecoderStep.SAVE_DURATION
                self.decode_data = 0
                self.decode_count_bit = 0
            else:
                self.parser_step = GateTXDecoderStep.RESET

        elif self.parser_step == GateTXDecoderStep.SAVE_DURATION:
            if not level:
                if duration >= (GATE_TX_CONST.te_short * 10 + GATE_TX_CONST.te_delta):
                    self.parser_step = GateTXDecoderStep.FOUND_START_BIT
                    if self.decode_count_bit == GATE_TX_CONST.min_count_bit_for_found:
                        self.generic.data = self.decode_data
                        self.generic.data_count_bit = self.decode_count_bit
                        if self.callback:
                            self.callback(self, self.context)
                    self.decode_data = 0
                    self.decode_count_bit = 0
                else:
                    self.te_last = duration
                    self.parser_step = GateTXDecoderStep.CHECK_DURATION

        elif self.parser_step == GateTXDecoderStep.CHECK_DURATION:
            if level:
                if (duration_diff(self.te_last, GATE_TX_CONST.te_short) <
                        GATE_TX_CONST.te_delta and
                    duration_diff(duration, GATE_TX_CONST.te_long) <
                        GATE_TX_CONST.te_delta * 3):
                    add_bit(self, 0)
                    self.parser_step = GateTXDecoderStep.SAVE_DURATION

                elif (duration_diff(self.te_last, GATE_TX_CONST.te_long) <
                      GATE_TX_CONST.te_delta * 3 and
                      duration_diff(duration, GATE_TX_CONST.te_short) <
                      GATE_TX_CONST.te_delta):
                    add_bit(self, 1)
                    self.parser_step = GateTXDecoderStep.SAVE_DURATION
                else:
                    self.parser_step = GateTXDecoderStep.RESET
            else:
                self.parser_step = GateTXDecoderStep.RESET

    def get_string(self) -> str:
        code_found_reverse = reverse_key(self.generic.data, self.generic.data_count_bit)
        self.generic.serial = ((code_found_reverse & 0xFF) << 12 |
                               ((code_found_reverse >> 8) & 0xFF) << 4 |
                               ((code_found_reverse >> 20) & 0x0F))
        self.generic.btn = (code_found_reverse >> 16) & 0x0F
        return (
            f"{self.generic.protocol_name} {self.generic.data_count_bit}bit\n"
            f"Key:{self.generic.data:06X}\n"
            f"Sn:{self.generic.serial:05X}  Btn:{self.generic.btn:X}"
        )


class GateTXEncoder(Encoder):
    def __init__(self, environment=None):
        super().__init__(environment)
        self.generic.protocol_name = SUBGHZ_PROTOCOL_GATE_TX_NAME

    def deserialize(self, data: Dict[str, Any]) -> bool:
        self.generic.data = data.get('key', 0)
        self.generic.data_count_bit = data.get('bit', 24)
        self.repeat = data.get('repeat', 10)
        return self._generate_upload()

    def _generate_upload(self) -> bool:
        self.upload = []
        self.upload.append(LevelDuration(False, GATE_TX_CONST.te_short * 49))
        self.upload.append(LevelDuration(True, GATE_TX_CONST.te_long))
        for i in range(self.generic.data_count_bit - 1, -1, -1):
            bit = bit_read(self.generic.data, i)
            if bit:
                self.upload.append(LevelDuration(False, GATE_TX_CONST.te_long))
                self.upload.append(LevelDuration(True, GATE_TX_CONST.te_short))
            else:
                self.upload.append(LevelDuration(False, GATE_TX_CONST.te_short))
                self.upload.append(LevelDuration(True, GATE_TX_CONST.te_long))
        self.is_running = True
        return True

    def stop(self):
        self.is_running = False


class GateTXProtocol(Protocol):
    @property
    def name(self) -> str:
        return SUBGHZ_PROTOCOL_GATE_TX_NAME

    @property
    def type(self) -> SubGhzProtocolType:
        return SubGhzProtocolType.STATIC

    @property
    def flag(self) -> SubGhzProtocolFlag:
        return (SubGhzProtocolFlag.FREQ_433 |
                SubGhzProtocolFlag.MOD_AM |
                SubGhzProtocolFlag.DECODABLE |
                SubGhzProtocolFlag.LOAD |
                SubGhzProtocolFlag.SAVE |
                SubGhzProtocolFlag.SEND)

    @property
    def decoder_cls(self):
        return GateTXDecoder

    @property
    def encoder_cls(self):
        return GateTXEncoder


subghz_protocol_gate_tx = GateTXProtocol()