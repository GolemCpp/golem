import os
import re
import hashlib
import platform
from golemcpp.golem import helpers
import subprocess
import time
import stat
from golemcpp.golem.version import Version
from waflib import Logs, Task


def package_dmg(self, package_build_context):

    print("Check package's targets")

    depends = package_build_context.configuration.packages.copy()
    depends = helpers.filter_unique(depends)

    dmg_package = package_build_context.package.dmg_package
    # depends = helpers.filter_unique(dmg_package.depends + depends)

    print("Gather package metadata")
    prefix = ""

    subdirectory = prefix

    package_name = dmg_package.name if dmg_package.name else package_build_context.package.name
    #package_section = dmg_package.section
    #package_priority = dmg_package.priority
    #package_maintainer = dmg_package.maintainer
    #package_description = dmg_package.description
    #package_homepage = dmg_package.homepage

    version = Version(working_dir=self.get_project_dir(),
                      build_number=self.get_build_number())

    build_number = self.get_build_number(default=0)
    package_version = '{}.{}.{}'.format(version.major, version.minor,
                                        version.patch)
    package_build_version = '{}.{}.{}.{}'.format(version.major, version.minor,
                                                 version.patch, build_number)

    package_arch = self.get_arch_for_linux()
    package_depends = ', '.join(depends)

    print("Clean-up")
    package_directory = self.make_output_path('dist')
    helpers.remove_tree(self, package_directory)
    app_bundle_name = package_name + '.app'
    app_directory = os.path.join(package_directory, app_bundle_name,
                                 'Contents')
    app_bundle_directory = os.path.join(package_directory, app_bundle_name)

    print("Prepare package")
    app_directory = helpers.make_directory(app_directory)

    prefix_directory = os.path.realpath(
        helpers.make_directory(app_directory, '.' + prefix))

    subdirectory_directory = os.path.realpath(
        helpers.make_directory(app_directory, '.' + subdirectory))

    helpers.make_directory(subdirectory_directory)

    package_skeleton = None

    if dmg_package.skeleton:
        package_skeleton = os.path.join(self.get_project_dir(),
                                        dmg_package.skeleton)

    if package_skeleton and not os.path.exists(package_skeleton):
        raise RuntimeError(
            "Package skeleton directory doesn't exist: {}".format(
                package_skeleton))

    if package_skeleton:
        helpers.copy_tree(package_skeleton, prefix_directory)

    artifacts = package_build_context.configuration.artifacts.copy()
    artifacts = [artifact for artifact in artifacts if artifact.scope is None]

    binary_artifacts = list()

    for artifact in artifacts:
        local_dir = 'MacOS'
        if artifact.type == 'library':
            local_dir = 'Frameworks'
        elif artifact.type == 'program':
            local_dir = 'MacOS'
        elif artifact.type == 'license':
            if artifact.location != self.get_project_dir():
                dep_id = self.find_dependency_id(artifact.location)
                local_dir = os.path.join('Resources', 'share', 'doc',
                                         package_build_context.package.name,
                                         'licenses', dep_id)
            else:
                local_dir = os.path.join('Resources', 'share', 'doc',
                                         package_build_context.package.name,
                                         'licenses')
        else:
            local_dir = os.path.join('Resources', 'share')

        artifact_filename = os.path.basename(artifact.path)
        artifact_dirname = os.path.dirname(artifact.path)

        dst_directory = os.path.realpath(
            helpers.make_directory(subdirectory_directory,
                                   os.path.join(local_dir, artifact_dirname)))

        src = artifact.absolute_path
        dst = os.path.abspath(os.path.join(dst_directory, artifact_filename))
        dst_dir = os.path.dirname(dst)
        if not os.path.exists(dst_dir):
            print("Creating directories {}".format(dst_dir))
            os.makedirs(dst_dir)
        print("Copying {} to {}".format(src, dst))
        helpers.copy_file(src, dst)
        artifact.path = os.path.join(local_dir, artifact_dirname,
                                     artifact_filename)
        artifact.location = os.path.realpath(subdirectory_directory)
        if artifact.type in ['library', 'program']:
            binary_artifacts.append(artifact)

    for binary_artifact in binary_artifacts:
        self.patch_darwin_binary_artifacts(binary_artifacts=[binary_artifact],
                                           prefix_path='@loader_path',
                                           source_artifacts=binary_artifacts,
                                           relative_path=True)

    repository = self.load_git_remote_origin_url()
    targets_binaries = []
    targets_libpaths = ['lib']
    target_programs = []
    qt5_binaries = []
    for artifact in artifacts:
        if artifact.type in ['library', 'program']:
            if artifact.target in package_build_context.package.targets and artifact.repository == repository:
                targets_binaries.append(artifact.path)

                target_config = None
                if artifact.target in package_build_context.targets_and_configs:
                    target_config = package_build_context.targets_and_configs[
                        artifact.target]

                if target_config and self.is_qt5_enabled(config=target_config):
                    qt5_binaries.append(artifact.path)

                if artifact.type in ['program']:
                    target_programs.append(artifact.path)

        if artifact.type in ['library']:
            target_path = os.path.dirname(artifact.path)
            if target_path:
                targets_libpaths.append(target_path)

    targets_binaries = helpers.filter_unique(targets_binaries)
    targets_libpaths = helpers.filter_unique(targets_libpaths)

    targets_binaries_real_paths = list()
    unique_targets_binaries = list()
    for binary in targets_binaries:
        real_path = os.path.realpath(
            os.path.join(subdirectory_directory, binary))
        if real_path in targets_binaries_real_paths:
            continue
        targets_binaries_real_paths.append(real_path)
        unique_targets_binaries.append(binary)
    targets_binaries_symlinks = list()

    qt5_targets_binaries_real_paths = list()
    qt5_unique_targets_binaries = list()
    for binary in qt5_binaries:
        real_path = os.path.realpath(
            os.path.join(subdirectory_directory, binary))
        if real_path in qt5_targets_binaries_real_paths:
            continue
        qt5_targets_binaries_real_paths.append(real_path)
        qt5_unique_targets_binaries.append(binary)

    template_tempoary_dir = self.make_build_path('dist_templates_app')
    helpers.make_directory(template_tempoary_dir)

    template_files = [os.path.join(app_directory, 'Info.plist')]

    for template_file in template_files:
        template_file = str(template_file)
        template_file_relative = os.path.relpath(path=template_file,
                                                 start=app_directory)

        if not os.path.exists(str(template_file)):
            continue

        tmp_path = os.path.join(template_tempoary_dir, template_file_relative)
        helpers.make_directory(os.path.dirname(tmp_path))
        helpers.copy_file(template_file, tmp_path)
        os.remove(template_file)

        template_file_src = self.context.root.find_node(tmp_path)
        template_file_dst = self.context.root.find_or_declare(template_file)

        self.context(
            features='subst',
            source=template_file_src,
            target=template_file_dst,
            GOLEM_PACKAGE_DMG_BUNDLE_NAME=str(package_name),
            GOLEM_PACKAGE_DMG_BUNDLE_EXECUTABLE=str(
                os.path.relpath(path=os.path.join(app_directory,
                                                  target_programs[0]),
                                start=os.path.join(app_directory, 'MacOS'))),
            GOLEM_PACKAGE_DMG_VERSION=str(package_version),
            GOLEM_PACKAGE_DMG_BUILD_VERSION=str(package_build_version))

    self.context.add_group()
    self.context.execute_build()

    if 'qt5' in package_build_context.configuration.wfeatures:
        if not self.context.env.QMAKE:
            raise RuntimeError("Can't find path to qmake")
        if not self.context.env.QTLIBS:
            raise RuntimeError("Can't find path to Qt libraries")
        for binary in unique_targets_binaries:

            if binary not in qt5_unique_targets_binaries:
                print("{} is not a Qt binary".format(binary))
                continue

            print("Run macdeployqt {}".format(binary))

            real_path = os.path.realpath(
                os.path.join(subdirectory_directory, binary))
            if not os.path.exists(real_path):
                raise RuntimeError(
                    "Cannot find binary path {}".format(real_path))

            deployqt_bin = os.path.join(self.context.env.QT_HOST_BINS,
                                        'macdeployqt')
            helpers.run_task([
                deployqt_bin, app_bundle_name, '-always-overwrite',
                '-executable={}'.format(
                    os.path.relpath(path=real_path, start=package_directory))
            ] + [
                '-qmldir={}'.format(
                    os.path.realpath(
                        os.path.join(self.get_project_dir(), qmldir)))
                for qmldir in package_build_context.configuration.qmldirs
            ],
                             cwd=package_directory,
                             debug=True)

        qt_conf_path = os.path.join(subdirectory_directory, 'Resources',
                                    'qt.conf')
        if not os.path.exists(qt_conf_path):
            with open(qt_conf_path, 'w') as qt_conf_file:
                qt_conf_file.writelines([
                    "[Paths]\n",  # Header
                    "Plugins = PlugIns\n",  # Plugin
                    "Imports = Resources/qml\n",  # QML imports
                    "Qml2Imports = Resources/qml\n"  # QML imports
                ])

    for symlink_path in targets_binaries_symlinks:
        os.remove(symlink_path)

    ps = subprocess.Popen(('du', '-sh', app_bundle_directory),
                          stdout=subprocess.PIPE,
                          cwd=package_directory)
    size_string = subprocess.check_output(
        ['sed', 's/\\([0-9\\.]*\\)M\\(.*\\)/\\1/'],
        stdin=ps.stdout,
        cwd=package_directory).split()[0].decode('utf-8')
    ps.wait()

    size = int(size_string)

    if size is None or size <= 0:
        raise RuntimeError("Bad size of app folder: {}".format(size))

    size += 1

    size_in_mbytes = 0
    volume_background_path = ''

    if dmg_package.background:
        volume_background_path = os.path.join(self.get_project_dir(),
                                              dmg_package.background)

    if volume_background_path and os.path.exists(volume_background_path):
        size_in_mbytes += os.path.getsize(volume_background_path) / 1048576

    size_in_mbytes += 1
    size += int(size_in_mbytes)

    volume_name = '{} {}'.format(package_name, package_version)
    volume_tmp = volume_name + '-temp.dmg'
    volume_final = volume_name + '.dmg'

    helpers.run_task([
        'hdiutil', 'create', '-srcfolder', app_bundle_directory, '-volname',
        volume_name, '-fs', 'HFS+', '-fsargs', '-c c=64,a=16,e=16', '-format',
        'UDRW', '-size', '{}M'.format(size), volume_tmp
    ],
                     cwd=package_directory,
                     debug=True)

    background_script_line = 'set background picture of viewOptions to file ".background:{}"'.format(
        os.path.basename(
            volume_background_path)) if volume_background_path else ''

    script = \
"""\
tell application "Finder"
    tell disk "{}"
        open
        set current view of container window to icon view
        set toolbar visible of container window to false
        set statusbar visible of container window to false
        set the bounds of container window to {{400, 100, 900, 400}}
        set viewOptions to the icon view options of container window
        set arrangement of viewOptions to not arranged
        set icon size of viewOptions to 72
        {}
        make new alias file at container window to POSIX file "/Applications" with properties {{name:"Applications"}}
        set position of item "{}" of container window to {{150, 170}}
        set position of item "Applications" of container window to {{350, 170}}
        close
        open
        update without registering applications
        delay 2
    end tell
end tell
""".format(volume_name, background_script_line, app_bundle_name)

    print("Run hdiutil attach -readwrite -noverify {}".format(volume_tmp))
    ps1 = subprocess.Popen(
        ('hdiutil', 'attach', '-readwrite', '-noverify', volume_tmp),
        stdout=subprocess.PIPE,
        cwd=package_directory)
    ps2 = subprocess.Popen(('egrep', '^/dev/'),
                           stdin=ps1.stdout,
                           stdout=subprocess.PIPE,
                           cwd=package_directory)
    ps3 = subprocess.Popen(('sed', '1q'),
                           stdin=ps2.stdout,
                           stdout=subprocess.PIPE,
                           cwd=package_directory)
    device_id = subprocess.check_output(
        ['awk', '{print $1}'], stdin=ps3.stdout,
        cwd=package_directory).split()[0].decode('utf-8')
    ps1.wait()
    ps2.wait()
    ps3.wait()

    print("Wait for 5 seconds")
    time.sleep(5)

    if volume_background_path:
        print("Install background image into the DMG volume: {}".format(
            volume_background_path))
        background_directory = os.path.join("/Volumes", volume_name,
                                            ".background")
        helpers.make_directory(background_directory)
        helpers.copy_file(volume_background_path, background_directory)

    print("Run osascript...")
    print("{}".format(script))
    ps = subprocess.Popen(('echo', script),
                          stdout=subprocess.PIPE,
                          cwd=package_directory)
    _ = subprocess.check_output(['osascript'],
                                stdin=ps.stdout,
                                cwd=package_directory)
    ps.wait()

    helpers.run_task(["sync"], cwd=package_directory, debug=True)

    helpers.run_task(['hdiutil', 'detach', device_id],
                     cwd=package_directory,
                     debug=True)

    helpers.run_task([
        'hdiutil', 'convert', volume_tmp, '-format', 'UDZO', '-imagekey',
        'zlib-level=9', '-o', volume_final
    ],
                     cwd=package_directory,
                     debug=True)

    os.remove(os.path.join(package_directory, volume_tmp))

    all_prefix_files = []
    for (dirpath, dirnames, filenames) in os.walk(subdirectory_directory):
        all_prefix_files.extend([
            os.path.realpath(os.path.join(dirpath, filename))
            for filename in filenames
        ])

    system_name = self.osname()
    distribution_name = self.distribution()
    release_name = self.release()

    class File:
        def __init__(self, path, absolute_path, type='file'):
            self.path = path
            self.absolute_path = absolute_path
            self.type = type

    class System:
        def __init__(self):
            self.name = system_name
            self.distribution = distribution_name
            self.release = release_name
            self.version = platform.platform()
            self.architecture = package_arch

    files_absolute_paths = []
    files = []
    for artifact in artifacts:
        artifact_file = File(path=artifact.path,
                             absolute_path=artifact.absolute_path,
                             type=artifact.type)
        files_absolute_paths.append(os.path.realpath(artifact.absolute_path))
        files.append(artifact_file)

    package_file = File(path=volume_final,
                        absolute_path=os.path.join(package_directory,
                                                   volume_final),
                        type='package')

    libraries_list = self.find_artifacts(path=subdirectory_directory,
                                         recursively=True,
                                         types=('*.so', '*.so.*', '*.dylib',
                                                '*.dylib.*'))

    for file_path in all_prefix_files:
        if os.path.realpath(file_path) in files_absolute_paths:
            continue

        file_type = 'library' if file_path in libraries_list else 'file'

        if file_type == 'library':
            is_executable = (os.stat(file_path).st_mode & stat.S_IXUSR) > 0
            file_type = file_type if is_executable else 'file'

        artifact_file = File(path=os.path.relpath(
            path=file_path, start=subdirectory_directory),
                             absolute_path=file_path,
                             type=file_type)

        files_absolute_paths.append(file_path)
        files.append(artifact_file)

    class Context:
        def __init__(self):
            self.name = package_build_context.package.name
            self.binaries = targets_binaries
            self.libpaths = targets_libpaths
            self.targets = package_build_context.package.targets
            self.files = files
            self.version = version.semver
            self.major = version.major
            self.minor = version.minor
            self.patch = version.patch
            self.build_number = build_number
            self.hash = version.githash
            self.system = System()
            self.message = version.gitmessage
            self.package = package_file

    ctx = Context()
    for hook in package_build_context.package.hooks:
        hook(ctx)
