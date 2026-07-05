from tortoise import Tortoise, fields, models
import os

class AIModel(models.Model):
    id = fields.IntField(pk=True)
    friendly_name = fields.CharField(max_length=255)
    model_name = fields.CharField(max_length=255)
    path = fields.CharField(max_length=1024)
    type = fields.CharField(max_length=255)

    class Meta:
        table = "ai_models"

class UserAccount(models.Model):
    id = fields.IntField(pk=True)
    username = fields.CharField(max_length=64, unique=True, index=True)
    password_hash = fields.CharField(max_length=255)
    is_admin = fields.BooleanField(default=False)
    is_disabled = fields.BooleanField(default=False)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "users"

class ApiKey(models.Model):
    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=128, null=True)
    key_hash = fields.CharField(max_length=64, unique=True, index=True)
    scopes = fields.JSONField(null=True)
    is_revoked = fields.BooleanField(default=False)
    created_at = fields.DatetimeField(auto_now_add=True)
    revoked_at = fields.DatetimeField(null=True)

    class Meta:
        table = "api_keys"

class WebAuthnCredential(models.Model):
    id = fields.IntField(pk=True)
    user = fields.ForeignKeyField("models.UserAccount", related_name="credentials", on_delete=fields.CASCADE)
    credential_id = fields.CharField(max_length=512, unique=True, index=True)
    public_key = fields.TextField()  # Base64URL encoded public key string
    sign_count = fields.IntField(default=0)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "webauthn_credentials"

class ProjectAlias(models.Model):
    canonical = fields.CharField(pk=True, max_length=255)
    repoId = fields.CharField(max_length=255, null=True)
    owner = fields.CharField(max_length=255, null=True)
    isPrivate = fields.BooleanField(default=False)
    aliases = fields.JSONField(default=list)
    previousRemote = fields.CharField(max_length=255, null=True)
    newRemote = fields.CharField(max_length=255, null=True)
    notes = fields.TextField(null=True)
    isDeleted = fields.BooleanField(default=False)
    isFork = fields.BooleanField(default=False)
    createdAt = fields.DatetimeField(auto_now_add=True)
    renamedAt = fields.DatetimeField(null=True)
    deletedAt = fields.DatetimeField(null=True)

    class Meta:
        table = "project_aliases"


async def init_db(db_url: str):
    # Register both db and api_server modules for Tortoise ORM
    await Tortoise.init(
        db_url=db_url,
        modules={"models": ["db", "api.database", "api_server"]}
    )
    await Tortoise.generate_schemas()

async def close_db():
    await Tortoise.close_connections()
