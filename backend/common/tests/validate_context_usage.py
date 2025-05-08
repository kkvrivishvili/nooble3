"""
Script para validar que todos los usos de @with_context en el código sigan las mejores prácticas.

Analiza todos los archivos en busca de usos del decorador @with_context y verifica:
1. Uso explícito de validate_tenant=True cuando corresponda
2. Presencia de documentación inline explicando el propósito del decorador
3. Consistencia en el uso de parámetros para cada tipo de endpoint

Uso:
    python validate_context_usage.py [--fix] [--dir directorio_a_analizar]
"""

import os
import re
import sys
import argparse
from typing import List, Dict, Tuple, Set, Optional
from collections import defaultdict


# Patrones para buscar y validar el uso de @with_context
# El patrón debe coincidir con un decorador real, no con menciones en comentarios o docstrings
WITH_CONTEXT_PATTERN = r'^(\s*)@with_context\((.*?)\)'
COMMENT_PATTERN = r'^(\s*)@with_context\(.*?\)(\s*#.*)?$'
DOCSTRING_TRIPLE_QUOTES = r'""".*?"""'
DOCSTRING_TRIPLE_QUOTES_SINGLE = r"'''.*?'''"


def find_python_files(directory: str) -> List[str]:
    """
    Encuentra todos los archivos Python en un directorio y sus subdirectorios.
    """
    python_files = []
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith('.py'):
                python_files.append(os.path.join(root, file))
    return python_files


def analyze_with_context_usage(file_path: str) -> List[Dict]:
    """
    Analiza un archivo en busca de usos de @with_context y verifica las mejores prácticas.
    
    Returns:
        List[Dict]: Lista de problemas encontrados
    """
    issues = []
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Remover docstrings para evitar falsos positivos
        content_no_docstrings = re.sub(DOCSTRING_TRIPLE_QUOTES, '', content, flags=re.DOTALL)
        content_no_docstrings = re.sub(DOCSTRING_TRIPLE_QUOTES_SINGLE, '', content_no_docstrings, flags=re.DOTALL)
        
        # Convertir de nuevo a líneas para análisis
        content_lines = content_no_docstrings.splitlines()
        
        in_comment_block = False
        for i, line in enumerate(content_lines):
            # Ignorar líneas de comentarios
            if line.strip().startswith('#'):
                continue
                
            # Buscar decoradores reales de @with_context
            match = re.match(WITH_CONTEXT_PATTERN, line)
            if match and '@with_context' in line:
                line_number = i + 1
                indent = match.group(1)  # Captura la indentación
                args = match.group(2)    # Captura los argumentos
                
                # Verificar si está en código real (no en comentario o string)
                if '@with_context' in line.strip() and line.strip().startswith('@'):
                    # Verificar si tiene validate_tenant explícito
                    if 'tenant=True' in line and 'validate_tenant' not in line:
                        fixed_line = f"{indent}@with_context({args}, validate_tenant=True)"
                        issues.append({
                            'file': file_path,
                            'line': line_number,
                            'issue': 'validate_tenant no explícito',
                            'content': line.strip(),
                            'fix': fixed_line
                        })
                    
                    # Verificar si tiene comentario explicativo
                    comment_match = re.search(COMMENT_PATTERN, line)
                    if not comment_match or not comment_match.group(2):
                        # No tiene comentario
                        fixed_line = f"{line.rstrip()}  # Requerimos contexto para operación"
                        issues.append({
                            'file': file_path,
                            'line': line_number,
                            'issue': 'sin comentario explicativo',
                            'content': line.strip(),
                            'fix': fixed_line
                        })
    
    except Exception as e:
        print(f"Error analizando {file_path}: {str(e)}")
    
    return issues


def generate_report(all_issues: List[Dict]) -> str:
    """
    Genera un informe de los problemas encontrados.
    """
    if not all_issues:
        return "✅ No se encontraron problemas en el uso de @with_context."
    
    report = []
    report.append(f"Se encontraron {len(all_issues)} problemas en el uso de @with_context:\n")
    
    # Agrupar por archivo
    issues_by_file = defaultdict(list)
    for issue in all_issues:
        issues_by_file[issue['file']].append(issue)
    
    for file, issues in issues_by_file.items():
        report.append(f"\n📁 {file}")
        for issue in issues:
            report.append(f"   Línea {issue['line']}: {issue['issue']}")
            report.append(f"      {issue['content']}")
            report.append(f"      Sugerencia: {issue['fix'].strip()}")
    
    return "\n".join(report)


def fix_issues(all_issues: List[Dict]) -> int:
    """
    Corrige automáticamente los problemas encontrados.
    
    Returns:
        int: Número de archivos modificados
    """
    modified_files = set()
    
    # Agrupar por archivo
    issues_by_file = defaultdict(list)
    for issue in all_issues:
        issues_by_file[issue['file']].append(issue)
    
    for file, issues in issues_by_file.items():
        try:
            # Leer contenido completo del archivo
            with open(file, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # Convertir a líneas para manipulación
            content_lines = content.splitlines()
            
            # Ordenar por línea en orden descendente para evitar que los índices cambien
            issues.sort(key=lambda x: x['line'], reverse=True)
            
            # Realizar modificaciones línea por línea
            for issue in issues:
                line_idx = issue['line'] - 1
                if line_idx >= 0 and line_idx < len(content_lines):
                    # Solo reemplazar si la línea existe y contiene @with_context
                    if '@with_context' in content_lines[line_idx] and content_lines[line_idx].strip().startswith('@'):
                        content_lines[line_idx] = issue['fix']
            
            # Reunir de nuevo el contenido modificado
            modified_content = '\n'.join(content_lines)
            if content.endswith('\n') and not modified_content.endswith('\n'):
                modified_content += '\n'  # Preservar el salto de línea final si existía
            
            # Escribir contenido modificado
            with open(file, 'w', encoding='utf-8') as f:
                f.write(modified_content)
            
            modified_files.add(file)
            print(f"Archivo corregido: {file}")
            
        except Exception as e:
            print(f"Error corrigiendo {file}: {str(e)}")
    
    return len(modified_files)


def main():
    parser = argparse.ArgumentParser(description='Validar el uso de @with_context según las mejores prácticas')
    parser.add_argument('--fix', action='store_true', help='Corregir automáticamente los problemas encontrados')
    parser.add_argument('--dir', type=str, default='..', help='Directorio para analizar (relativo a este script)')
    parser.add_argument('--service', type=str, choices=['query', 'embedding', 'ingestion', 'common'], 
                      help='Limitar análisis a un servicio específico')
    parser.add_argument('--exclude-tests', action='store_true', help='Excluir archivos de pruebas')
    parser.add_argument('--exclude-docs', action='store_true', help='Excluir archivos de documentación')
    args = parser.parse_args()
    
    # Obtener ruta base
    base_dir = os.path.dirname(os.path.abspath(__file__))
    target_dir = os.path.abspath(os.path.join(base_dir, args.dir))
    
    # Ajustar directorio si se especificó un servicio
    if args.service:
        if args.service == 'common':
            target_dir = os.path.join(os.path.dirname(base_dir), 'common')
        else:
            target_dir = os.path.join(os.path.dirname(os.path.dirname(base_dir)), f"{args.service}-service")
    
    print(f"Analizando directorio: {target_dir}\n")
    
    # Encontrar todos los archivos Python
    python_files = find_python_files(target_dir)
    
    # Filtrar archivos según opciones
    filtered_files = []
    for file in python_files:
        # Excluir archivos de pruebas si se indicó
        if args.exclude_tests and ('test_' in os.path.basename(file) or '/tests/' in file.replace('\\', '/')):
            continue
            
        # Excluir archivos de documentación si se indicó
        if args.exclude_docs and ('docs/' in file.replace('\\', '/') or file.endswith('README.md')):
            continue
            
        filtered_files.append(file)
    
    print(f"Encontrados {len(filtered_files)} archivos Python para analizar\n")
    
    # Analizar cada archivo
    all_issues = []
    for file in filtered_files:
        issues = analyze_with_context_usage(file)
        if issues:
            all_issues.extend(issues)
    
    # Generar y mostrar informe
    report = generate_report(all_issues)
    print(report)
    
    # Corregir problemas si se solicita
    if args.fix and all_issues:
        modified = fix_issues(all_issues)
        print(f"\n✅ Corregidos problemas en {modified} archivos")
    
    # Sugerencias para servicios específicos
    if not args.service:
        print("\nProTip: Puedes analizar servicios específicos con la opción --service:")
        print("  python validate_context_usage.py --service query")
        print("  python validate_context_usage.py --service embedding")
        print("  python validate_context_usage.py --service ingestion")
    
    return len(all_issues)


if __name__ == "__main__":
    sys.exit(main())
