"""Exercise the first-run installer through its public PowerShell interface."""
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]


class InstallerRegressions(unittest.TestCase):
    def test_dependency_check_reads_the_requested_version_constraints(self):
        with tempfile.TemporaryDirectory(prefix='fluent requirements ') as scratch:
            requirements=Path(scratch)/'requirements.txt'
            requirements.write_text((ROOT/'requirements.txt').read_text('utf-8'),encoding='utf-8')
            command=[sys.executable,str(ROOT/'tools'/'check_dependencies.py'),str(requirements)]
            good=subprocess.run(command,capture_output=True,text=True)
            self.assertEqual(good.returncode,0,good.stdout+good.stderr)
            requirements.write_text('Pillow<1\n',encoding='utf-8')
            wrong=subprocess.run(command,capture_output=True,text=True)
            self.assertNotEqual(wrong.returncode,0,'Installed packages must satisfy this requirements file')

    def test_clean_source_prepares_itself_without_existing_venv_or_generated_skin(self):
        cache=ROOT/'.cache';cache.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='installer clean source ',dir=cache) as scratch:
            project=Path(scratch)/'Fluent Glass source';project.mkdir()
            shutil.copytree(ROOT/'tools',project/'tools')
            shutil.copytree(ROOT/'assets',project/'assets')
            for name in ('requirements.txt','LICENSE','THIRD_PARTY_NOTICES.md'):
                if (ROOT/name).is_file():shutil.copy2(ROOT/name,project/name)
            player=Path(scratch)/'Player with spaces';(player/'Skins').mkdir(parents=True)
            installed_value=os.environ.get('FLUENT_TEST_PLAYER_DIRECTORY')
            config_file=ROOT/'.runtime'/'install.json'
            if not installed_value and config_file.exists():
                installed_value=json.loads(config_file.read_text('utf-8-sig')).get('playerDirectory')
            if not installed_value:self.skipTest('Set FLUENT_TEST_PLAYER_DIRECTORY to an installed PotPlayer x64 directory')
            installed=Path(installed_value)
            for name in ('PotPlayerMini64.exe','PotPlayer64.dll','Skins/Default.dsf'):
                shutil.copy2(installed/name,player/name)
            result=subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass',
                                   '-File',str(project/'tools'/'install.ps1'),
                                   '-PlayerDirectory',str(player),'-PythonExecutable',sys.executable,
                                   '-PrepareOnly','-Json'],capture_output=True,text=True,
                                  encoding='utf-8',errors='replace',timeout=180)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            config_file=project/'.runtime'/'install.json'
            self.assertTrue(config_file.exists(),'First run must save the discovered installation')
            config=json.loads(config_file.read_text('utf-8-sig'))
            self.assertEqual(Path(config['playerDirectory']),player)
            self.assertTrue((project/'.venv'/'Scripts'/'python.exe').is_file())
            self.assertTrue((project/'dist'/'FluentGlass.dsf').is_file())
            self.assertTrue((project/'.runtime'/'Skins'/'FluentGlass.dsf').is_file())
            self.assertFalse(config['restartRequired'])
            ini=project/'.runtime'/'PotPlayerMini64.ini'
            ini.write_text(ini.read_text('utf-16')+'\n[InstallerRegression]\nKeep=required\n',encoding='utf-16')
            preserved=ini.read_bytes()
            skin_mtime=(project/'dist'/'FluentGlass.dsf').stat().st_mtime_ns
            repeated_command=['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass',
                              '-File',str(project/'tools'/'preview.ps1'),'-PrepareOnly','-Json']
            repeated=subprocess.run(repeated_command,capture_output=True,text=True,
                                    encoding='utf-8',errors='replace',timeout=60)
            self.assertEqual(repeated.returncode,0,repeated.stdout+repeated.stderr)
            repeated_config=json.loads(config_file.read_text('utf-8-sig'))
            self.assertEqual(Path(repeated_config['playerDirectory']),player,
                             'A later run must discover the saved installation without an explicit path')
            self.assertFalse(repeated_config['buildPerformed'],'An unchanged source checkout must reuse its skin')
            self.assertEqual((project/'dist'/'FluentGlass.dsf').stat().st_mtime_ns,skin_mtime)
            self.assertEqual(ini.read_bytes(),preserved,'Repeated setup must preserve custom player settings')
            changed_asset=project/'assets'/'search.svg'
            changed_asset.write_text(changed_asset.read_text('utf-8')+'\n',encoding='utf-8')
            changed=subprocess.run(repeated_command,capture_output=True,text=True,
                                   encoding='utf-8',errors='replace',timeout=60)
            self.assertEqual(changed.returncode,0,changed.stdout+changed.stderr)
            changed_config=json.loads(config_file.read_text('utf-8-sig'))
            self.assertTrue(changed_config['buildPerformed'],'Asset content changes must invalidate the local skin')
            self.assertNotEqual(changed_config['buildFingerprint'],repeated_config['buildFingerprint'])
            self.assertEqual(ini.read_bytes(),preserved)

    def test_invalid_explicit_player_directory_is_actionable(self):
        with tempfile.TemporaryDirectory(prefix='fluent installer ') as scratch:
            missing=Path(scratch)/'missing player'
            result=subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass',
                                   '-File',str(ROOT/'tools'/'install.ps1'),
                                   '-PlayerDirectory',str(missing),'-PrepareOnly','-Json'],
                                  capture_output=True,text=True,encoding='utf-8',errors='replace')
            self.assertNotEqual(result.returncode,0)
            self.assertIn('PotPlayerMini64.exe',result.stdout+result.stderr,
                          'An invalid explicit directory must explain what installation is required')


if __name__=='__main__':unittest.main(verbosity=2)
