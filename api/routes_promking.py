from fastapi import APIRouter, Depends, HTTPException, Request
import logging

router = APIRouter()
logger = logging.getLogger("vaultwares.api")
