from datetime import datetime
from pydantic import BaseModel

#يعرّف شكل البيانات الداخلة والخارجة من الـAPI
class EnergyReadingCreate(BaseModel):
    room_id: str
    energy: float
    timestamp: datetime


class EnergyReadingResponse(BaseModel):
    id: int
    room_id: str
    energy: float
    timestamp: datetime

    model_config = {
        "from_attributes": True
    }


#يفصل بين: شكل البيانات داخل الـAPI وشكل الجداول داخل الـDB