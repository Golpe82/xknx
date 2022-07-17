import logging
import struct
from typing import Optional

from .knx_hid_datatypes import PacketType, ProtocolID, SequenceNumber, EMIID
from .knx_hid_transfer import KNXUSBTransferProtocolBody, KNXUSBTransferProtocolBodyData, KNXUSBTransferProtocolHeader, KNXUSBTransferProtocolHeaderData

logger = logging.getLogger("xknx.log")
knx_logger = logging.getLogger("xknx.knx")
usb_logger = logging.getLogger("xknx.usb")


class PacketInfoData:
    """ """
    def __init__(self, sequence_number: SequenceNumber, packet_type: PacketType) -> None:
        self.sequence_number = sequence_number
        self.packet_type = packet_type


class PacketInfo:
    """
    Represents part of a KNX header

    If the length of a KNX frame to be passed through USB exceeds the maximal
    length of the KNX HID Report Body, this is 61 octets, the KNX frame shall
    be transmitted in multiple HID reports.
      - Unused bytes in the last HID report frame shall be filled with 00h.
      - The first HID report frame shall have sequence number 1. Also if
        a single HID report is sufficient for the transmission of the KNX frame,
        this single HID report shall have sequence number 1. The use of sequence
        number 0 is not allowed. The sequence number shall be incremented for
        each next HID report that is used for the transmission of a KNX frame.

    | Sequence Number Value | Description                 |
    |:----------------------|:----------------------------|
    | 0h                    | reserved; shall not be used |
    | 1h                    | 1st packet (start packet)   |
    | 2h                    | 2nd packet                  |
    | 3h                    | 3rd packet                  |
    | 4h                    | 4th packet                  |
    | 5h                    | 5th packet                  |
    | other values          | reserved; not used          |

    Parameters
    ----------
    sequence_number: int (½ octet (high nibble))
    packet_type: int (½ octet (low nibble))
    """

    def __init__(self):
        self._sequence_number = None
        self._packet_type = None

    @classmethod
    def from_data(cls, data: PacketInfoData):
        """ """
        obj = cls()
        obj._sequence_number = data.sequence_number
        obj._packet_type = data.packet_type
        return obj

    @classmethod
    def from_knx(cls, data: bytes):
        """ """
        obj = cls()
        obj._init(data)
        return obj

    def to_knx(self) -> bytes:
        """ """
        if self._sequence_number and self._packet_type:
            return struct.pack("<B", (self._sequence_number.value << 4) | self._packet_type.value)
        else:
            return bytes()

    @property
    def sequence_number(self) -> Optional[SequenceNumber]:
        """ """
        return self._sequence_number

    @property
    def packet_type(self) -> Optional[PacketType]:
        """ """
        return self._packet_type

    def _init(self, data: bytes):
        """ """
        if len(data) != 1:
            logger.error(f"received {len(data)} bytes, expected one byte")
            return
        self._sequence_number = SequenceNumber(data[0] >> 4)
        self._packet_type = PacketType(data[0] & 0x0F)


class KNXHIDReportHeaderData:
    """ """
    def __init__(self, packet_info: PacketInfo, data_length: int) -> None:
        self.packet_info = packet_info
        self.data_length = data_length


class KNXHIDReportHeader:
    """
    Represents the header of a KNX HID report frame (3.4.1.2 KNX HID report header)

    Parameters
    ----------
    report_id: str or None (1 octet)
        The Report ID allows the HID Class host driver to distinguish incoming data, e.g. pointer from keyboard
        data, by examining this transfer prefix. The Report ID is a feature, which is supported and can be
        managed by the Host driver.
        (fixed to 0x01)
    packet_info: PacketInfo (1 octet)
    data_length: int (1 octet)
        The data length is the number of octets of the data field (KNX HID Report Body).
        This is the information following the data length field itself. The maximum value is 61.
    """

    def __init__(self) -> None:
        self._report_id = 0x01
        self._packet_info = None
        self._data_length = 0
        self._max_expected_data_length = 61
        self._valid = False

    @classmethod
    def from_data(cls, data: KNXHIDReportHeaderData):
        """ """
        obj = cls()
        obj._packet_info = data.packet_info
        if data.data_length <= obj._max_expected_data_length:
            obj._data_length = data.data_length
            obj._valid = True
        return obj

    @classmethod
    def from_knx(cls, data: bytes):
        """ """
        obj = cls()
        obj._init(data)
        return obj

    def to_knx(self) -> bytes:
        """ """
        if self._valid:
            return struct.pack("<B1sB", self._report_id, self._packet_info.to_knx(), self._data_length)
        else:
            return bytes()

    @property
    def report_id(self) -> int:
        """ """
        return self._report_id

    @report_id.setter
    def report_id(self, value: int):
        """ """
        if value != 0x01:
            logger.warning("the Report ID value shall have the fixed value 01h (3.4.1.2.1 Report ID)")
        self._report_id = value

    @property
    def packet_info(self) -> Optional[PacketInfo]:
        """
        returns an object containing information about the sequence number (3.4.1.2.2 Sequence number)
        and packet type (start/partial/end packet) (3.4.1.2.3 Packet type)
        """
        return self._packet_info

    @property
    def data_length(self) -> int:
        """ """
        return self._data_length

    @property
    def is_valid(self) -> bool:
        """ """
        return self._valid

    def _init(self, data: bytes):
        """ """
        if len(data) > self._max_expected_data_length:
            logger.error(
                f"KNX HID Report Header: received {len(data)} bytes, but expected not more than {self._max_expected_data_length}")
            return
        self._report_id = data[0]
        self._packet_info = PacketInfo.from_knx(data[1:2])
        self._data_length = data[2]
        if self._report_id == 0x01:
            self._valid = True


class KNXHIDReportBodyData:
    """ """
    def __init__(self, protocol_id: ProtocolID, emi_id: EMIID, emi_data: bytes, partial: bool) -> None:
        self.protocol_id = protocol_id
        self.emi_id = emi_id
        self.emi_data = emi_data
        self.partial = partial


class KNXHIDReportBody:
    """ Represents `3.4.1.3 Data (KNX HID report body)` of the KNX specification """

    def __init__(self):
        self._max_size = 61  # HID frame has max. size of 64 - 3 octets for the header
        self._header: Optional[KNXUSBTransferProtocolHeader] = None
        self._body: Optional[KNXUSBTransferProtocolBody] = None
        self._is_valid = False
        self._partial = False

    @classmethod
    def from_data(cls, data: KNXHIDReportBodyData):
        """ """
        obj = cls()
        obj._body = KNXUSBTransferProtocolBody.from_data(KNXUSBTransferProtocolBodyData(data.emi_data, data.partial))
        if data.partial:
            obj._is_valid = obj._body.is_valid
        else:
            obj._header = KNXUSBTransferProtocolHeader.from_data(KNXUSBTransferProtocolHeaderData(obj._body.length, data.protocol_id, data.emi_id))
            obj._is_valid = obj._header.is_valid and obj._body.is_valid
        return obj

    @classmethod
    def from_knx(cls, data: bytes, partial: bool = False):
        """ Takes the report body data bytes and create a `KNXHIDReportBody` object """
        obj = cls()
        obj._init(data, partial)
        return obj

    def to_knx(self) -> bytes:
        """ Converts the data in the object to its byte representation, ready to be sent over USB. """
        if self._header and self._body:
            return self._header.to_knx() + self._body.to_knx(self._partial)
        else:
            return bytes()

    @property
    def transfer_protocol_header(self) -> Optional[KNXUSBTransferProtocolHeader]:
        """
        Contains the header part as described in `3.4.1.3 Data (KNX HID report body)`
        of the KNX specification
        """
        return self._header

    @property
    def transfer_protocol_body(self) -> Optional[KNXUSBTransferProtocolBody]:
        """
        Contains the body part as described in `3.4.1.3 Data (KNX HID report body)`
        of the KNX specification
        """
        return self._body

    @property
    def length(self) -> int:
        """ """
        if self._partial and self._body:
            return self._body.length
        elif self._header and self._body:
            return self._header.header_length + self._body.length
        return 0

    @property
    def is_valid(self) -> bool:
        """ Returns true if all fields could be parsed successfully """
        return self._is_valid

    def _init(self, data: bytes, partial: bool) -> None:
        """ """
        if len(data) != self._max_size:
            logger.error(
                f"only received {len(data)} bytes, expected {self._max_size}. (Unused bytes in the last HID report frame shall be filled with 00h (3.4.1.2.2 Sequence number))"
            )
            return
        self._partial = partial
        if self._partial:
            self._body = KNXUSBTransferProtocolBody.from_knx(data)
            self._is_valid = self._body.is_valid
        else:
            self._header = KNXUSBTransferProtocolHeader.from_knx(data[:8])  # only in the start packet has a header
            self._body = KNXUSBTransferProtocolBody.from_knx(data[8:])
            self._is_valid = self._header.is_valid and self._body.is_valid


class KNXHIDFrameData:
    """ Holds the data necessary to initialize a `KNXHIDFrame` object """

    def __init__(self, packet_info: PacketInfo, hid_report_body_data: KNXHIDReportBodyData) -> None:
        self.packet_info = packet_info
        self.hid_report_body_data = hid_report_body_data


class KNXHIDFrame:
    """ Represents `3.4.1.1 HID report frame structure` of the KNX specification """

    def __init__(self) -> None:
        self._body: Optional[KNXHIDReportBody] = None
        self._expected_byte_count = 64
        self._header: Optional[KNXHIDReportHeader] = None
        self._is_valid = False
        self._partial = False

    @classmethod
    def from_data(cls, data: KNXHIDFrameData):
        """ """
        obj = cls()
        obj._body = KNXHIDReportBody.from_data(data.hid_report_body_data)
        obj._header = KNXHIDReportHeader.from_data(KNXHIDReportHeaderData(data.packet_info, obj._body.length))
        obj._partial = data.hid_report_body_data.partial
        if data.hid_report_body_data.partial:
            obj._is_valid = obj._body.is_valid
        else:
            obj._is_valid = obj._header.is_valid and obj._body.is_valid
        return obj

    @classmethod
    def from_knx(cls, data: bytes, partial: bool = False):
        """ Takes USB HID data and creates a `KNXHIDFrame` object. """
        obj = cls()
        obj._init(data, partial)
        return obj

    def to_knx(self) -> bytes:
        """ Converts the data in the object to its byte representation, ready to be sent over USB. """
        return self._header.to_knx() + self._body.to_knx()

    @property
    def is_valid(self) -> bool:
        """
        Returns true if all fields were parsed successfully and seem to
        be plausible
        """
        return self._is_valid

    @property
    def report_header(self) -> Optional[KNXHIDReportHeader]:
        """
        Contains the information as described in `3.4.1.2 KNX HID report header`
        of the KNX specification

        Fields
          - Report ID
          - Sequence number
          - Packet type
          - Data length
        """
        return self._header

    @property
    def report_body(self) -> Optional[KNXHIDReportBody]:
        """
        Contains the information as described in `3.4.1.3 Data (KNX HID report body)`
        of the KNX specification

        Fields
          - Protocol version
          - Header length
          - Body length
          - Protocol ID
          - EMI ID
          - Manufacturer code
          - EMI message code
          - Data (cEMI/EMI1/EMI2)
        """
        return self._body

    def _init(self, data: bytes, partial: bool):
        """ """
        if len(data) < self._expected_byte_count:
            logger.warning(
                f"only received {len(data)} bytes, expected {self._expected_byte_count}. (Unused bytes in the last HID report frame shall be filled with 00h (3.4.1.2.2 Sequence number))"
            )
        self._partial = partial
        self._header = KNXHIDReportHeader.from_knx(data[:3])
        self._body = KNXHIDReportBody.from_knx(data[3:], partial=partial)
        self._is_valid = self._header.is_valid and self._body.is_valid