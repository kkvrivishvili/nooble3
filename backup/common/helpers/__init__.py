"""
Utilidades y helpers compartidos para todos los servicios backend.
"""

from .health import basic_health_check, detailed_status_check, get_service_health
from .swagger import (
    configure_swagger_ui,
    get_swagger_ui_html,
    add_example_to_endpoint,
    generate_docstring_template,
    COMMON_TAGS,
    COMMON_RESPONSES,
)
