"""Export public source only; never ship generated PotPlayer resources or history."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT=Path(__file__).resolve().parents[1]
ROOT_FILES=('README.md','LICENSE','THIRD_PARTY_NOTICES.md','requirements.txt',
            '.gitignore','安装皮肤.cmd','预览皮肤.cmd')
SOURCE_DIRS={'tools':{'.py','.ps1'},'tests':{'.py','.md'},
             'assets':{'.svg','.png','.md','.txt'},'docs':{'.md','.png'}}
EXCLUDED={'.git','.runtime','.venv','.cache','__pycache__','src','dist','reference'}


def source_files():
    files=[ROOT/name for name in ROOT_FILES if (ROOT/name).is_file()]
    for directory,suffixes in SOURCE_DIRS.items():
        for path in (ROOT/directory).rglob('*'):
            relative=path.relative_to(ROOT)
            if set(relative.parts)&EXCLUDED:continue
            if path.is_file() and (path.suffix.lower() in suffixes or path.name=='LICENSE'):
                files.append(path)
    result={}
    for path in sorted(files):
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT):
            raise ValueError(f'Linked source is not allowed: {path.relative_to(ROOT)}')
        result[path.relative_to(ROOT).as_posix()]=path.read_bytes()
    required={'README.md','LICENSE','THIRD_PARTY_NOTICES.md','tools/build.py',
              'assets/logo/glass-orbit.svg','assets/lucide/LICENSE'}
    if required-result.keys():raise ValueError('Missing required source: '+str(required-result.keys()))
    return result


def package(output,directory=None):
    if output.suffix.lower()!='.zip':raise ValueError('Source archive must use the .zip extension')
    if directory is not None:
        if directory==ROOT or any(directory.is_relative_to(ROOT/name) for name in SOURCE_DIRS):
            raise ValueError('Export directory must be separate from the original source directories')
        if output.is_relative_to(directory):
            raise ValueError('Archive must be outside the clean export directory')
        if directory.exists() and (not directory.is_dir() or any(directory.iterdir())):
            raise ValueError('Export directory must be new or empty; existing files are never overwritten')
    files=source_files()
    # Keep the exported manifest valid after a Windows Git checkout as well.
    # This affects line-ending conversion, not Git's text diff detection.
    files['.gitattributes']=b'# Preserve source-manifest byte hashes across Git checkouts.\n* -text\n'
    manifest={'format':'fluent-glass-source-v1','distribution':'source-only',
              'files':{name:hashlib.sha256(data).hexdigest() for name,data in files.items()}}
    files['source-manifest.json']=(json.dumps(manifest,ensure_ascii=True,indent=2)+'\n').encode()
    output.parent.mkdir(parents=True,exist_ok=True)
    with ZipFile(output,'w',ZIP_DEFLATED) as archive:
        for name,data in files.items():
            info=ZipInfo('FluentGlass/'+name)
            info.compress_type=ZIP_DEFLATED
            info.external_attr=0o100644<<16
            archive.writestr(info,data)
    if directory is not None:
        directory.mkdir(parents=True,exist_ok=True)
        for name,data in files.items():
            target=directory/name
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(data)
    return len(files)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'.release'/'FluentGlass-source.zip')
    parser.add_argument('--directory',type=Path,help='Also write a new clean directory without Git history')
    args=parser.parse_args()
    try:
        count=package(args.output.resolve(),args.directory.resolve() if args.directory else None)
    except (ValueError,OSError) as error:
        parser.exit(1,str(error)+'\n')
    print(json.dumps({'archive':str(args.output.resolve()),'files':count,'distribution':'source-only'}))
