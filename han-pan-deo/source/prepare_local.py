from pathlib import Path
import shutil
from xml.etree import ElementTree as ET

root = Path(__file__).resolve().parent
target = root / 'sample'
if target.exists():
    raise FileExistsError('preserve existing reviewed local copy')
shutil.copytree(root / 'rap-rematch-20261028', target)
path = target / 'rap' / 'score.musicxml'
tree = ET.parse(path).getroot()
part = tree.find('part-list/score-part')
part.find('midi-instrument/midi-program').text = '116'
part.find('midi-instrument/midi-channel').text = '6'
for field in tree.findall('identification/miscellaneous/miscellaneous-field'):
    if field.get('name') == 'genre':
        field.text = 'rap_piano_backing'
path.write_text('<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(tree, encoding='unicode'), encoding='utf-8')
print('Prepared local rap and piano score files')
