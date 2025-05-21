"""
Herramientas de propósito general para los agentes.
"""

import json
import logging
import math
import ast
import operator
from datetime import datetime
from typing import Dict, Any, Optional, List, Union

from langchain_core.tools import BaseTool
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
    """Herramienta para realizar cálculos matemáticos de forma segura."""
    
    name = "calculator"
    description = "Realiza cálculos matemáticos. Proporciona una expresión matemática para evaluarla. Soporta operaciones comunes como suma, resta, multiplicación, división, potencias, raíces cuadradas, seno, coseno, etc."
    
    # Operadores permitidos y seguros
    _OPERATORS = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Pow: operator.pow,
        ast.BitXor: operator.xor,
        ast.USub: operator.neg,
        ast.Mod: operator.mod,
        # Comparaciones
        ast.Lt: operator.lt,
        ast.Gt: operator.gt,
        ast.LtE: operator.le,
        ast.GtE: operator.ge,
        ast.Eq: operator.eq,
        ast.NotEq: operator.ne,
    }
    
    # Funciones matemáticas seguras disponibles
    _MATH_FUNCTIONS = {
        'sin': math.sin,
        'cos': math.cos,
        'tan': math.tan,
        'sqrt': math.sqrt,
        'log': math.log,
        'log10': math.log10,
        'abs': abs,
        'round': round,
        'ceil': math.ceil,
        'floor': math.floor,
        'exp': math.exp,
        'pi': math.pi,
        'e': math.e
    }
    
    def _safe_eval(self, node):
        """Evalúa un nodo AST de forma segura."""
        # Evaluación de constantes como números
        if isinstance(node, ast.Constant):
            return node.value
        
        # Operaciones binarias como suma, resta, etc.
        elif isinstance(node, ast.BinOp):
            if type(node.op) not in self._OPERATORS:
                raise ValueError(f"Operador no soportado: {type(node.op).__name__}")
            
            left = self._safe_eval(node.left)
            right = self._safe_eval(node.right)
            return self._OPERATORS[type(node.op)](left, right)
        
        # Operaciones unarias como -x
        elif isinstance(node, ast.UnaryOp):
            if type(node.op) not in self._OPERATORS:
                raise ValueError(f"Operador unario no soportado: {type(node.op).__name__}")
            
            operand = self._safe_eval(node.operand)
            return self._OPERATORS[type(node.op)](operand)
        
        # Comparaciones como a < b, a == b, etc.
        elif isinstance(node, ast.Compare):
            if len(node.ops) != 1 or len(node.comparators) != 1:
                raise ValueError("Solo se permite una comparación a la vez")
            
            if type(node.ops[0]) not in self._OPERATORS:
                raise ValueError(f"Operador de comparación no soportado: {type(node.ops[0]).__name__}")
            
            left = self._safe_eval(node.left)
            right = self._safe_eval(node.comparators[0])
            return self._OPERATORS[type(node.ops[0])](left, right)
        
        # Llamadas a funciones matemáticas seguras
        elif isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise ValueError("Solo se permiten llamadas a funciones matemáticas predefinidas")
            
            func_name = node.func.id
            if func_name not in self._MATH_FUNCTIONS:
                raise ValueError(f"Función no permitida: {func_name}")
            
            args = [self._safe_eval(arg) for arg in node.args]
            return self._MATH_FUNCTIONS[func_name](*args)
        
        # Nombres especiales como pi, e
        elif isinstance(node, ast.Name):
            if node.id not in self._MATH_FUNCTIONS:
                raise ValueError(f"Variable no permitida: {node.id}")
            return self._MATH_FUNCTIONS[node.id]
        
        # No permitir otros tipos de nodos AST por seguridad
        else:
            raise ValueError(f"Tipo de expresión no soportado: {type(node).__name__}")
    
    @handle_errors(error_type="service", log_traceback=True)
    async def _arun(self, expression: str, **kwargs) -> str:
        """
        Evalúa una expresión matemática de forma segura.
        
        Args:
            expression: Expresión matemática a evaluar
            
        Returns:
            str: Resultado del cálculo
        """
        try:
            # Eliminar espacios en blanco y verificar contenido
            expression = expression.strip()
            if not expression:
                return "Error: Por favor, proporciona una expresión matemática válida."
            
            # Parsear la expresión a AST
            parsed_expr = ast.parse(expression, mode='eval')
            
            # Evaluar de forma segura sin usar eval()
            result = self._safe_eval(parsed_expr.body)
            
            # Formatear resultado
            if isinstance(result, bool):
                return f"Resultado: {result}"
            elif isinstance(result, int):
                return f"Resultado: {result}"
            elif isinstance(result, float):
                # Redondear a 6 decimales para evitar problemas de punto flotante
                formatted_result = round(result, 6)
                # Eliminar ceros innecesarios al final
                if formatted_result == int(formatted_result):
                    return f"Resultado: {int(formatted_result)}"
                return f"Resultado: {formatted_result}"
            else:
                return f"Resultado: {result}"
                
        except SyntaxError as e:
            logger.error(f"Error de sintaxis en la expresión matemática: {str(e)}")
            return f"Error de sintaxis: Por favor, verifica la expresión matemática."
        except (ValueError, TypeError) as e:
            logger.error(f"Error en evaluación matemática: {str(e)}")
            return f"Error: {str(e)}"
        except Exception as e:
            logger.error(f"Error al evaluar expresión matemática: {str(e)}")
            return f"Error al calcular: Expresión no válida o no soportada."


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
