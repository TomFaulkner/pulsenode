from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ChannelMCP(ABC):
    url: str

    name: str
    type: str

    @abstractmethod
    async def receive_messages(self): ...

    @abstractmethod
    async def send_message(self): ...
