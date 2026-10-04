from pathlib import Path

import pytest

from deeplabeling.core.paths import folder_label_path, training_label_path


@pytest.mark.parametrize("image, label", [
    ("/d/camA/images/0001.jpg", "/d/camA/labels/0001.txt"),
    ("/d/images/sub/a.jpg", "/d/labels/sub/a.txt"),
    ("/d/images/x/images/a.jpg", "/d/images/x/labels/a.txt"),     # the LAST /images/
    ("/d/frames/a.jpg", "/d/frames/a.txt"),                       # beside it, as training reads
    ("/d/my_images/a.jpg", "/d/my_images/a.txt"),                 # a name, not a folder
    ("/d/v1.2/images/a.b.jpg", "/d/v1.2/labels/a.b.txt"),
])
def test_the_training_rule(image, label):
    assert training_label_path(Path(image)) == Path(label)


def test_an_explicit_label_folder():
    assert folder_label_path(Path("/d/frames/sub/a.jpg"), Path("/l")) == Path("/l/a.txt")
