from pathlib import Path
import tarfile

base=Path(__file__).resolve().parent
assert not (base/'sample').exists(), 'preserve previous sample'
with tarfile.open(base/'generated.tgz','r:gz') as tar:
    for item in tar.getmembers():
        target=(base/item.name).resolve()
        assert item.isfile() and target.is_relative_to(base.resolve())
        assert item.name.startswith('sample/') and '..' not in Path(item.name).parts
    tar.extractall(base)
print('Piano ballad retrieved without the original image or WAV intermediates')
