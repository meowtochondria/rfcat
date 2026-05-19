## Analysis: Does RfCat Firmware Support Raw Mode?

Yes, the RfCat firmware supports raw mode for sending arbitrary signals. However, it's not a separate "mode" but rather a configuration of the radio's packet handling core. Here's what I found:

### 1. Raw Mode Capability

The CC1111 radio (used in RfCat dongles) supports both packet-based and raw (FIFO) modes. The firmware can be configured for raw mode by setting the `PKTCTRL0` register appropriately:

- **Packet mode**: `PKTCTRL0.LENGTH_CONFIG = 01` (variable) or `10` (fixed)
- **Raw mode**: `PKTCTRL0.LENGTH_CONFIG = 00` (bypass packet handling)

The firmware's `transmit()` function (in `cc1111rf.c`) automatically adapts to the current `PKTCTRL0` setting and will work in raw mode.

### 2. How to Put Dongle in Raw Mode

Using the Python library (`rflib/chipcon_nic.py`), you can:

**Step 1: Disable packet handling** via direct register write (`poke`):
```python
from rflib import *
d = RfCat()
d.poke(0x08, 0x00)  # PKTCTRL0 register = 0x00, raw mode
```

**Step 2: Configure modulation** (FSK, OOK, ASK, MSK, etc.):
```python
d.setMdmModulation(MOD_FSK)    # or MOD_ASK_OOK, MOD_GFSK, MOD_MSK
```

**Step 3: Set symbol rate (data rate)**:
```python
d.setMdmDRate(rate)  # e.g., 38400 for 38.4 kbaud
```

**Step 4: Set deviation** (for FSK/GFSK):
```python
d.setMdmDeviatn(deviation)  # e.g., 20000 for 20 kHz deviation
```

**Step 5: Set frequency**:
```python
d.setFreq(freq_hz)
```

**Step 6: Transmit arbitrary bytes**:
```python
d.RFxmit(b'\x01\x02\x03\x04')  # sends these bytes raw; each byte maps to 8 symbols
```

### 3. Raw Transmission Details

- **Data is sent through the DMA-based `transmit()` function** which feeds the radio's FIFO. This works in both packet and raw modes.
- **Timing**: Symbol timing is controlled by the hardware (DRATE register). The firmware ensures data is fed at the correct rate via DMA. No host involvement during transmission.
- **Infinite mode**: For very long or continuous signals, the firmware supports infinite transmission (`PKTCTRL0_LENGTH_CONFIG_INF`). The Python `RFxmitLong` method uses this.
- **Direct register access**: The firmware implements USB commands `CMD_PEEK` and `CMD_POKE` (system app 0xFF) that allow reading and writing arbitrary memory-mapped registers. The Python library's `peek()` and `poke()` use these.
- **Carrier generation**: To generate a continuous carrier (carrier wave), you can put the radio in TX mode and write a constant pattern to the data register. For FSK/OOK, sending a constant byte will produce a steady carrier (or constant tone for FSK with zero deviation). For OOK, sending `0x00` might produce no output (depending on how the modulator works) and `0xFF` produces carrier; you need to test.

### 4. Existing Applications

The firmware includes multiple applications:

- **`application.c`** - Generic template
- **`appNIC.c`** - Packet-oriented NIC (default for most RfCat dongles) - supports `NIC_XMIT` command which uses `transmit()` and works in raw mode if PKTCTRL0=0.
- **`appSniff.c`** - Sniffer for packets
- **`appFHSSNIC.c`** - Frequency-hopping version
- **`appNetworkTest.c`** - Test app
- **`appCC2531.c`** - For CC2531 chips

The default RfCat firmware (Dons, YS1, Chronos) uses the `appNIC` or `appFHSSNIC` firmware, both of which support the `NIC_XMIT` command. That command calls `transmit()` which is mode-agnostic.

### 5. Limitations

- **USB latency**: For very short transmissions, USB round-trip latency may affect timing. For continuous streams, use a single large transmission or infinite mode.
- **Modulation flexibility**: Modulation format must be set globally; cannot change mid-transmission.
- **No built-in sample-level access**: You cannot modulate individual bits with custom waveforms; you send bytes and the hardware modulates according to the configured format (GFSK, ASK, etc.).
- **Maximum buffer size**: `RF_MAX_TX_BLOCK` (typically ~255 bytes) is the maximum size for a single DMA transfer. For longer data, you need to use `RFxmitLong` which handles multiple buffers and infinite mode.

### 6. Comparison to Flipper

Flipper's "raw" mode is similar:
- Flipper uses the same CC1111 radio.
- Its firmware provides a raw mode that bypasses packet handling.
- It allows setting modulation, data rate, deviation, etc.
- It sends arbitrary byte buffers over USB and uses DMA to feed the radio.

Thus, RfCat can achieve the same results as Flipper's raw mode with proper configuration. The main difference is the host software API.

### Conclusion

The RfCat firmware **does support raw mode** for arbitrary signal transmission. You can:
- Put radio in raw mode by writing setting value of `PKTCTRL0`. See `chipcon_nic.py` for usage and examples.

Thus, the answer is yes, with details on how to do it.
