"""
Sistema centralizado de alertas y notificaciones para tracking de tokens.

Este módulo proporciona una interfaz unificada para registrar
y enviar alertas relacionadas con tracking y reconciliación.
"""

import enum
import json
import logging
import asyncio
from typing import Dict, Any, Optional, List, Union

from ..config import get_settings
from ..utils.http import call_service

logger = logging.getLogger(__name__)

class AlertLevel(enum.Enum):
    """Niveles de alerta para el sistema de monitorización."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

async def register_alert(
    title: str,
    message: str,
    level: AlertLevel = AlertLevel.INFO,
    component: str = "tracking",
    metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Registra una alerta en el sistema de monitorización.
    
    Esta función envía la alerta a todos los canales configurados,
    como logs, métricas, Slack, email, etc.
    
    Args:
        title: Título breve y descriptivo de la alerta
        message: Mensaje detallado de la alerta
        level: Nivel de severidad (INFO, WARNING, ERROR, CRITICAL)
        component: Componente del sistema que genera la alerta
        metadata: Datos adicionales relacionados con la alerta
        
    Returns:
        Dict con información sobre la alerta registrada
    """
    settings = get_settings()
    
    # 1. Siempre registrar en logs
    log_alert(title, message, level, component, metadata)
    
    # 2. Enviar notificaciones para alertas importantes
    if level in [AlertLevel.ERROR, AlertLevel.CRITICAL] and settings.alert_notifications_enabled:
        await send_notifications(title, message, level, component, metadata)
    
    return {
        "title": title,
        "message": message,
        "level": level.value,
        "component": component,
        "timestamp": asyncio.get_event_loop().time()
    }

def log_alert(
    title: str,
    message: str,
    level: AlertLevel,
    component: str,
    metadata: Optional[Dict[str, Any]] = None
) -> None:
    """
    Registra una alerta en los logs del sistema.
    
    Args:
        title: Título de la alerta
        message: Mensaje detallado
        level: Nivel de severidad
        component: Componente del sistema
        metadata: Datos adicionales
    """
    log_message = f"[ALERT][{component}] {title}: {message}"
    extra = {
        "alert": True,
        "component": component,
        "level": level.value
    }
    
    if metadata:
        extra.update({"metadata": json.dumps(metadata)})
    
    if level == AlertLevel.INFO:
        logger.info(log_message, extra=extra)
    elif level == AlertLevel.WARNING:
        logger.warning(log_message, extra=extra)
    elif level == AlertLevel.ERROR:
        logger.error(log_message, extra=extra)
    elif level == AlertLevel.CRITICAL:
        logger.critical(log_message, extra=extra)

async def send_notifications(
    title: str,
    message: str,
    level: AlertLevel,
    component: str,
    metadata: Optional[Dict[str, Any]] = None
) -> None:
    """
    Envía notificaciones para alertas importantes.
    
    Esta función puede enviar emails, mensajes a Slack, SMS,
    u otros canales según la configuración.
    
    Args:
        title: Título de la alerta
        message: Mensaje detallado
        level: Nivel de severidad
        component: Componente del sistema
        metadata: Datos adicionales
    """
    settings = get_settings()
    
    # Solo enviar notificaciones para errores y críticos
    if level not in [AlertLevel.ERROR, AlertLevel.CRITICAL]:
        return
    
    try:
        # Comprobar si están habilitadas las notificaciones
        if not settings.alert_notifications_enabled:
            logger.debug("Notificaciones de alertas deshabilitadas por configuración")
            return
            
        # Ejemplo con Slack
        if settings.slack_webhook_url:
            await send_slack_notification(
                title=title,
                message=message,
                level=level,
                component=component,
                metadata=metadata
            )
            
    except Exception as e:
        logger.error(f"Error enviando notificaciones para alerta: {str(e)}", exc_info=True)

async def send_slack_notification(
    title: str,
    message: str,
    level: AlertLevel,
    component: str,
    metadata: Optional[Dict[str, Any]] = None
) -> None:
    """
    Envía una notificación a Slack.
    
    Args:
        title: Título de la alerta
        message: Mensaje detallado
        level: Nivel de severidad
        component: Componente del sistema
        metadata: Datos adicionales
    """
    settings = get_settings()
    
    # Verificar que el webhook esté configurado
    if not settings.slack_webhook_url:
        logger.debug("No se envió notificación a Slack: webhook no configurado")
        return
        
    # Crear payload para Slack
    color = {
        AlertLevel.INFO: "#36a64f",  # verde
        AlertLevel.WARNING: "#ffcc00",  # amarillo
        AlertLevel.ERROR: "#ff9900",  # naranja
        AlertLevel.CRITICAL: "#ff0000"  # rojo
    }.get(level, "#36a64f")
    
    payload = {
        "attachments": [{
            "fallback": f"{title}: {message}",
            "color": color,
            "title": f"[{level.value.upper()}][{component}] {title}",
            "text": message,
            "fields": []
        }]
    }
    
    # Añadir metadata como campos
    if metadata:
        for key, value in metadata.items():
            if isinstance(value, (dict, list)):
                payload["attachments"][0]["fields"].append({
                    "title": key,
                    "value": f"```{json.dumps(value, indent=2)}```",
                    "short": False
                })
            else:
                payload["attachments"][0]["fields"].append({
                    "title": key,
                    "value": str(value),
                    "short": True
                })
    
    # Usar el estándar call_service si está disponible, o directo
    try:
        # El webhook de Slack es independiente del contexto de tenant/agent
        await call_service(
            url=settings.slack_webhook_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            operation_type="notification",
            use_cache=False,
            max_retries=2
        )
        logger.debug(f"Notificación enviada a Slack: {title}")
    except Exception as e:
        logger.error(f"Error enviando notificación a Slack: {str(e)}", exc_info=True)
