from fastapi import APIRouter

from app.domains.auth.router import router as auth_router
from app.domains.customers.router import router as customers_router
from app.domains.staff.router import router as staff_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router)
api_router.include_router(staff_router)
api_router.include_router(customers_router)

