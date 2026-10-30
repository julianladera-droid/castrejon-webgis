"""Package the canonical WordPress plugin plus shared mobile assets, without secrets."""
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'artifacts' / 'castrejon-averias-1.1.0.zip'


def main():
    OUTPUT.parent.mkdir(exist_ok=True)
    sources = [(ROOT / 'wordpress/castrejon-averias', 'castrejon-averias'), (ROOT / 'averias', 'castrejon-averias/app')]
    with zipfile.ZipFile(OUTPUT, 'w', zipfile.ZIP_DEFLATED) as archive:
        for root, prefix in sources:
            for path in sorted(root.rglob('*')):
                if path.is_file() and path.name not in ('map-layer.js', 'map-layer.css'):
                    archive.write(path, prefix + '/' + path.relative_to(root).as_posix())
    print(OUTPUT)


if __name__ == '__main__':
    main()
