"""Event handling classes for GUI thread communication."""

from dataclasses import dataclass
from enum import Enum, auto


class TicketPurpose(Enum):
    """Enum for message types passed between converter thread and UI thread."""
    UPDATE_PROGRESS = auto()


@dataclass
class Ticket:
    """Message container for thread-safe communication with GUI.
    
    Attributes:
        ticket_type: The purpose/type of this message
        ticket_value: The message content (typically a status string)
    """
    ticket_type: TicketPurpose
    ticket_value: str
