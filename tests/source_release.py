"""Public source ZIP must exclude locally derived PotPlayer content and history."""
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parents[1]


class SourceRelease(unittest.TestCase):
    def test_source_archive_contains_licenses_and_original_sources_only(self):
        with tempfile.TemporaryDirectory(prefix='Fluent release ') as folder:
            output=Path(folder)/'source.zip'
            run=subprocess.run([sys.executable,str(ROOT/'tools'/'package_source.py'),
                                '--output',str(output)],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
            with ZipFile(output) as archive:
                names={name.removeprefix('FluentGlass/') for name in archive.namelist()}
                required={'README.md','LICENSE','THIRD_PARTY_NOTICES.md','.gitattributes','tools/build.py',
                          'tools/install.ps1','tools/install_helpers.ps1','tools/check_dependencies.py',
                          '安装皮肤.cmd','预览皮肤.cmd',
                          'assets/logo/glass-orbit.svg','assets/search.svg',
                          'assets/lucide/LICENSE','source-manifest.json'}
                self.assertTrue(required<=names,required-names)
                for name in names:
                    parts=Path(name).parts
                    self.assertFalse(set(parts)&{'src','dist','.runtime','.venv','.git','.cache','reference'},name)
                    self.assertNotIn(Path(name).suffix.lower(),{'.dsf','.exe','.dll','.ttf','.ttc'},name)
                manifest=json.loads(archive.read('FluentGlass/source-manifest.json'))
                self.assertEqual(manifest['distribution'],'source-only')
                self.assertEqual(set(manifest['files']),names-{'source-manifest.json'})
                import hashlib
                for name,digest in manifest['files'].items():
                    self.assertEqual(hashlib.sha256(archive.read('FluentGlass/'+name)).hexdigest(),digest,name)

    def test_clean_directory_has_no_old_history_and_never_overwrites_user_files(self):
        with tempfile.TemporaryDirectory(prefix='Fluent clean source ') as folder:
            output=Path(folder)/'source.zip';checkout=Path(folder)/'GitHub source'
            command=[sys.executable,str(ROOT/'tools'/'package_source.py'),
                     '--output',str(output),'--directory',str(checkout)]
            run=subprocess.run(command,capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
            self.assertTrue((checkout/'tools'/'build.py').is_file())
            self.assertFalse((checkout/'.git').exists(),'Old Git objects must never enter public source')
            self.assertFalse((checkout/'src').exists())
            marker=checkout/'keep-my-file.txt';marker.write_text('preserve me')
            repeated=subprocess.run(command,capture_output=True,text=True)
            self.assertNotEqual(repeated.returncode,0,'Existing nonempty exports must not be overwritten')
            self.assertEqual(marker.read_text(),'preserve me')


if __name__=='__main__':unittest.main(verbosity=2)
