from fastapi import APIRouter

from app.domains.auth.router import router as auth_router
from app.domains.analytics.router import router as analytics_router
from app.domains.branches.admin_router import router as branches_admin_router
from app.domains.branches.router import router as branches_router
from app.domains.customers.customer_router import router as customers_customer_router
from app.domains.customers.router import router as customers_router
from app.domains.dashboard.customer_router import router as dashboard_customer_router
from app.domains.dashboard.router import router as dashboard_router
from app.domains.inventory.admin_router import router as inventory_admin_router
from app.domains.inventory.router import router as inventory_router
from app.domains.leads.customer_router import router as leads_customer_router
from app.domains.leads.router import router as leads_router
from app.domains.notifications.admin_router import router as notifications_admin_router
from app.domains.notifications.router import router as notifications_router
from app.domains.ownership.admin_router import router as ownership_admin_router
from app.domains.ownership.customer_router import router as ownership_customer_router
from app.domains.sales.customer_router import router as sales_customer_router
from app.domains.service.customer_router import router as service_customer_router
from app.domains.service.router import router as service_router
from app.domains.staff.router import router as staff_router
from app.domains.support.customer_router import router as support_customer_router
from app.domains.support.router import router as support_router
from app.domains.users.router import router as users_router
from app.domains.warranty.customer_router import router as warranty_customer_router
from app.domains.warranty.router import router as warranty_router
from app.realtime.ticket_gateway import router as realtime_ticket_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(branches_router)
api_router.include_router(branches_admin_router)
api_router.include_router(staff_router)
api_router.include_router(inventory_router)
api_router.include_router(inventory_admin_router)
api_router.include_router(customers_router)
api_router.include_router(leads_router)
api_router.include_router(dashboard_router)
api_router.include_router(notifications_admin_router)
api_router.include_router(notifications_router)
api_router.include_router(customers_customer_router)
api_router.include_router(dashboard_customer_router)
api_router.include_router(support_customer_router)
api_router.include_router(support_router)
api_router.include_router(ownership_customer_router)
api_router.include_router(ownership_admin_router)
api_router.include_router(warranty_customer_router)
api_router.include_router(warranty_router)
api_router.include_router(realtime_ticket_router)
api_router.include_router(analytics_router)
api_router.include_router(service_router)
api_router.include_router(leads_customer_router)
api_router.include_router(sales_customer_router)
api_router.include_router(service_customer_router)
