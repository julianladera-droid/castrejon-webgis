#!/usr/bin/env python3
"""Gate M0 offline: stdlib Python + Node; no descarga ni instala nada."""
import json
from html.parser import HTMLParser
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
VOID = set('area base br col embed hr img input link meta param source track wbr'.split())
OL_JS = 'https://cdn.jsdelivr.net/npm/ol@10.6.1/dist/ol.js'
OL_CSS = 'https://cdn.jsdelivr.net/npm/ol@10.6.1/ol.css'


def require(condition, message):
    if not condition:
        raise ValueError(message)


class Page(HTMLParser):
    """Estructura básica de este HTML explícito; no es un validador W3C completo."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.ids, self.scripts, self.handlers = [], {}, [], []
        self.tags, self.styles, self.links, self.labels = [], [], [], []
        self.doctype = False

    def handle_decl(self, decl):
        require(decl.lower() == 'doctype html', 'HTML: doctype debe ser HTML5')
        self.doctype = True

    def handle_starttag(self, tag, attrs):
        keys = [key for key, _ in attrs]
        require(len(keys) == len(set(keys)), f'HTML: atributos duplicados en {tag}')
        attrs = dict(attrs)
        self.tags.append(tag)
        if 'id' in attrs:
            require(attrs['id'] and attrs['id'] not in self.ids, 'HTML: id vacío o duplicado')
            self.ids[attrs['id']] = attrs
        for key, value in attrs.items():
            if key.startswith('on'):
                self.handlers.append(value or '')
        if tag == 'label' and 'for' in attrs:
            self.labels.append(attrs['for'])
        if tag == 'link':
            self.links.append(attrs.get('href'))
        if tag == 'script':
            require(attrs.get('type', '') in ('', 'text/javascript', 'application/javascript'),
                    'HTML: nuevo tipo de script; adaptar el gate antes de publicarlo')
            self.scripts.append({'src': attrs.get('src'), 'code': ''})
        if tag == 'style':
            self.styles.append('')
        if tag not in VOID:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        require(tag in VOID, f'HTML: cierre autocontenido no válido para {tag}')
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        require(self.stack and self.stack[-1] == tag, f'HTML: cierre desordenado de {tag}')
        self.stack.pop()

    def handle_data(self, data):
        if self.stack and self.stack[-1] == 'script':
            self.scripts[-1]['code'] += data
        if self.stack and self.stack[-1] == 'style':
            self.styles[-1] += data


def check_secrets():
    # Se inspecciona el contenido actual de TODOS los archivos versionados, no el historial.
    paths = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
    patterns = {
        'clave privada': r'-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----',
        'token conocido': r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|AKIA[A-Z0-9]{16}|ASIA[A-Z0-9]{16}|AIza[\w-]{35}|xox[baprs]-[\w-]{20,}|sk-(?:proj-)?[\w-]{32,})\b',
        'credencial en URL': r'https?://[^\s/<>\'"]+:[^\s/<>\'"]+@',
        'secreto literal': r'''(?ix)["']?\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|token|password|passwd|client[_-]?secret|secret[_-]?key)\b["']?\s*[:=]\s*["'][^\s"'{}$]{8,}["']''',
        'secreto en query': r'(?i)[?&](?:api[_-]?key|access[_-]?token|token|password|secret)=[A-Za-z0-9_+./%-]{8,}',
        'secreto de entorno': r'(?im)^\s*(?:[A-Z0-9_]*(?:TOKEN|PASSWORD|SECRET|API_KEY))\s*=\s*[A-Za-z0-9_+./-]{8,}\s*$',
    }
    for name in filter(None, paths):
        path = ROOT / name
        require(not path.is_symlink(), f'Archivo simbólico no previsto: {name}')
        content = path.read_bytes().decode('utf-8', errors='replace')
        for kind, pattern in patterns.items():
            # Nunca imprimir el valor coincidente (tampoco contexto ni trazas).
            require(not re.search(pattern, content), f'Secreto evidente ({kind}) en {name}')
    print('OK: patrones de secretos evidentes en archivos versionados', flush=True)


def main():
    check_secrets()
    page = Page()
    page.feed((ROOT / 'index.html').read_text(encoding='utf-8'))
    page.close()
    require(page.doctype and not page.stack, 'HTML: doctype ausente o elementos sin cerrar')
    for tag in ('html', 'head', 'body', 'title'):
        require(page.tags.count(tag) == 1, f'HTML: debe existir un único {tag}')
    require('map' in page.ids, 'HTML: falta el destino map')
    require(all(label in page.ids for label in page.labels), 'HTML: label apunta a id inexistente')
    require(OL_CSS in page.links, 'HTML: falta CSS OpenLayers previsto')
    require(len(page.scripts) >= 2 and page.scripts[0]['src'] == OL_JS,
            'HTML: OpenLayers debe preceder al código del visor')
    require([s['src'] for s in page.scripts if s['src']] == [OL_JS],
            'HTML: script externo nuevo; incorporarlo expresamente al gate')
    require(all(not s['code'].strip() for s in page.scripts if s['src']),
            'HTML: código inline ignorado por un atributo src')
    # No evaluamos CSS ni hacemos layout: sólo una ocultación directa reconocible.
    css = re.sub(r'/\*.*?\*/', '', '\n'.join(page.styles), flags=re.S)
    for selector, body in re.findall(r'([^{}]+)\{([^{}]*)\}', css):
        if re.search(r'ol-attribution', selector, re.I):
            require(not re.search(r'(?:display\s*:\s*none|visibility\s*:\s*hidden|opacity\s*:\s*0(?:\D|$))', body, re.I),
                    'Atribuciones: ocultación CSS directa')
    print('OK: estructura HTML básica, ids y scripts previstos', flush=True)
    payload = {'scripts': [s['code'] for s in page.scripts if not s['src']],
               'handlers': page.handlers, 'ids': page.ids}
    result = subprocess.run(['node', str(ROOT / 'scripts/check-map.cjs')],
                            input=json.dumps(payload), text=True, cwd=ROOT, timeout=15)
    require(result.returncode == 0, 'JavaScript/contrato cartográfico: gate rechazado')
    print('PASS: gate offline; pruebas visuales/remotas pendientes del checklist manual')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(f'FAIL: {error}', file=sys.stderr)
        sys.exit(1)
