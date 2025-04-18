#!/usr/bin/env python3
"""
Check each __init__.py to verify it includes either imports or an __all__ definition.
"""
import os

def analyze_init(path):
    text = open(path, encoding='utf-8').read()
    has_all = '__all__' in text
    has_import = 'import ' in text or 'from .' in text
    return has_all, has_import

issues = []
print("Checking __init__.py files under project root...\n")
for root, dirs, files in os.walk('.'):
    if '__init__.py' in files:
        path = os.path.join(root, '__init__.py')
        has_all, has_import = analyze_init(path)
        status = []
        if has_all: status.append('__all__')
        if has_import: status.append('imports')
        if not status:
            issues.append(path)
            status_str = 'none'
        else:
            status_str = ', '.join(status)
        print(f"{path}: {status_str}")

if issues:
    print("\nPotential issues detected in: ")
    for p in issues:
        print(f"  - {p}")
else:
    print("\nAll __init__.py files contain either imports or __all__.")
