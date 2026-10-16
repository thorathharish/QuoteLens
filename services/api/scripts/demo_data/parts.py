"""Declarative demo catalog: real manufacturer part numbers, synthetic commercial data.

Prices, stock, lead times and lifecycle states are illustrative values generated for the
demo. They are published with mode=DEMO_SNAPSHOT and `DEMO-` SKUs, and must never be
presented as real distributor data. Live adapters (Phase 3, P1) replace them when API keys
are configured.

`profile` selects how offers are synthesized (see generate_demo_data.py):
  standard        3 authorized distributors, healthy stock
  single_source   one authorized distributor only                      → risk S02
  long_lead       little stock anywhere, 16-week factory lead time     → S01, S03
  price_outlier   one distributor ~2.3x the others                     → P01
  reel_only       full-reel MOQ and multiple only                      → P03 (MOQ excess)
  no_stock        authorized stock 0 everywhere (used with OBSOLETE)   → L01 blocker, S01
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from app.domain.enums import Lifecycle

# Canonical manufacturer names (BOMs below deliberately use aliases such as "TI").
TI = "Texas Instruments"
ST = "STMicroelectronics"
MCHP = "Microchip Technology"
NXP = "NXP Semiconductors"
ALLEGRO = "Allegro MicroSystems"
INFINEON = "Infineon Technologies"
NEXPERIA = "Nexperia"
VISHAY = "Vishay"
LITTELFUSE = "Littelfuse"
LITEON = "Lite-On"
YAGEO = "Yageo"
PANASONIC = "Panasonic"
MURATA = "Murata"
SAMSUNG = "Samsung Electro-Mechanics"
KEMET = "KEMET"
BOURNS = "Bourns"
WURTH = "Würth Elektronik"
ABRACON = "Abracon"
MOLEX = "Molex"
TE = "TE Connectivity"
ONSEMI = "onsemi"
DIODES = "Diodes Incorporated"
ESPRESSIF = "Espressif Systems"
BOSCH = "Bosch Sensortec"
ADI = "Analog Devices"
GCT = "GCT"
JST = "JST"
COILCRAFT = "Coilcraft"


@dataclass(frozen=True)
class PartSpec:
    mpn: str
    manufacturer: str
    category: str
    description: str
    package: str | None
    unit_price: Decimal  # synthetic qty-1 list price, USD
    params: dict[str, str | float | int] = field(default_factory=dict)
    lifecycle: Lifecycle = Lifecycle.ACTIVE
    ltb_date: date | None = None
    profile: str = "standard"
    reel_qty: int = 0  # 0 → derived from category


def _r(mpn: str, ohms: float, pkg: str, tol: float = 1.0, watts: float = 0.1) -> PartSpec:
    return PartSpec(
        mpn,
        YAGEO,
        "resistor",
        f"RES SMD {_ohm_label(ohms)} {tol:g}% {watts:g}W {pkg}",
        pkg,
        Decimal("0.10"),
        {"resistance_ohm": ohms, "tolerance_pct": tol, "power_w": watts, "package": pkg},
    )


def _c(
    mpn: str, mfr: str, farads: float, volts: int, dielectric: str, pkg: str, price: str
) -> PartSpec:
    return PartSpec(
        mpn,
        mfr,
        "capacitor",
        f"CAP CER {_farad_label(farads)} {volts}V {dielectric} {pkg}",
        pkg,
        Decimal(price),
        {
            "capacitance_f": farads,
            "voltage_v": volts,
            "dielectric": dielectric,
            "tolerance_pct": 10.0,
            "package": pkg,
        },
    )


def _ohm_label(ohms: float) -> str:
    if ohms >= 1000:
        return f"{ohms / 1000:g}K"
    return f"{ohms:g}R" if ohms >= 1 else f"{ohms * 1000:g}mR"


def _farad_label(farads: float) -> str:
    for scale, unit in ((1e-6, "UF"), (1e-9, "NF"), (1e-12, "PF")):
        if farads >= scale:
            return f"{farads / scale:g}{unit}"
    return f"{farads:g}F"


PARTS: list[PartSpec] = [
    # ── Motor controller: ICs ────────────────────────────────
    PartSpec(
        "STM32G431CBT6",
        ST,
        "mcu",
        "MCU ARM Cortex-M4 170MHz 128KB Flash LQFP-48",
        "LQFP-48",
        Decimal("5.80"),
        {
            "core": "Cortex-M4",
            "flash_kb": 128,
            "pins": 48,
            "package": "LQFP-48",
            "temp_min_c": -40,
            "temp_max_c": 85,
        },
        profile="single_source",
    ),
    PartSpec(
        "STM32G431CBT6TR",
        ST,
        "mcu",
        "MCU ARM Cortex-M4 170MHz 128KB Flash LQFP-48 (tape & reel)",
        "LQFP-48",
        Decimal("5.65"),
        {
            "core": "Cortex-M4",
            "flash_kb": 128,
            "pins": 48,
            "package": "LQFP-48",
            "temp_min_c": -40,
            "temp_max_c": 85,
        },
    ),
    PartSpec(
        "DRV8323RSRGZR",
        TI,
        "gate_driver",
        "3-phase smart gate driver, buck + 3x CSA, SPI, VQFN-48",
        "VQFN-48",
        Decimal("6.95"),
        {
            "function": "3-phase gate driver",
            "interface": "SPI",
            "vm_max_v": 60,
            "package": "VQFN-48",
            "temp_min_c": -40,
            "temp_max_c": 125,
        },
        profile="long_lead",
    ),
    PartSpec(
        "DRV8323RHRGZR",
        TI,
        "gate_driver",
        "3-phase smart gate driver, buck + 3x CSA, hardware I/F, VQFN-48",
        "VQFN-48",
        Decimal("6.80"),
        {
            "function": "3-phase gate driver",
            "interface": "Hardware",
            "vm_max_v": 60,
            "package": "VQFN-48",
            "temp_min_c": -40,
            "temp_max_c": 125,
        },
    ),
    PartSpec(
        "INA240A1PWR",
        TI,
        "current_sense",
        "Current sense amp, gain 20V/V, PWM rejection, TSSOP-8",
        "TSSOP-8",
        Decimal("2.85"),
        {
            "gain_v_per_v": 20,
            "cm_max_v": 80,
            "package": "TSSOP-8",
            "temp_min_c": -40,
            "temp_max_c": 125,
        },
        profile="price_outlier",
    ),
    PartSpec(
        "INA240A2PWR",
        TI,
        "current_sense",
        "Current sense amp, gain 50V/V, PWM rejection, TSSOP-8",
        "TSSOP-8",
        Decimal("2.85"),
        {
            "gain_v_per_v": 50,
            "cm_max_v": 80,
            "package": "TSSOP-8",
            "temp_min_c": -40,
            "temp_max_c": 125,
        },
    ),
    PartSpec(
        "LM5164DDAR",
        TI,
        "dc_dc",
        "Sync buck converter 6-100V in, 1A, SO-8 PowerPAD",
        "SO-8 PowerPAD",
        Decimal("2.10"),
        {"vin_max_v": 100, "iout_a": 1, "topology": "buck", "package": "SO-8 PowerPAD"},
    ),
    PartSpec(
        "TPS54331DDR",
        TI,
        "dc_dc",
        "Buck converter 3.5-28V in, 3A, SOIC-8 PowerPAD",
        "SOIC-8",
        Decimal("1.45"),
        {"vin_max_v": 28, "iout_a": 3, "topology": "buck", "package": "SOIC-8"},
    ),
    PartSpec(
        "TLV75533PDBVR",
        TI,
        "ldo",
        "LDO 3.3V 500mA SOT-23-5",
        "SOT-23-5",
        Decimal("0.32"),
        {"vout_v": 3.3, "iout_ma": 500, "vin_max_v": 5.5, "package": "SOT-23-5"},
    ),
    PartSpec(
        "MCP1700T-3302E/TT",
        MCHP,
        "ldo",
        "LDO 3.3V 250mA SOT-23",
        "SOT-23",
        Decimal("0.40"),
        {"vout_v": 3.3, "iout_ma": 250, "vin_max_v": 6, "package": "SOT-23"},
    ),
    PartSpec(
        "MCP2551-I/SN",
        MCHP,
        "can_transceiver",
        "High-speed CAN transceiver 1Mbps SOIC-8",
        "SOIC-8",
        Decimal("1.05"),
        {
            "standard": "ISO 11898",
            "max_rate_kbps": 1000,
            "package": "SOIC-8",
            "temp_min_c": -40,
            "temp_max_c": 85,
        },
        lifecycle=Lifecycle.NRND,
    ),
    PartSpec(
        "MCP2561-E/SN",
        MCHP,
        "can_transceiver",
        "High-speed CAN transceiver 1Mbps, SPLIT pin, SOIC-8",
        "SOIC-8",
        Decimal("0.98"),
        {
            "standard": "ISO 11898",
            "max_rate_kbps": 1000,
            "package": "SOIC-8",
            "temp_min_c": -40,
            "temp_max_c": 125,
        },
    ),
    PartSpec(
        "24LC256-I/SN",
        MCHP,
        "memory",
        "EEPROM 256Kbit I2C 400kHz SOIC-8",
        "SOIC-8",
        Decimal("0.92"),
        {"density_kbit": 256, "interface": "I2C", "package": "SOIC-8"},
    ),
    PartSpec(
        "TLV9062IDR",
        TI,
        "opamp",
        "Dual op amp RRIO 10MHz SOIC-8",
        "SOIC-8",
        Decimal("0.58"),
        {"channels": 2, "gbw_mhz": 10, "package": "SOIC-8"},
    ),
    PartSpec(
        "LMV321IDBVR",
        TI,
        "opamp",
        "Single op amp RRO 1MHz SOT-23-5",
        "SOT-23-5",
        Decimal("0.30"),
        {"channels": 1, "gbw_mhz": 1, "package": "SOT-23-5"},
    ),
    PartSpec(
        "LM75BD,118",
        NXP,
        "sensor",
        "Digital temperature sensor I2C SO-8",
        "SO-8",
        Decimal("0.55"),
        {"interface": "I2C", "accuracy_c": 2, "package": "SO-8"},
    ),
    PartSpec(
        "A1101ELHLT-T",
        ALLEGRO,
        "hall_sensor",
        "Hall-effect unipolar switch, open drain, SOT-23W",
        "SOT-23W",
        Decimal("0.78"),
        {
            "function": "unipolar switch",
            "output": "open drain",
            "vcc_max_v": 24,
            "package": "SOT-23W",
            "temp_min_c": -40,
            "temp_max_c": 85,
        },
        lifecycle=Lifecycle.OBSOLETE,
        ltb_date=date(2026, 3, 31),
        profile="no_stock",
    ),
    PartSpec(
        "A1120ELHLX-T",
        ALLEGRO,
        "hall_sensor",
        "Hall-effect unipolar switch, chopper-stabilized, SOT-23W",
        "SOT-23W",
        Decimal("0.62"),
        {
            "function": "unipolar switch",
            "output": "open drain",
            "vcc_max_v": 24,
            "package": "SOT-23W",
            "temp_min_c": -40,
            "temp_max_c": 85,
        },
    ),
    PartSpec(
        "USBLC6-2SC6",
        ST,
        "esd",
        "ESD protection 2-line + VBUS SOT-23-6",
        "SOT-23-6",
        Decimal("0.45"),
        {"lines": 2, "vrwm_v": 5.25, "package": "SOT-23-6"},
    ),
    PartSpec(
        "TPD2E2U06DRLR",
        TI,
        "esd",
        "ESD protection 2-channel SOT-5X3",
        "SOT-5X3",
        Decimal("0.35"),
        {"lines": 2, "vrwm_v": 5.5, "package": "SOT-5X3"},
    ),
    PartSpec(
        "REF3033AIDBZR",
        TI,
        "reference",
        "Voltage reference 3.3V 0.2% SOT-23-3",
        "SOT-23-3",
        Decimal("1.35"),
        {"vout_v": 3.3, "accuracy_pct": 0.2, "package": "SOT-23-3"},
    ),
    PartSpec(
        "SN74LVC1G17DBVR",
        TI,
        "logic",
        "Single Schmitt-trigger buffer SOT-23-5",
        "SOT-23-5",
        Decimal("0.22"),
        {"function": "buffer", "schmitt": "yes", "package": "SOT-23-5"},
    ),
    # ── Motor controller: discretes ──────────────────────────
    PartSpec(
        "BSC040N08NS5ATMA1",
        INFINEON,
        "mosfet",
        "N-MOSFET 80V 100A 4mOhm TDSON-8",
        "TDSON-8",
        Decimal("2.40"),
        {"polarity": "N", "vds_v": 80, "rds_on_mohm": 4.0, "id_a": 100, "package": "TDSON-8"},
    ),
    PartSpec(
        "2N7002,215",
        NEXPERIA,
        "mosfet",
        "N-MOSFET 60V 300mA SOT-23",
        "SOT-23",
        Decimal("0.12"),
        {"polarity": "N", "vds_v": 60, "id_a": 0.3, "package": "SOT-23"},
    ),
    PartSpec(
        "MMBT3904LT1G",
        ONSEMI,
        "bjt",
        "NPN transistor 40V 200mA SOT-23",
        "SOT-23",
        Decimal("0.06"),
        {"polarity": "NPN", "vce_v": 40, "ic_a": 0.2, "package": "SOT-23"},
    ),
    PartSpec(
        "BAT54S,215",
        NEXPERIA,
        "diode",
        "Schottky dual series 30V 200mA SOT-23",
        "SOT-23",
        Decimal("0.10"),
        {"type": "schottky", "vr_v": 30, "if_a": 0.2, "package": "SOT-23"},
    ),
    PartSpec(
        "SS34-E3/57T",
        VISHAY,
        "diode",
        "Schottky 40V 3A SMA",
        "SMA",
        Decimal("0.32"),
        {"type": "schottky", "vr_v": 40, "if_a": 3, "package": "SMA"},
    ),
    PartSpec(
        "SMBJ58A",
        LITTELFUSE,
        "tvs",
        "TVS unidirectional 58V standoff 600W SMB",
        "SMB",
        Decimal("0.48"),
        {"vrwm_v": 58, "power_w": 600, "package": "SMB"},
    ),
    PartSpec(
        "BZT52C5V1-7-F",
        DIODES,
        "diode",
        "Zener 5.1V 500mW SOD-123",
        "SOD-123",
        Decimal("0.10"),
        {"type": "zener", "vz_v": 5.1, "package": "SOD-123"},
    ),
    PartSpec(
        "PESD2CAN,215",
        NEXPERIA,
        "esd",
        "CAN bus ESD protection SOT-23",
        "SOT-23",
        Decimal("0.25"),
        {"lines": 2, "vrwm_v": 24, "package": "SOT-23"},
    ),
    PartSpec(
        "LTST-C191KGKT",
        LITEON,
        "led",
        "LED green 0603",
        "0603",
        Decimal("0.21"),
        {"color": "green", "package": "0603"},
    ),
    PartSpec(
        "LTST-C191KRKT",
        LITEON,
        "led",
        "LED red 0603",
        "0603",
        Decimal("0.21"),
        {"color": "red", "package": "0603"},
    ),
    # ── Motor controller: passives ───────────────────────────
    PartSpec(
        "WSL2512R0010FEA",
        VISHAY,
        "resistor",
        "RES SMD 1mR 1% 1W 2512 current sense",
        "2512",
        Decimal("0.92"),
        {"resistance_ohm": 0.001, "tolerance_pct": 1.0, "power_w": 1.0, "package": "2512"},
    ),
    _r("RC0603FR-0710KL", 10_000, "0603"),
    _r("RC0603FR-07100RL", 100, "0603"),
    _r("RC0603FR-074K7L", 4_700, "0603"),
    _r("RC0603FR-0722RL", 22, "0603"),
    _r("RC0603FR-071KL", 1_000, "0603"),
    _r("RC0402FR-0749K9L", 49_900, "0402", watts=0.063),
    _r("RC0805FR-07100KL", 100_000, "0805", watts=0.125),
    _r("RC0603JR-070RL", 0, "0603", tol=5.0),
    PartSpec(
        "ERJ-3EKF1002V",
        PANASONIC,
        "resistor",
        "RES SMD 10K 1% 0.1W 0603",
        "0603",
        Decimal("0.10"),
        {"resistance_ohm": 10_000, "tolerance_pct": 1.0, "power_w": 0.1, "package": "0603"},
    ),
    PartSpec(
        "NCP18XH103F03RB",
        MURATA,
        "thermistor",
        "NTC thermistor 10K 1% 0603",
        "0603",
        Decimal("0.25"),
        {"resistance_ohm": 10_000, "b_value_k": 3380, "package": "0603"},
    ),
    _c("GRM188R71H104KA93D", MURATA, 100e-9, 50, "X7R", "0603", "0.10"),
    _c("CL10B104KB8NNNC", SAMSUNG, 100e-9, 50, "X7R", "0603", "0.08"),
    _c("GRM21BR61E106KA73L", MURATA, 10e-6, 25, "X5R", "0805", "0.30"),
    _c("CL10A475KO8NNNC", SAMSUNG, 4.7e-6, 16, "X5R", "0603", "0.08"),
    _c("GRM32ER72A225KA35L", MURATA, 2.2e-6, 100, "X7R", "1210", "0.85"),
    _c("CL21B105KBFNNNE", SAMSUNG, 1e-6, 50, "X7R", "0805", "0.10"),
    _c("GRM1555C1H101JA01D", MURATA, 100e-12, 50, "C0G", "0402", "0.10"),
    _c("GRM188R71C224KA01D", MURATA, 220e-9, 16, "X7R", "0603", "0.10"),
    _c("GRM188R61A106KE69D", MURATA, 10e-6, 10, "X5R", "0603", "0.22"),
    PartSpec(
        "EEE-FK2A101AM",
        PANASONIC,
        "capacitor",
        "CAP ALU 100UF 100V SMD",
        "SMD 12.5x13.5",
        Decimal("1.20"),
        {
            "capacitance_f": 100e-6,
            "voltage_v": 100,
            "dielectric": "aluminum",
            "package": "SMD 12.5x13.5",
        },
    ),
    PartSpec(
        "T491D226K035AT",
        KEMET,
        "capacitor",
        "CAP TANT 22UF 35V 10% D case",
        "D case",
        Decimal("0.95"),
        {"capacitance_f": 22e-6, "voltage_v": 35, "dielectric": "tantalum", "package": "D case"},
    ),
    # ── Magnetics, timing, electromechanical ─────────────────
    PartSpec(
        "SRP1265A-220M",
        BOURNS,
        "inductor",
        "Power inductor 22uH 20% 7A shielded",
        "12.5x13.5mm",
        Decimal("1.10"),
        {"inductance_h": 22e-6, "isat_a": 7.0, "package": "12.5x13.5mm"},
        profile="reel_only",
        reel_qty=500,
    ),
    PartSpec(
        "XAL1010-223MEB",
        COILCRAFT,
        "inductor",
        "Power inductor 22uH 20% 9A shielded",
        "10x11mm",
        Decimal("2.05"),
        {"inductance_h": 22e-6, "isat_a": 9.0, "package": "10x11mm"},
    ),
    PartSpec(
        "744043100",
        WURTH,
        "inductor",
        "Power inductor 10uH WE-TPC 4.8x4.8mm",
        "4.8x4.8mm",
        Decimal("0.70"),
        {"inductance_h": 10e-6, "isat_a": 1.4, "package": "4.8x4.8mm"},
    ),
    PartSpec(
        "744235510",
        WURTH,
        "inductor",
        "Common mode choke for CAN 51uH",
        "1812",
        Decimal("0.85"),
        {"inductance_h": 51e-6, "package": "1812"},
    ),
    PartSpec(
        "BLM18PG221SN1D",
        MURATA,
        "ferrite",
        "Ferrite bead 220R @100MHz 1.4A 0603",
        "0603",
        Decimal("0.10"),
        {"impedance_ohm": 220, "current_a": 1.4, "package": "0603"},
    ),
    PartSpec(
        "ABM8-8.000MHZ-B2-T",
        ABRACON,
        "crystal",
        "Crystal 8MHz 18pF SMD 3.2x2.5",
        "3.2x2.5mm",
        Decimal("0.55"),
        {"frequency_hz": 8_000_000, "load_pf": 18, "package": "3.2x2.5mm"},
    ),
    PartSpec(
        "0430450400",
        MOLEX,
        "connector",
        "Micro-Fit 3.0 header 4 pos dual row",
        "THT",
        Decimal("1.45"),
        {"positions": 4, "pitch_mm": 3.0},
    ),
    PartSpec(
        "0430450200",
        MOLEX,
        "connector",
        "Micro-Fit 3.0 header 2 pos dual row",
        "THT",
        Decimal("1.10"),
        {"positions": 2, "pitch_mm": 3.0},
    ),
    PartSpec(
        "61300611121",
        WURTH,
        "connector",
        "Pin header 6 pos 2.54mm",
        "THT",
        Decimal("0.38"),
        {"positions": 6, "pitch_mm": 2.54},
    ),
    PartSpec(
        "0451005.MRL",
        LITTELFUSE,
        "fuse",
        "Fuse 5A fast-acting 125V NANO2",
        "SMD",
        Decimal("0.70"),
        {"current_a": 5, "voltage_v": 125, "speed": "fast"},
    ),
    PartSpec(
        "1825910-6",
        TE,
        "switch",
        "Tactile switch 6x6mm THT",
        "THT",
        Decimal("0.15"),
        {"type": "tactile"},
    ),
    # ── IoT sensor node ──────────────────────────────────────
    PartSpec(
        "ESP32-C3-MINI-1-N4",
        ESPRESSIF,
        "module",
        "Wi-Fi + BLE module RISC-V 4MB flash",
        "Module",
        Decimal("2.30"),
        {"radio": "Wi-Fi 4 + BLE 5", "flash_mb": 4},
    ),
    PartSpec(
        "BME280",
        BOSCH,
        "sensor",
        "Humidity, pressure, temperature sensor LGA-8",
        "LGA-8",
        Decimal("3.90"),
        {"interface": "I2C/SPI", "package": "LGA-8"},
    ),
    PartSpec(
        "ADXL345BCCZ",
        ADI,
        "sensor",
        "3-axis accelerometer +/-16g LGA-14",
        "LGA-14",
        Decimal("4.10"),
        {"interface": "I2C/SPI", "range_g": 16, "package": "LGA-14"},
    ),
    PartSpec(
        "TPS63031DSKR",
        TI,
        "dc_dc",
        "Buck-boost 3.3V 1A SON-10",
        "SON-10",
        Decimal("1.85"),
        {"vout_v": 3.3, "iout_a": 1, "topology": "buck-boost", "package": "SON-10"},
    ),
    PartSpec(
        "MCP73831T-2ACI/OT",
        MCHP,
        "charger",
        "Li-Ion charger 500mA SOT-23-5",
        "SOT-23-5",
        Decimal("0.62"),
        {"cells": 1, "ichg_ma": 500, "package": "SOT-23-5"},
    ),
    PartSpec(
        "DMG2305UX-7",
        DIODES,
        "mosfet",
        "P-MOSFET 20V 4.2A SOT-23",
        "SOT-23",
        Decimal("0.28"),
        {"polarity": "P", "vds_v": 20, "id_a": 4.2, "package": "SOT-23"},
    ),
    PartSpec(
        "USB4105-GF-A",
        GCT,
        "connector",
        "USB Type-C receptacle 16 pin SMT",
        "SMT",
        Decimal("0.75"),
        {"positions": 16, "standard": "USB-C"},
    ),
    PartSpec(
        "S2B-PH-SM4-TB(LF)(SN)",
        JST,
        "connector",
        "PH 2 pos side-entry SMT header",
        "SMT",
        Decimal("0.32"),
        {"positions": 2, "pitch_mm": 2.0},
    ),
]

# Known alternates (catalog.crossrefs). relation: FFF = form-fit-function drop-in.
CROSSREFS: list[tuple[str, str, str, str]] = [
    ("A1101ELHLT-T", "A1120ELHLX-T", "FFF", "Manufacturer-recommended replacement"),
    (
        "MCP2551-I/SN",
        "MCP2561-E/SN",
        "FUNCTIONAL",
        "Successor; adds SPLIT pin and wider temp range",
    ),
    ("STM32G431CBT6", "STM32G431CBT6TR", "FFF", "Same die, tape & reel packaging"),
    (
        "DRV8323RSRGZR",
        "DRV8323RHRGZR",
        "FUNCTIONAL",
        "Hardware-interface variant; needs firmware review",
    ),
    ("INA240A1PWR", "INA240A2PWR", "FUNCTIONAL", "Different gain (50V/V); needs shunt rescale"),
    ("SRP1265A-220M", "XAL1010-223MEB", "FUNCTIONAL", "Same inductance; different footprint"),
    ("RC0603FR-0710KL", "ERJ-3EKF1002V", "FFF", "Equivalent 0603 thick film"),
    ("GRM188R71H104KA93D", "CL10B104KB8NNNC", "FFF", "Equivalent 0603 X7R 50V"),
]
