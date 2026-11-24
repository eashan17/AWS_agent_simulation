"""Policy input and (from slice 3a) the Blueprint schema."""

from pydantic import BaseModel, Field

MAX_INPUT_CHARS = 2000


class PolicyInput(BaseModel):
    """What the policymaker types: the rule, why it exists, and where it applies."""

    text: str = Field(min_length=1, max_length=MAX_INPUT_CHARS)
    purpose: str = Field(min_length=1, max_length=MAX_INPUT_CHARS)
    environment: str = Field(min_length=1, max_length=MAX_INPUT_CHARS)


class Policy(PolicyInput):
    """A stored policy."""

    id: str
    created_at: str
