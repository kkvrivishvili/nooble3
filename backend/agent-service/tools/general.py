"""
Herramientas de propósito general para los agentes.
"""

import logging
import json
from datetime import datetime
from typing import Dict, Any, List, Optional

from common.context import Context, with_context
from common.errors import handle_errors, ServiceError
from common.tracking import track_token_usage

from config import get_settings
from config.constants import TOKEN_TYPE_LLM, OPERATION_AGENT_QUERY
from tools.base import BaseTool

logger = logging.getLogger(__name__)


class DateTimeTool(BaseTool):
    """Herramienta para obtener la fecha y hora actual."""
    
    name = "get_date_time"
    description = "Obtiene la fecha y hora actual. Útil cuando necesitas saber la fecha, hora, día de la semana o información similar del momento actual."
    
    @handle_errors(error_type="service", log_traceback=True)
    async def _arun(self, **kwargs) -> str:
        """
        Obtiene la fecha y hora actual.
        
        Returns:
            str: Información de fecha y hora actual
        """
        now = datetime.now()
        
        weekday_map = {
            0: "Lunes",
            1: "Martes",
            2: "Miércoles",
            3: "Jueves",
            4: "Viernes", 
            5: "Sábado",
            6: "Domingo"
        }
        
        month_map = {
            1: "Enero",
            2: "Febrero",
            3: "Marzo",
            4: "Abril",
            5: "Mayo",
            6: "Junio",
            7: "Julio",
            8: "Agosto",
            9: "Septiembre",
            10: "Octubre",
            11: "Noviembre",
            12: "Diciembre"
        }
        
        # Obtener nombres en español
        weekday = weekday_map.get(now.weekday(), "Desconocido")
        month = month_map.get(now.month, "Desconocido")
        
        formatted_date = f"{weekday}, {now.day} de {month} de {now.year}"
        formatted_time = now.strftime("%H:%M:%S")
        
        return (
            f"Fecha actual: {formatted_date}\n"
            f"Hora actual: {formatted_time}\n"
            f"Timestamp (UTC): {datetime.utcnow().isoformat()}"
        )


class CalculatorTool(BaseTool):
    """Herramienta para realizar cálculos matemáticos."""
    
    name = "calculator"
    description = "Realiza cálculos matemáticos. Proporciona una expresión matemática para evaluarla. Soporta operaciones comunes como suma, resta, multiplicación, división, potencias, etc."
    
    @handle_errors(error_type="service", log_traceback=True)
    async def _arun(self, expression: str, **kwargs) -> str:
        """
        Evalúa una expresión matemática.
        
        Args:
            expression: Expresión matemática a evaluar
            
        Returns:
            str: Resultado del cálculo
        """
        try:
            # Limitar lo que se puede ejecutar por seguridad
            # Solo permitir caracteres seguros para operaciones matemáticas
            safe_chars = set("0123456789+-*/().% <>!=")
            
            if not all(c in safe_chars for c in expression):
                return "Error: La expresión contiene caracteres no permitidos. Solo se permiten números y operadores básicos (+, -, *, /, (), %, <, >, =, !)."
            
            # Evaluar la expresión de forma segura
            result = eval(expression, {"__builtins__": {}})
            
            return f"Resultado: {result}"
        except Exception as e:
            logger.error(f"Error al evaluar expresión matemática: {str(e)}")
            return f"Error al calcular: {str(e)}"


class FormatJSONTool(BaseTool):
    """Herramienta para formatear y validar JSON."""
    
    name = "format_json"
    description = "Formatea y valida una cadena JSON. Útil para verificar que un JSON es válido y darle formato legible."
    
    @handle_errors(error_type="service", log_traceback=True)
    async def _arun(self, json_string: str, indent: int = 2, **kwargs) -> str:
        """
        Formatea y valida una cadena JSON.
        
        Args:
            json_string: Cadena JSON a formatear
            indent: Nivel de indentación (default: 2)
            
        Returns:
            str: JSON formateado o mensaje de error
        """
        try:
            # Analizar el JSON
            parsed_json = json.loads(json_string)
            
            # Formatear con indentación
            formatted_json = json.dumps(parsed_json, indent=indent, ensure_ascii=False)
            
            return f"JSON válido y formateado:\n\n```json\n{formatted_json}\n```"
        except json.JSONDecodeError as e:
            position = e.pos
            line_no = json_string[:position].count('\n') + 1
            column = position - json_string[:position].rfind('\n')
            
            return f"Error de formato JSON en línea {line_no}, columna {column}: {str(e)}"
        except Exception as e:
            return f"Error al procesar JSON: {str(e)}"
