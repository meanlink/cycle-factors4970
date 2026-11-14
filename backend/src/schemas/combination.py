from pydantic import BaseModel, Field


class CombinationInput(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    dataset_ids: list[int] = Field(min_length=1)
    resolutions: dict = Field(default_factory=dict)


class CombinationVersionInput(BaseModel):
    dataset_ids: list[int] = Field(min_length=1)
    resolutions: dict = Field(default_factory=dict)
