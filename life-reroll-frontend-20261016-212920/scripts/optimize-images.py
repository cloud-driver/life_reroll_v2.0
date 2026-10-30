"""Offline asset build. Requires Pillow; the deployed server does not.

Original illustrations remain under source-assets, outside the public web root.
No crop or composition change; event images retain up to 1440 px (2x UI width).
"""

from pathlib import Path
import json
import shutil
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / 'public'
SOURCE = ROOT / 'source-assets'
files = list((PUBLIC / 'events').glob('*.jpg')) + list((SOURCE / 'events').glob('*.jpg'))
files += [
    PUBLIC / name if (PUBLIC / name).exists() else SOURCE / name
    for name in ['scene-home.png', 'life-reroll-city.png', 'life-reroll-city-panorama.png']
    + [f'car-{v}.png' for v in ('ne', 'nw', 'se', 'sw')]
]
rows = []
for path in sorted(set(files)):
    relative = path.relative_to(PUBLIC if path.is_relative_to(PUBLIC) else SOURCE)
    original = SOURCE / relative
    output = (PUBLIC / relative).with_suffix('.webp')
    original.parent.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    if path != original:
        if not original.exists():
            shutil.copy2(path, original)
    with Image.open(original) as im:
        im = ImageOps.exif_transpose(im)
        if relative.parts[0] == 'events':
            im.thumbnail((1440, 1440), Image.Resampling.LANCZOS)
        lossless = relative.name.startswith('car-')
        im.save(output, 'WEBP', quality=88, method=6, lossless=lossless)
        rows.append(
            {
                'source': str(relative),
                'output': str(output.relative_to(PUBLIC)),
                'before': original.stat().st_size,
                'after': output.stat().st_size,
                'width': im.width,
                'height': im.height,
            }
        )
    if path != original:
        path.unlink()
manifest = json.loads((PUBLIC / 'event-media.json').read_text())
for group in ('events', 'kinds'):
    for asset in manifest.get(group, {}).values():
        optimized = Path(asset['src']).with_suffix('.webp')
        if (PUBLIC / str(optimized).lstrip('/')).exists():
            asset['src'] = str(optimized)
(PUBLIC / 'event-media.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
(ROOT / 'docs/image-optimization.json').write_text(
    json.dumps(
        {'assets': rows, 'before_bytes': sum(x['before'] for x in rows), 'after_bytes': sum(x['after'] for x in rows)},
        indent=2,
    )
    + '\n'
)
print(f'{len(rows)} assets: {sum(x["before"] for x in rows):,} -> {sum(x["after"] for x in rows):,} bytes')
