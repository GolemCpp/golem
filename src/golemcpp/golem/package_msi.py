import os
import re
import hashlib
import platform
from golemcpp.golem import helpers
from golemcpp.golem.version import Version
from waflib import Logs, Task


def package_msi(self, package_build_context):

    print("Check package's targets")

    depends = package_build_context.configuration.packages.copy()
    depends = helpers.filter_unique(depends)

    msi_package = package_build_context.package.msi_package
    # depends = helpers.filter_unique(msi_package.depends + depends)

    print("Gather package metadata")
    prefix = ""

    subdirectory = prefix

    package_name = package_build_context.package.name
    #package_section = msi_package.section
    #package_priority = msi_package.priority
    #package_maintainer = msi_package.maintainer
    #package_description = msi_package.description
    #package_homepage = msi_package.homepage

    version = Version(working_dir=self.get_project_dir(),
                      build_number=self.get_build_number())

    build_number = self.get_build_number(default=0)
    package_version = '{}.{}.{}.{}'.format(version.major, version.minor,
                                           version.patch, build_number)

    package_arch = self.get_arch_for_linux()
    package_depends = ', '.join(depends)

    print("Clean-up")
    package_directory = self.make_output_path('dist')
    helpers.remove_tree(self, package_directory)
    files_directory = os.path.join(package_directory, 'files')
    wix_directory = os.path.join(package_directory, 'wix')

    print("Prepare package")
    files_directory = helpers.make_directory(files_directory)
    wix_directory = helpers.make_directory(wix_directory)

    prefix_directory = os.path.realpath(
        helpers.make_directory(files_directory, '.' + prefix))

    subdirectory_directory = os.path.realpath(
        helpers.make_directory(files_directory, '.' + subdirectory))

    helpers.make_directory(subdirectory_directory)

    package_skeleton = None

    if msi_package.skeleton:
        package_skeleton = os.path.join(self.get_project_dir(),
                                        msi_package.skeleton)

    if package_skeleton and not os.path.exists(package_skeleton):
        raise RuntimeError(
            "Package skeleton directory doesn't exist: {}".format(
                package_skeleton))

    if package_skeleton:
        helpers.copy_tree(package_skeleton, prefix_directory)

    package_wix_directory = None

    if msi_package.project:
        package_wix_directory = os.path.join(self.get_project_dir(),
                                             msi_package.project)

    if package_wix_directory and not os.path.exists(package_wix_directory):
        raise RuntimeError("Package wix directory doesn't exist: {}".format(
            package_wix_directory))

    if package_wix_directory:
        helpers.copy_tree(package_wix_directory, wix_directory)

    artifacts = package_build_context.configuration.artifacts.copy()
    artifacts = [artifact for artifact in artifacts if artifact.scope is None]

    for artifact in artifacts:
        local_dir = ''
        if artifact.type == 'library':
            local_dir = ''
        elif artifact.type == 'program':
            local_dir = ''
        elif artifact.type == 'license':
            if artifact.location != self.get_project_dir():
                dep_id = self.find_dependency_id(artifact.location)
                local_dir = os.path.join('share', 'doc',
                                         package_build_context.package.name,
                                         'licenses', dep_id)
            else:
                local_dir = os.path.join('share', 'doc',
                                         package_build_context.package.name,
                                         'licenses')
        else:
            local_dir = 'share'

        artifact_filename = os.path.basename(artifact.path)
        artifact_dirname = os.path.dirname(artifact.path)
        if artifact_dirname:
            local_dir = ''

        dst_directory = os.path.realpath(
            helpers.make_directory(subdirectory_directory,
                                   os.path.join(artifact_dirname, local_dir)))

        src = artifact.absolute_path
        dst = os.path.abspath(os.path.join(dst_directory, artifact_filename))
        dst_dir = os.path.dirname(dst)
        if not os.path.exists(dst_dir):
            print("Creating directories {}".format(dst_dir))
            os.makedirs(dst_dir)
        print("Copying {} to {}".format(src, dst))
        helpers.copy_file(src, dst)
        artifact.path = os.path.join(artifact_dirname, local_dir,
                                     artifact_filename)
        artifact.location = os.path.realpath(subdirectory_directory)

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

    if 'qt5' in package_build_context.configuration.wfeatures:
        if not self.context.env.QMAKE:
            raise RuntimeError("Can't find path to qmake")
        if not self.context.env.QTLIBS:
            raise RuntimeError("Can't find path to Qt libraries")
        for binary in unique_targets_binaries:

            if binary not in qt5_unique_targets_binaries:
                print("{} is not a Qt binary".format(binary))
                continue

            print("Run windeployqt {}".format(binary))

            real_path = os.path.realpath(
                os.path.join(subdirectory_directory, binary))
            if not os.path.exists(real_path):
                raise RuntimeError(
                    "Cannot find binary path {}".format(real_path))

            deployqt_bin = os.path.join(self.context.env.QT_HOST_BINS,
                                        'windeployqt')
            helpers.run_task([deployqt_bin, binary] + [
                '-qmldir={}'.format(
                    os.path.realpath(
                        os.path.join(self.get_project_dir(), qmldir)))
                for qmldir in package_build_context.configuration.qmldirs
            ],
                             cwd=subdirectory_directory)

    for symlink_path in targets_binaries_symlinks:
        os.remove(symlink_path)

    all_prefix_files = []
    for (dirpath, dirnames, filenames) in os.walk(subdirectory_directory):
        all_prefix_files.extend([
            os.path.realpath(os.path.join(dirpath, filename))
            for filename in filenames
        ])

    template_tempoary_dir = self.make_build_path('dist_templates_wix')
    helpers.make_directory(template_tempoary_dir)

    wxs_files = self.list_files('', [wix_directory], ['wxs'])
    wxl_files = self.list_files('', [wix_directory], ['wxl'])

    component_list = list()
    component_ref_list = list()

    for file_path in all_prefix_files:
        path = os.path.relpath(path=file_path, start=subdirectory_directory)
        print("Component: {}".format(path))
        path_id = '_' + hashlib.md5(path.encode('utf-8')).hexdigest()
        is_binary = os.path.splitext(file_path)[1] in ['.dll', '.exe']
        component = '<Component Id="{}" Guid="*" Win64="{}">\n'.format(
            path_id, 'yes' if self.is_x64() else 'no')
        component = '{}\t<File Source="{}" Id="{}" KeyPath="yes" Checksum="{}"/>\n'.format(
            component, file_path, path_id, 'yes' if is_binary else 'no')
        component = '{}</Component>'.format(component)
        component_list.append(component)
        component = '<ComponentRef Id="{}"/>'.format(path_id)
        component_ref_list.append(component)

    components_string = "\n".join(component_list)
    component_refs_string = "\n".join(component_ref_list)

    msvc_toolset = self.get_current_msvc_toolset()
    msvc_path = self.vswhere_get_installation_path()
    msvc_crt_path = os.path.join(
        msvc_path, 'VC', 'Redist', 'MSVC', msvc_toolset, 'MergeModules',
        'Microsoft_VC{}_CRT_{}.msm'.format(msvc_toolset[1:], self.get_arch()))

    if not os.path.exists(msvc_crt_path):
        raise RuntimeError(
            "Cannot find VC redistributable file {}".format(msvc_crt_path))

    msvc_crt_merge = '<Merge Id="VCRedist" SourceFile="{}" DiskId="1" Language="0"/>'.format(
        msvc_crt_path)
    msvc_crt_merge_ref = '<MergeRef Id="VCRedist"/>'

    for wix_file in wxs_files + wxl_files:
        wix_file = str(wix_file)
        wix_file_relative = os.path.relpath(path=wix_file, start=wix_directory)

        if not os.path.exists(str(wix_file)):
            raise RuntimeError("Cannot find any file at {}".format(
                str(wix_file)))

        tmp_path = os.path.join(template_tempoary_dir, wix_file_relative)
        helpers.make_directory(os.path.dirname(tmp_path))
        helpers.copy_file(wix_file, tmp_path)
        os.remove(wix_file)

        wix_file_src = self.context.root.find_node(tmp_path)
        wix_file_dst = self.context.root.find_or_declare(wix_file)

        self.context(
            features='subst',
            source=wix_file_src,
            target=wix_file_dst,
            GOLEM_PACKAGE_MSI_INSTALL_FILES_COMPONENTS=str(components_string),
            GOLEM_PACKAGE_MSI_INSTALL_FILES_COMPONENT_REFS=str(
                component_refs_string),
            GOLEM_PACKAGE_MSI_MSVC_CRT_MERGE=str(msvc_crt_merge),
            GOLEM_PACKAGE_MSI_MSVC_CRT_MERGE_REF=str(msvc_crt_merge_ref),
            GOLEM_PACKAGE_MSI_BINARY_PATH=str(
                os.path.join(subdirectory, target_programs[0])),
            GOLEM_PACKAGE_MSI_VERSION=str(package_version))

    self.context.add_group()
    self.context.execute_build()

    harvested_files_wxs = 'golem_files.wxs'

    helpers.run_task([
        'heat', 'dir', subdirectory_directory, '-nologo', '-var',
        'var.GolemDistSourceDir', '-ag', '-cg',
        msi_package.installdir_files_id, '-dr', msi_package.installdir_id,
        '-sreg', '-srd', '-sfrag', '-platform',
        self.get_arch(), '-o', harvested_files_wxs
    ],
                     cwd=wix_directory)

    wix_parameters = [
        '-d{}'.format(param) for param in msi_package.parameters
    ] + ['-dGolemDistSourceDir={}'.format(subdirectory_directory)]

    wix_extensions = []
    for extension in msi_package.extensions:
        wix_extensions += ['-ext', extension]

    wix_locales = []
    for path in wxl_files:
        wix_locales += ['-loc', str(path)]

    wix_cultures = []
    if msi_package.cultures:
        wix_cultures = ['-cultures:' + ';'.join(msi_package.cultures)]

    wix_declarations = [str(path)
                        for path in wxs_files] + [harvested_files_wxs]

    wix_objfiles = []
    for path in wix_declarations:
        objpath = path + '.wixobj'
        helpers.run_task(
            ['candle', '-nologo', '-out', objpath, '-arch',
             self.get_arch()] + wix_parameters + wix_extensions + [path],
            cwd=wix_directory)
        wix_objfiles.append(objpath)

    output_filename = package_name + '_' + package_version + "_" + package_arch
    output_filename_path = output_filename + '.msi'
    package_filename = output_filename_path
    package_path = os.path.realpath(
        os.path.join(self.get_output_path(), package_filename))

    helpers.run_task(['light', '-nologo', '-o', package_path] + wix_locales +
                     wix_cultures + wix_extensions + wix_objfiles,
                     cwd=wix_directory)

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

    package_file = File(path=package_filename,
                        absolute_path=package_path,
                        type='package')

    libraries_list = self.find_artifacts(path=subdirectory_directory,
                                         recursively=True,
                                         types=('*.dll'))

    for file_path in all_prefix_files:
        if os.path.realpath(file_path) in files_absolute_paths:
            continue

        file_type = 'library' if file_path in libraries_list else 'file'

        if file_type == 'library':
            is_executable = os.path.splitext(file_path)[1] in ['.dll', '.exe']
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
