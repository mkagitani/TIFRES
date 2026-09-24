"""Static inventory: never imports or executes the reduction scripts."""
import ast
import hashlib
import json
from pathlib import Path


def inventory(directory):
    result = {}
    for path in sorted(Path(directory).glob('*.py')):
        source = path.read_text(encoding='utf-8-sig')
        tree = ast.parse(source)
        functions, imports, config, fields, interactions, io = [], set(), set(), set(), [], []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(f'{node.name}({ast.unparse(node.args)}) [line {node.lineno}]')
            if isinstance(node, ast.Import):
                imports.update(a.name for a in node.names)
            if isinstance(node, ast.ImportFrom):
                imports.add(node.module or '')
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                if node.value.id == 'cfg': config.add(node.attr)
                if node.value.id == 'row': fields.add(node.attr)
            if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute) and node.value.attr in ('at', 'loc'):
                fields.update(n.value for n in ast.walk(node.slice) if isinstance(n, ast.Constant) and isinstance(n.value, str))
            if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id in ('row', 'df'):
                fields.update(n.value for n in ast.walk(node.slice) if isinstance(n, ast.Constant) and isinstance(n.value, str))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) and node.func.value.id == 'row' and node.func.attr == 'get':
                if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                    fields.add(node.args[0].value)
            if isinstance(node, ast.Call):
                call = ast.unparse(node.func)
                if call == 'input' or call.endswith(('.show', '.pause', '.use', '.wm_geometry')):
                    interactions.append(f'{node.lineno}: {ast.unparse(node)}')
                if call.endswith(('.open', '.writeto', '.loadtxt', '.read_csv', '.to_csv', '.copy2', '.savefig', '.replace')):
                    io.append(f'{node.lineno}: {ast.unparse(node)}')
        result[path.name] = dict(sha256=hashlib.sha256(path.read_bytes()).hexdigest(), functions=functions,
                                 imports=sorted(imports), cfg=sorted(config), csv_fields=sorted(fields),
                                 interactive_calls=interactions, io_calls=io)
    return result


if __name__ == '__main__':
    import sys
    print(json.dumps(inventory(sys.argv[1]), indent=2, ensure_ascii=False))
