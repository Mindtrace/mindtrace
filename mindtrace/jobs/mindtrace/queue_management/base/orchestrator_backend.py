from abc import ABC, abstractmethod
import pydantic
class OrchestratorBackend(ABC):
   
   @abstractmethod
   def publish(self, queue_name: str, message: pydantic.BaseModel):
      raise NotImplementedError
   
   @abstractmethod
   def receive_message(self, queue_name: str) -> pydantic.BaseModel:
      raise NotImplementedError
   
   @abstractmethod
   def clean_queue(self, queue_name: str):
      raise NotImplementedError
   
   @abstractmethod
   def delete_queue(self, queue_name: str):
      raise NotImplementedError
   
   @abstractmethod
   def count_queue_messages(self, queue_name: str) -> int:
      raise NotImplementedError
   
   def delete_exchange(self, **kwargs):
      raise NotImplementedError
   
   def delete_exchange(self, **kwargs):
      raise NotImplementedError
   
   def count_exchanges(self, **kwargs):
      raise NotImplementedError

   