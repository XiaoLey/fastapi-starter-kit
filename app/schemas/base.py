from pydantic import BaseModel, ConfigDict


class BaseSc(BaseModel):
    model_config = ConfigDict(extra='forbid', from_attributes=True, validate_assignment=True, validate_by_name=True)
