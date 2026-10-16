"""Sample BOMs for the demo and golden tests (LLD §7).

Manufacturer names deliberately vary ("TI", "Texas Instruments", "Murata Electronics", …)
so ingestion's alias normalization is exercised. `Expect` records what each seeded row
should trigger; rows without one are expected to be clean.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Expect:
    match: str = "MATCHED"  # MATCHED | NOT_FOUND | (none when there is no MPN)
    issues: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    note: str = ""


@dataclass(frozen=True)
class BomRow:
    refdes: str
    mpn: str
    manufacturer: str
    description: str
    qty: str
    cpn: str = ""
    uom: str = "EA"
    dnp: str = ""
    target_price: str = ""
    expect: Expect | None = None
    extra: dict[str, str] = field(default_factory=dict)


# ── Hero BOM: 48V BLDC motor controller (≈60 rows, every seeded scenario) ──────────
MOTOR_CONTROLLER: list[BomRow] = [
    BomRow(
        "U1",
        "STM32G431CBT6",
        "ST",
        "MCU Cortex-M4 128KB LQFP-48",
        "1",
        expect=Expect(risks=("S02",), note="Only one authorized distributor stocks it"),
    ),
    BomRow(
        "U2",
        "DRV8323RSRGZR",
        "TI",
        "3-phase gate driver SPI VQFN-48",
        "1",
        expect=Expect(risks=("S01", "S03"), note="Low stock everywhere; 16-week lead time"),
    ),
    BomRow(
        "U3,U4",
        "INA240A1PWR",
        "Texas Instruments",
        "Current sense amplifier 20V/V",
        "2",
        target_price="2.80",
        expect=Expect(risks=("P01",), note="One distributor ~2.3x the others"),
    ),
    BomRow(
        "U5",
        "LM5164DDAR",
        "TI",
        "Buck converter 100V 1A",
        "1",
        target_price="0.95",
        expect=Expect(risks=("P02",), note="Customer target price far below market"),
    ),
    BomRow("U6", "TLV75533PDBVR", "TI", "LDO 3.3V 500mA", "1"),
    BomRow(
        "U7",
        "MCP2551-I/SN",
        "Microchip",
        "CAN transceiver",
        "1",
        expect=Expect(risks=("L02",), note="NRND; successor MCP2561-E/SN"),
    ),
    BomRow("U8", "24LC256-I/SN", "Microchip", "EEPROM 256Kb I2C", "1"),
    BomRow("U9", "TLV9062IDR", "TI", "Dual op amp", "1"),
    BomRow("U10", "LM75BD,118", "NXP", "Temperature sensor", "1"),
    BomRow(
        "U11-U13",
        "A1101ELHLT-T",
        "Allegro",
        "Hall switch SOT-23W",
        "3",
        expect=Expect(
            risks=("L01", "S01"),
            note="Obsolete, no authorized stock (blocker); drop-in A1120ELHLX-T",
        ),
    ),
    BomRow("U14", "USBLC6-2SC6", "ST", "USB ESD protection", "1"),
    BomRow("U15", "REF3033AIDBZR", "TI", "Voltage reference 3.3V", "1"),
    BomRow(
        "U16",
        "TPS5431DDR",
        "TI",
        "Aux buck converter 3A",
        "1",
        expect=Expect(match="NOT_FOUND", risks=("D03",), note="Typo of TPS54331DDR"),
    ),
    BomRow("U17", "TPD2E2U06DRLR", "TI", "ESD 2-channel", "1"),
    BomRow("U18", "LMV321IDBVR", "TI", "Op amp single", "1"),
    BomRow("U19", "MCP1700T-3302E/TT", "Microchip", "LDO 3.3V 250mA", "1"),
    BomRow("U20-U22", "SN74LVC1G17DBVR", "TI", "Schmitt buffer", "3"),
    BomRow("Q1-Q6", "BSC040N08NS5ATMA1", "Infineon", "N-MOSFET 80V 4mOhm", "6"),
    BomRow("Q7,Q8", "2N7002,215", "Nexperia", "N-MOSFET small signal", "2"),
    BomRow("Q9,Q10", "MMBT3904LT1G", "ON Semi", "NPN transistor", "2"),
    BomRow("D1,D2", "BAT54S,215", "Nexperia", "Schottky dual", "2"),
    BomRow("D3", "SS34-E3/57T", "Vishay", "Schottky 3A", "1"),
    BomRow("D4", "SMBJ58A", "Littelfuse", "TVS 58V", "1"),
    BomRow("D5,D6", "LTST-C191KGKT", "Lite-On Inc", "LED green", "2"),
    BomRow("D7", "LTST-C191KRKT", "Lite-On Inc", "LED red", "1"),
    BomRow("D8", "PESD2CAN,215", "Nexperia", "CAN ESD", "1"),
    BomRow("D9,D10", "BZT52C5V1-7-F", "Diodes Inc", "Zener 5.1V", "2"),
    BomRow("R1-R3", "WSL2512R0010FEA", "Vishay Dale", "Shunt 1mOhm 2512", "3"),
    BomRow("R4-R15", "RC0603FR-0710KL", "Yageo", "RES 10K 1% 0603", "12"),
    BomRow(
        "R16-R21",
        "RC0603FR-07100RL",
        "Yageo",
        "RES 100R 1% 0603",
        "5",
        expect=Expect(
            issues=("REFDES_QTY_MISMATCH",), risks=("D05",), note="6 designators but quantity 5"
        ),
    ),
    BomRow("R22,R23", "RC0603FR-074K7L", "Yageo", "RES 4.7K 1% 0603", "2"),
    BomRow("R24-R29", "RC0603FR-0722RL", "Yageo", "RES 22R 1% 0603 gate", "6"),
    BomRow("R30-R33", "RC0603FR-071KL", "Yageo", "RES 1K 1% 0603", "4"),
    BomRow("R34,R35", "RC0402FR-0749K9L", "Yageo", "RES 49.9K 1% 0402", "2"),
    BomRow(
        "R36,R37",
        "RC0805FR-07100KL",
        "",
        "RES 100K 1% 0805 divider",
        "2",
        expect=Expect(issues=("MISSING_MFR",), risks=("D02",), note="Manufacturer column empty"),
    ),
    BomRow("R38,R39", "ERJ-3EKF1002V", "Panasonic", "RES 10K 1% 0603", "2"),
    BomRow("R40-R43", "RC0603JR-070RL", "Yageo", "RES 0R jumper 0603", "4"),
    BomRow(
        "R44",
        "RC0603FR-071KL",
        "Yageo",
        "RES 1K 1% 0603 (option)",
        "1",
        dnp="DNP",
        expect=Expect(issues=("DNP",), note="Do not populate: excluded from costing, not merged"),
    ),
    BomRow("RT1", "NCP18XH103F03RB", "Murata", "NTC 10K 0603", "1"),
    BomRow("C1-C20", "GRM188R71H104KA93D", "Murata Electronics", "CAP 0.1UF 50V X7R 0603", "20"),
    BomRow(
        "C21-C24",
        "GRM188R71H104KA93D",
        "Murata",
        "CAP 0.1UF 50V X7R 0603 (gate)",
        "4",
        expect=Expect(note="Duplicate MPN: consolidated into the C1-C20 line (qty 24)"),
    ),
    BomRow("C25-C30", "GRM21BR61E106KA73L", "Murata", "CAP 10UF 25V X5R 0805", "6"),
    BomRow("C31-C34", "CL10A475KO8NNNC", "Samsung", "CAP 4.7UF 16V X5R 0603", "4"),
    BomRow("C35-C40", "GRM32ER72A225KA35L", "Murata", "CAP 2.2UF 100V X7R 1210 bus", "6"),
    BomRow("C41,C42", "EEE-FK2A101AM", "Panasonic", "CAP ALU 100UF 100V", "2"),
    BomRow("C43-C48", "CL21B105KBFNNNE", "Samsung", "CAP 1UF 50V X7R 0805 bootstrap", "6"),
    BomRow("C49-C52", "GRM1555C1H101JA01D", "Murata", "CAP 100PF 50V C0G 0402", "4"),
    BomRow("C53,C54", "GRM188R71C224KA01D", "Murata", "CAP 0.22UF 16V X7R 0603", "2"),
    BomRow("C55", "T491D226K035AT", "Kemet", "CAP TANT 22UF 35V", "1"),
    BomRow("C56-C59", "GRM188R61A106KE69D", "Murata", "CAP 10UF 10V X5R 0603", "4"),
    BomRow(
        "L1",
        "SRP1265A-220M",
        "Bourns",
        "Inductor 22uH 7A",
        "1",
        expect=Expect(risks=("P03",), note="Reel-only (MOQ 500): large excess at low volume"),
    ),
    BomRow("L2", "744043100", "Wurth Electronics", "Inductor 10uH", "1"),
    BomRow("L3", "744235510", "Würth", "CAN common mode choke", "1"),
    BomRow("FB1-FB4", "BLM18PG221SN1D", "Murata", "Ferrite bead 220R 0603", "4"),
    BomRow("Y1", "ABM8-8.000MHZ-B2-T", "Abracon", "Crystal 8MHz", "1"),
    BomRow("J1", "0430450400", "Molex", "Micro-Fit 4 pos (motor phases)", "1"),
    BomRow(
        "J2",
        "0430450200",
        "Molex",
        "Micro-Fit 2 pos (power)",
        "TBD",
        expect=Expect(issues=("QTY_INVALID",), risks=("D04",), note="Quantity 'TBD' (blocker)"),
    ),
    BomRow("J3", "61300611121", "Würth", "Header 6 pos SWD", "1"),
    BomRow(
        "F1",
        "",
        "",
        "Fuse 5A fast-acting SMD",
        "1",
        expect=Expect(
            match="",
            issues=("MISSING_MPN",),
            risks=("D01",),
            note="No MPN (blocker); demo fixes it to 0451005.MRL",
        ),
    ),
    BomRow("SW1", "1825910-6", "TE", "Tactile switch reset", "1"),
]

# ── Happy path: IoT sensor node (clean) ──────────────────────
IOT_SENSOR: list[BomRow] = [
    BomRow("U1", "ESP32-C3-MINI-1-N4", "Espressif", "Wi-Fi/BLE module", "1"),
    BomRow("U2", "BME280", "Bosch", "Environmental sensor", "1"),
    BomRow("U3", "ADXL345BCCZ", "Analog Devices Inc.", "Accelerometer", "1"),
    BomRow("U4", "TPS63031DSKR", "TI", "Buck-boost 3.3V", "1"),
    BomRow("U5", "MCP73831T-2ACI/OT", "Microchip", "Li-Ion charger", "1"),
    BomRow("U6", "USBLC6-2SC6", "STMicroelectronics", "USB ESD", "1"),
    BomRow("U7", "MCP1700T-3302E/TT", "Microchip", "LDO 3.3V", "1"),
    BomRow("U8", "TPD2E2U06DRLR", "TI", "ESD 2ch", "1"),
    BomRow("U9", "LM75BD,118", "NXP", "Temperature sensor", "1"),
    BomRow("Q1", "DMG2305UX-7", "Diodes Incorporated", "P-MOSFET load switch", "1"),
    BomRow("Q2", "2N7002,215", "Nexperia", "N-MOSFET", "1"),
    BomRow("D1", "BAT54S,215", "Nexperia", "Schottky dual", "1"),
    BomRow("D2", "LTST-C191KGKT", "Lite-On", "LED green", "1"),
    BomRow("D3", "LTST-C191KRKT", "Lite-On", "LED red", "1"),
    BomRow("J1", "USB4105-GF-A", "GCT", "USB-C receptacle", "1"),
    BomRow("J2", "S2B-PH-SM4-TB(LF)(SN)", "JST", "Battery connector", "1"),
    BomRow("J3", "61300611121", "Wurth", "Programming header", "1"),
    BomRow("SW1,SW2", "1825910-6", "TE Connectivity", "Tactile switch", "2"),
    BomRow("R1-R6", "RC0603FR-0710KL", "Yageo", "RES 10K 0603", "6"),
    BomRow("R7,R8", "RC0603FR-074K7L", "Yageo", "RES 4.7K 0603", "2"),
    BomRow("R9,R10", "RC0603FR-071KL", "Yageo", "RES 1K 0603", "2"),
    BomRow("R11", "RC0402FR-0749K9L", "Yageo", "RES 49.9K 0402", "1"),
    BomRow("R12,R13", "RC0805FR-07100KL", "Yageo", "RES 100K 0805", "2"),
    BomRow("C1-C10", "GRM188R71H104KA93D", "Murata", "CAP 0.1UF 0603", "10"),
    BomRow("C11-C14", "GRM21BR61E106KA73L", "Murata", "CAP 10UF 0805", "4"),
    BomRow("C15,C16", "CL10A475KO8NNNC", "Samsung", "CAP 4.7UF 0603", "2"),
    BomRow("C17,C18", "GRM1555C1H101JA01D", "Murata", "CAP 100PF 0402", "2"),
    BomRow("C19-C21", "GRM188R61A106KE69D", "Murata", "CAP 10UF 0603", "3"),
    BomRow("L1", "744043100", "Würth Elektronik", "Inductor 10uH", "1"),
    BomRow("FB1", "BLM18PG221SN1D", "Murata", "Ferrite bead", "1"),
]

# ── Messy export: title block, odd headers, "Nos" units, fitted flag ──
MESSY_TITLE_BLOCK = [
    "ACME Robotics Pvt Ltd - RFQ #RFQ-2026-0412",
    "Assembly: Drive Interface Board  Rev C",
    "Date: 12-Oct-2026     Prepared by: NPI",
]
MESSY_HEADERS = [
    "Sl No",
    "Cust P/N",
    "Part Description",
    "Make",
    "Maker Part No.",
    "Qty/Assy",
    "Unit",
    "Ref Des",
    "Fitted (Y/N)",
    "Remarks",
]
MESSY_FORMAT: list[BomRow] = [
    BomRow("U1", "STM32G431CBT6", "ST Micro", "MCU 128KB", "1", cpn="DIB-1001", uom="Nos"),
    BomRow(
        "U2",
        "MCP2551-I/SN",
        "Microchip Tech",
        "CAN XCVR",
        "1",
        cpn="DIB-1002",
        uom="Nos",
        extra={"Remarks": "Customer approved alt OK"},
    ),
    BomRow("U3", "TLV75533PDBVR", "T.I.", "LDO 3V3", "1", cpn="DIB-1003", uom="Nos"),
    BomRow("U4", "USBLC6-2SC6", "ST Micro", "ESD", "1", cpn="DIB-1004", uom="Nos"),
    BomRow("Q1,Q2", "2N7002,215", "NXP/Nexperia", "MOSFET N", "2", cpn="DIB-1101", uom="Nos"),
    BomRow("D1", "LTST-C191KGKT", "LITEON", "LED GRN", "1", cpn="DIB-1201", uom="Nos"),
    BomRow("D2", "BAT54S,215", "Nexperia", "Schottky", "1", cpn="DIB-1202", uom="Nos"),
    BomRow("R1-R8", "RC0603FR-0710KL", "YAGEO", "10K 1% 0603", "8", cpn="DIB-2001", uom="Nos"),
    BomRow("R9,R10", "RC0603FR-074K7L", "YAGEO", "4K7 1% 0603", "2", cpn="DIB-2002", uom="Nos"),
    BomRow(
        "R11",
        "RC0603FR-071KL",
        "YAGEO",
        "1K 1% 0603",
        "1",
        cpn="DIB-2003",
        uom="Nos",
        dnp="N",
        extra={"Remarks": "Fit only for debug builds"},
    ),
    BomRow(
        "C1-C12",
        "GRM188R71H104KA93D",
        "MURATA",
        "100nF 50V X7R 0603",
        "12",
        cpn="DIB-3001",
        uom="Nos",
    ),
    BomRow(
        "C13-C16", "GRM21BR61E106KA73L", "MURATA", "10uF 25V 0805", "4", cpn="DIB-3002", uom="Nos"
    ),
    BomRow("C17,C18", "CL10A475KO8NNNC", "SAMSUNG", "4u7 16V 0603", "2", cpn="DIB-3003", uom="Nos"),
    BomRow("FB1,FB2", "BLM18PG221SN1D", "MURATA", "Bead 220R", "2", cpn="DIB-4001", uom="Nos"),
    BomRow("Y1", "ABM8-8.000MHZ-B2-T", "ABRACON", "XTAL 8MHz", "1", cpn="DIB-5001", uom="Nos"),
    BomRow("J1", "61300611121", "WURTH", "HDR 6P", "1", cpn="DIB-6001", uom="Nos"),
    BomRow("J2", "USB4105-GF-A", "GCT", "USB-C", "1", cpn="DIB-6002", uom="Nos"),
    BomRow("SW1", "1825910-6", "TE", "Tact switch", "1", cpn="DIB-7001", uom="Nos"),
]
