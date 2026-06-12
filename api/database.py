from tortoise import fields, models, Tortoise
from typing import Optional, List
from api.models import Workflow

_tortoise_initialized = False

class WorkflowDB(models.Model):
    id = fields.CharField(pk=True, max_length=64)
    name = fields.CharField(max_length=255)
    category = fields.CharField(max_length=255, null=True)
    steps = fields.JSONField(null=True)
    pinned = fields.BooleanField(default=False)
    favorite = fields.BooleanField(default=False)

    class Meta:
        table = "workflows"

def db_available() -> bool:
    return bool(_tortoise_initialized and Tortoise._inited)

def workflowdb_to_pydantic(wf: WorkflowDB) -> Workflow:
    pin_value = bool(wf.pinned)
    return Workflow(
        id=wf.id,
        name=wf.name,
        category=wf.category,
        description=None,
        steps=wf.steps or [],
        pinned=pin_value,
        pin=pin_value,
        favorite=wf.favorite,
        lastRun=None,
    )
