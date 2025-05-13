import time
import logging
from typing import List, Dict, Any, Optional

from langchain_core.callbacks import BaseCallbackHandler
from common.llm.token_counters import count_tokens

logger = logging.getLogger(__name__)

class AgentCallbackHandler(BaseCallbackHandler):
    """Callback handler para capturar acciones y resultados del agente."""
    
    def __init__(self):
        self.action_logs = []
        self.sources = []
        
    def on_tool_start(self, serialized, input_str, **kwargs):
        """Registra cuando se inicia una herramienta."""
        self.action_logs.append({
            "type": "tool_start",
            "tool": serialized.get("name", "unknown_tool"),
            "input": input_str,
            "timestamp": time.time()
        })
    
    def on_tool_end(self, output, **kwargs):
        """Registra cuando finaliza una herramienta."""
        self.action_logs.append({
            "type": "tool_end",
            "output": str(output),
            "timestamp": time.time()
        })
        
        # Intentar extraer fuentes del texto de respuesta si contiene "Fuentes:"
        if isinstance(output, str) and "Fuentes:" in output:
            try:
                sources_text = output.split("Fuentes:")[1]
                sources_lines = sources_text.split("\n")
                for line in sources_lines:
                    if line.strip() and "[" in line and "]" in line:
                        self.sources.append({
                            "text": line.split("]:")[1].strip() if "]:" in line else line,
                            "metadata": {"source": line.split("]")[0].replace("[", "").strip()}
                        })
            except Exception as e:
                logger.debug(f"Error extrayendo fuentes: {str(e)}")
    
    def on_tool_error(self, error, **kwargs):
        """Registra errores de herramientas."""
        self.action_logs.append({
            "type": "tool_error",
            "error": str(error),
            "timestamp": time.time()
        })
    
    def on_chain_start(self, serialized, inputs, **kwargs):
        """Registra cuando se inicia una cadena."""
        self.action_logs.append({
            "type": "chain_start",
            "inputs": str(inputs),
            "timestamp": time.time()
        })
        
    def on_chain_end(self, outputs, **kwargs):
        """Registra cuando finaliza una cadena."""
        self.action_logs.append({
            "type": "chain_end",
            "outputs": str(outputs),
            "timestamp": time.time()
        })
    
    def get_tools_used(self) -> List[str]:
        """Retorna una lista de herramientas únicas utilizadas."""
        tools = [log["tool"] for log in self.action_logs if log["type"] == "tool_start"]
        return list(set(tools))
    
    def get_thinking_steps(self) -> str:
        """Retorna un resumen de los pasos de pensamiento."""
        steps = []
        for log in self.action_logs:
            if log["type"] == "tool_start":
                steps.append(f"Pensando: Voy a usar {log['tool']} con input: {log['input']}")
            elif log["type"] == "tool_end":
                steps.append(f"Resultado: {log['output']}")
            elif log["type"] == "tool_error":
                steps.append(f"Error: {log['error']}")
        return "\n".join(steps)
    
    def get_sources(self) -> List[Dict[str, Any]]:
        """Retorna las fuentes extraídas."""
        return self.sources


class TokenCountingHandler(BaseCallbackHandler):
    """Callback handler para contar tokens de entrada y salida con precisión."""
    
    def __init__(self):
        super().__init__()
        self.input_tokens = 0
        self.output_tokens = 0
        self._prompts = []
    
    def on_llm_start(self, serialized, prompts, **kwargs):
        """Cuenta tokens de entrada al iniciar el LLM."""
        self._prompts = prompts
        # Contar tokens de entrada usando la función centralizada
        self.input_tokens = sum(count_tokens(p) for p in prompts)
    
    def on_llm_new_token(self, token: str, **kwargs):
        """Cuenta cada token de salida."""
        # Incrementa contador por cada token generado
        self.output_tokens += 1
    
    def get_total_tokens(self):
        """Retorna el total de tokens utilizados."""
        return self.input_tokens + self.output_tokens
    
    def get_counts(self):
        """Retorna un diccionario con el conteo de tokens."""
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.input_tokens + self.output_tokens
        }

class StreamingCallbackHandler(BaseCallbackHandler):
    """Manejador de callback para streaming de respuestas."""
    
    def __init__(self):
        super().__init__()
        self.tokens = []
        self.tool_outputs = []
        self.sources = []
    
    def on_llm_new_token(self, token: str, **kwargs):
        """Captura un nuevo token generado."""
        self.tokens.append(token)
    
    def on_tool_end(self, output: str, **kwargs):
        """Captura el resultado de una herramienta."""
        self.tool_outputs.append(output)
        
        # Intentar extraer fuentes como en el handler anterior
        if isinstance(output, str) and "Fuentes:" in output:
            try:
                sources_text = output.split("Fuentes:")[1]
                sources_lines = sources_text.split("\n")
                for line in sources_lines:
                    if line.strip() and "[" in line and "]" in line:
                        self.sources.append({
                            "text": line.split("]:")[1].strip() if "]:" in line else line,
                            "metadata": {"source": line.split("]")[0].replace("[", "").strip()}
                        })
            except Exception as e:
                logger.debug(f"Error extrayendo fuentes: {str(e)}")
    
    def get_tokens(self):
        """Obtiene todos los tokens capturados."""
        return self.tokens
    
    def get_tool_outputs(self):
        """Obtiene todas las salidas de herramientas."""
        return self.tool_outputs
    
    def get_thinking_steps(self):
        """Obtiene pasos de pensamiento (implementado para compatibilidad)."""
        if not self.tool_outputs:
            return ""
        return "\n".join([f"Resultado: {output}" for output in self.tool_outputs])
    
    def get_tools_used(self):
        """Obtiene herramientas usadas (implementado para compatibilidad)."""
        return [] if not self.tool_outputs else ["search"]
    
    def get_sources(self):
        """Retorna las fuentes extraídas."""
        return self.sources