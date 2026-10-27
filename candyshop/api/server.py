"""One HTTP server hosting the live sources: support desk (REST), marketing events (REST) and billing exports."""
from __future__ import annotations

from . import billing_api, crm_api, marketing_api, support_api

app = support_api.app
app.title = "SweetReach source systems (fake)"
app.description = ("Support desk (/api/v2), marketing hub (/api/v1/marketing), billing exports (/api/v1/billing) and the CRM export (/api/v1/crm) "
                   "for the SweetReach candy-shop example data.")
app.include_router(marketing_api.router)
app.include_router(billing_api.router)
app.include_router(crm_api.router)
