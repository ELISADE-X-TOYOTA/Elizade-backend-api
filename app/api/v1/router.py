from fastapi import APIRouter

from app.domains.auth.router import router as auth_router
from app.domains.analytics.router import router as analytics_router
from app.domains.branches.router import router as branches_router
from app.domains.customers.router import router as customers_router
from app.domains.dashboard.router import router as dashboard_router
from app.domains.inventory.admin_router import router as inventory_admin_router
from app.domains.inventory.router import router as inventory_router
from app.domains.notifications.admin_router import router as notifications_admin_router
from app.domains.notifications.router import router as notifications_router
from app.domains.staff.router import router as staff_router
from app.domains.support.router import router as support_router
from app.domains.users.router import router as users_router
from app.domains.warranty.router import router as warranty_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(branches_router)
api_router.include_router(staff_router)
api_router.include_router(inventory_router)
api_router.include_router(inventory_admin_router)
api_router.include_router(customers_router)
api_router.include_router(dashboard_router)
api_router.include_router(notifications_admin_router)
api_router.include_router(notifications_router)
api_router.include_router(support_router)
api_router.include_router(warranty_router)
api_router.include_router(analytics_router)
