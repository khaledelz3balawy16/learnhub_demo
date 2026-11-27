"""Delivery endpoints, mounted at /api/v1/delivery/.

Staff manage cohorts and groups in the console (apps.platform.console.programs). Learners
read their own schedule through their enrolment (apps.learning.api). Nothing is public here.
"""

from ninja import Router

from core.auth import session_auth

router = Router(tags=["delivery"], auth=session_auth)
