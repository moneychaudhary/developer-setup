import json
import pathlib
import plistlib
import shutil
import tempfile

from . import providers

SOURCE = pathlib.Path(__file__).resolve().parents[1] / 'config/workspace'
SCRIPTS = ('signin.sh', 'signout.sh')
# App name, SF Symbol and colour for each workspace shortcut
APPS = {'SignIn': ('sunrise.fill', '0.20', '0.72', '0.40'), 'SignOut': ('power', '0.88', '0.24', '0.22')}


def install_scripts(home, managed):
    # Write the scripts through the managed writer so rollback can restore them
    target = home / '.local/share/workspace'
    for name in SCRIPTS + ('mouse.swift',):
        managed.write(target / name, (SOURCE / name).read_text())
    for name in SCRIPTS:
        (target / name).chmod(0o700)
    return target


def build_helper(target, run):
    # Compile the window helper that sends real clicks and drags
    if not shutil.which('swiftc'):
        return 'Window helper not built: install the Xcode command-line tools, then rerun.'
    run(['swiftc', '-O', str(target / 'mouse.swift'), '-o', str(target / 'mouse')])
    return ''


def make_icns(name, symbol_args, work, run):
    # Draw a PNG with the icon generator and convert it into an .icns file
    png, iconset = work / (name + '.png'), work / (name + '.iconset')
    run([str(work / 'icon'), *symbol_args, str(png)])
    iconset.mkdir()
    for size in (16, 32, 128, 256, 512):
        run(['sips', '-z', str(size), str(size), str(png), '--out', str(iconset / f'icon_{size}x{size}.png')])
        run(['sips', '-z', str(size * 2), str(size * 2), str(png), '--out', str(iconset / f'icon_{size}x{size}@2x.png')])
    run(['iconutil', '-c', 'icns', str(iconset), '-o', str(work / (name + '.icns'))])
    return work / (name + '.icns')


def build_apps(home, run):
    # Compile SignIn and SignOut, give them their icons and names, and sign them ad hoc
    folder = home / 'Applications/Workspace'
    folder.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temp:
        work = pathlib.Path(temp)
        run(['swiftc', '-O', str(SOURCE / 'icon.swift'), '-o', str(work / 'icon')])
        for name, symbol_args in APPS.items():
            app = folder / (name + '.app')
            if app.exists():
                shutil.rmtree(app)
            run(['osacompile', '-o', str(app), str(SOURCE / (name + '.applescript'))])
            shutil.copy(make_icns(name, symbol_args, work, run), app / 'Contents/Resources/applet.icns')
            (app / 'Contents/Resources/Assets.car').unlink(missing_ok=True)
            info = app / 'Contents/Info.plist'
            data = plistlib.loads(info.read_bytes())
            data.pop('CFBundleIconName', None)
            data['CFBundleName'] = name
            info.write_bytes(plistlib.dumps(data))
            run(['codesign', '--force', '--sign', '-', str(app)])
    return folder


def desktop_shortcuts(home):
    # Link each existing app onto the Desktop, never replacing something already there
    desktop, made = home / 'Desktop', []
    desktop.mkdir(exist_ok=True)
    for label, path in json.loads((SOURCE / 'shortcuts.json').read_text()).items():
        target = pathlib.Path(path.replace('~', str(home), 1))
        link = desktop / label
        if target.exists() and not link.exists() and not link.is_symlink():
            link.symlink_to(target)
            made.append(label)
    return made


def configure(home, managed, run=providers.run):
    # Install the workspace scripts, helper, SignIn and SignOut apps, and Desktop shortcuts
    target = install_scripts(home, managed)
    notes = [build_helper(target, run)]
    if shutil.which('osacompile') and shutil.which('swiftc'):
        build_apps(home, run)
    else:
        notes.append('SignIn and SignOut apps need macOS with the Xcode command-line tools.')
    made = desktop_shortcuts(home)
    notes.append('Desktop shortcuts added: ' + (', '.join(made) if made else 'none new'))
    notes.append('First run of SignIn asks for Accessibility and System Events permission.')
    return ' '.join(n for n in notes if n)
