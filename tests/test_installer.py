import importlib.util
from pathlib import Path
import pytest

path=Path(__file__).resolve().parents[1]/'install.py'
spec=importlib.util.spec_from_file_location('defro_installer',path)
installer=importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


def test_installer_writes_only_component_and_preserves_yaml(tmp_path):
    config=tmp_path/'config';config.mkdir()
    yaml=config/'configuration.yaml';yaml.write_text('default_config:\n')
    target,backup=installer.install(config)
    assert backup is None
    assert (target/'manifest.json').is_file() and (target/'catalogue.json').is_file()
    assert yaml.read_text()=='default_config:\n'
    (target/'old_marker.txt').write_text('old component version')
    target,backup=installer.install(config)
    assert (backup/'old_marker.txt').read_text()=='old component version'
    assert not (target/'old_marker.txt').exists()
    assert yaml.read_text()=='default_config:\n'


def test_installer_rejects_download_folder(tmp_path):
    with pytest.raises(ValueError,match='configuration.yaml'):installer.install(tmp_path)
    assert not (tmp_path/'custom_components').exists()


def test_installer_rolls_back_if_new_folder_cannot_be_activated(tmp_path,monkeypatch):
    config=tmp_path/'config';config.mkdir();(config/'configuration.yaml').write_text('original')
    target,_=installer.install(config)
    (target/'old_marker.txt').write_text('must survive')
    original_rename=Path.rename
    def fail_activation(self,target):
        if self.name.startswith('.defro_install_'):raise PermissionError('simulated activation failure')
        return original_rename(self,target)
    monkeypatch.setattr(Path,'rename',fail_activation)
    with pytest.raises(PermissionError):installer.install(config)
    assert (target/'old_marker.txt').read_text()=='must survive'
    assert (config/'configuration.yaml').read_text()=='original'
    assert not list(config.glob('.defro_install_*'))

