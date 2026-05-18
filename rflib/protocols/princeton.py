from typing import Optional, Dict, Any
from dataclasses import dataclass
from enum import IntEnum

from .base import (
    Protocol, Decoder, Encoder, LevelDuration,
    SubGhzProtocolType, SubGhzProtocolFlag, SubGhzBlockConst,
    SubGhzBlockGeneric
)
from .blocks.math import duration_diff, bit_read, reverse_key, add_bit


SUBGHZ_PROTOCOL_PRINCETON_NAME = "Princeton"
PRINCETON_GUARD_TIME_DEFAULT = 30


PRINCETON_CONST = SubGhzBlockConst(
    te_short=390,
    te_long=1170,
    te_delta=300,
    min_count_bit_for_found=24
)


class PrincetonDecoderStep(IntEnum):
    RESET = 0
    SAVE_DURATION = 1
    CHECK_DURATION = 2


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
        self.decode_data = 0
        self.decode_count_bit = 0

    def feed(self, level: bool, duration: int):
        if self.parser_step == PrincetonDecoderStep.RESET:
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
                if duration >= PRINCETON_CONST.te_long * 2:
                    self.parser_step = PrincetonDecoderStep.SAVE_DURATION
                    if self.decode_count_bit == PRINCETON_CONST.min_count_bit_for_found:
                        if self.last_data == self.decode_data and self.last_data != 0:
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
                    return

                self.te += duration

                if (duration_diff(self.te_last, PRINCETON_CONST.te_short) <
                        PRINCETON_CONST.te_delta and
                    duration_diff(duration, PRINCETON_CONST.te_long) <
                        PRINCETON_CONST.te_delta * 3):
                    add_bit(self, 0)
                    self.parser_step = PrincetonDecoderStep.SAVE_DURATION

                elif (duration_diff(self.te_last, PRINCETON_CONST.te_long) <
                      PRINCETON_CONST.te_delta * 3 and
                      duration_diff(duration, PRINCETON_CONST.te_short) <
                      PRINCETON_CONST.te_delta):
                    add_bit(self, 1)
                    self.parser_step = PrincetonDecoderStep.SAVE_DURATION
                else:
                    self.parser_step = PrincetonDecoderStep.RESET
            else:
                self.parser_step = PrincetonDecoderStep.RESET

    def get_string(self) -> str:
        self.generic.serial = self.generic.data >> 4
        self.generic.btn = self.generic.data & 0xF
        data_rev = reverse_key(self.generic.data, self.generic.data_count_bit)
        return (
            f"{self.generic.protocol_name} {self.generic.data_count_bit}bit\n"
            f"Key:0x{self.generic.data:08X}\n"
            f"Yek:0x{data_rev:08X}\n"
            f"Sn:0x{self.generic.serial:05X} Btn:{self.generic.btn:X}\n"
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
        for i in range(self.generic.data_count_bit - 1, -1, -1):
            bit = bit_read(self.generic.data, i)
            if bit:
                self.upload.append(LevelDuration(True, self.te * 3))
                self.upload.append(LevelDuration(False, self.te))
            else:
                self.upload.append(LevelDuration(True, self.te))
                self.upload.append(LevelDuration(False, self.te * 3))
        self.upload.append(LevelDuration(True, self.te))
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
    def decoder_cls(self):
        return PrincetonDecoder

    @property
    def encoder_cls(self):
        return PrincetonEncoder


subghz_protocol_princeton = PrincetonProtocol()